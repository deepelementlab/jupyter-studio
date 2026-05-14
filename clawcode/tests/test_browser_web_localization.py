from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.asyncio
async def test_website_policy_blocks_domain_via_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from clawcode.config.settings import load_settings
    from clawcode.llm.tools.browser.website_policy import (
        check_website_access,
        invalidate_cache,
    )

    settings = await load_settings(working_directory=str(tmp_path), debug=False)
    settings.website_blocklist.enabled = True
    settings.website_blocklist.domains = ["example.com"]
    settings.website_blocklist.shared_files = []
    invalidate_cache()

    out = check_website_access("https://sub.example.com/docs")
    assert out is not None
    assert out["host"] == "sub.example.com"
    assert out["rule"] == "example.com"
    assert out["source"] == "config"


@pytest.mark.asyncio
async def test_website_policy_shared_file_via_settings(tmp_path: Path) -> None:
    from clawcode.config.settings import load_settings
    from clawcode.llm.tools.browser.website_policy import (
        check_website_access,
        invalidate_cache,
    )

    settings = await load_settings(working_directory=str(tmp_path), debug=False)
    data_dir = settings.get_data_directory()
    block_file = data_dir / "shared_blocklist.txt"
    block_file.parent.mkdir(parents=True, exist_ok=True)
    block_file.write_text("blocked.com\n# comment\n", encoding="utf-8")

    settings.website_blocklist.enabled = True
    settings.website_blocklist.domains = []
    # relative path should be resolved under clawcode data dir
    settings.website_blocklist.shared_files = ["shared_blocklist.txt"]
    invalidate_cache()

    out = check_website_access("https://blocked.com/path")
    assert out is not None
    assert out["host"] == "blocked.com"
    assert out["rule"] == "blocked.com"
    assert out["source"] == str(block_file.resolve())


@pytest.mark.asyncio
async def test_auxiliary_llm_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from clawcode.llm.base import ProviderResponse, TokenUsage
    from clawcode.llm.tools.browser import auxiliary_llm

    class FakeProvider:
        async def send_messages(self, messages, tools=None):  # noqa: ANN001
            del messages, tools
            return ProviderResponse(
                content="hello",
                thinking="",
                tool_calls=[],
                usage=TokenUsage(input_tokens=1, output_tokens=1),
                finish_reason="stop",
                model="fake",
                cache_stats=None,
            )

    monkeypatch.setattr(
        auxiliary_llm,
        "_resolve_provider_for_model",
        lambda model_id: ("openai", "openai", (None, None)),
    )
    monkeypatch.setattr(
        auxiliary_llm,
        "create_provider",
        lambda **_: FakeProvider(),
    )

    resp = await auxiliary_llm.async_call_llm(
        messages=[{"role": "user", "content": "ping"}],
        model="fake-model",
        temperature=0.1,
        max_tokens=64,
    )
    assert resp.choices[0].message.content == "hello"


@pytest.mark.asyncio
async def test_browser_web_tool_wrappers_pass_task_id_and_await_async(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall, ToolContext
    from clawcode.llm.tools.browser import browser_tools

    # --- browser_navigate wrapper ---
    def _fake_browser_navigate(*, url: str, task_id: str | None = None, **_kw) -> str:
        return f"nav:{url}:task:{task_id}"

    monkeypatch.setattr(browser_tools, "browser_navigate", _fake_browser_navigate)
    browser_tool_list = browser_tools.create_browser_tools()
    nav_tool = next(t for t in browser_tool_list if t.info().name == "browser_navigate")

    ctx = ToolContext(session_id="sess1", message_id="msg1", working_directory=str(tmp_path))
    call = ToolCall(id="c1", name="browser_navigate", input={"url": "https://example.com"})
    nav_resp = await nav_tool.run(call, ctx)
    assert nav_resp.content == "nav:https://example.com:task:sess1"
    assert nav_resp.is_error is False

    # --- web_extract wrapper (async) ---
    async def _fake_web_extract_tool(*, urls, format: str | None = None, **_kw) -> str:  # noqa: ANN001
        del format
        return "extract_ok:" + ",".join(urls)

    monkeypatch.setattr(browser_tools, "web_extract_tool", _fake_web_extract_tool)
    web_tool_list = browser_tools.create_web_tools()
    extract_tool = next(t for t in web_tool_list if t.info().name == "web_extract")
    extract_call = ToolCall(id="c2", name="web_extract", input={"urls": ["https://a.com", "https://b.com"]})
    extract_resp = await extract_tool.run(extract_call, ctx)
    assert extract_resp.content.startswith("extract_ok:https://a.com")
    assert extract_resp.is_error is False

