"""Regression tests for vendor catalog config, provider resolution, and strict API message shapes.

Live API calls are not performed here (no keys). These tests guard:
- `.clawcode.json` parses into Settings
- Model → provider inference matches each vendor class (OpenAI-compat vs native)
- OpenAI-compatible request rows include ``tool_call_id`` / ``tool_calls`` as required by
  strict gateways (e.g. DeepSeek).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from anthropic import omit

# tests/ → package root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clawcode.config.settings import AgentConfig, Provider, Settings
from clawcode.config.constants import AgentName, CONTEXT_WINDOWS
from clawcode.history.summarizer import Summarizer, SummarizerService
from clawcode.llm.agent import Agent
from clawcode.llm.openai_compat.openrouter import OpenRouterAdapter
from clawcode.llm.providers import resolve_provider_from_model
from clawcode.llm.providers.anthropic import AnthropicProvider
from clawcode.llm.providers.openai import OpenAIProvider
from clawcode.llm.base import ProviderEventType, ProviderResponse, ToolCall as LLMToolCall
from clawcode.llm.tools.advanced import _coerce_tool_params
from clawcode.llm.tools.base import ToolCall as BaseToolCall
from clawcode.message.service import Message, MessageRole, TextContent, ToolCallContent, ThinkingContent
from clawcode.config.reference_providers import provider_models_from_reference
from clawcode.tui.components.dialogs.model import ModelDialog


def _repo_clawcode_json() -> Path:
    return Path(__file__).resolve().parent.parent / ".clawcode.json"


class TestVendorCatalogJson:
    def test_clawcode_json_exists_and_validates(self) -> None:
        path = _repo_clawcode_json()
        assert path.is_file(), f"Missing {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        s = Settings.model_validate(data)
        assert len(s.providers) >= 20
        assert "openai_deepseek" in s.providers
        assert s.providers["openai_deepseek"].base_url == "https://api.deepseek.com"
        assert "deepseek-reasoner" in (s.providers["openai_deepseek"].models or [])
        assert "anthropic_shengsuanyun" in s.providers
        assert s.providers["anthropic_shengsuanyun"].base_url == "https://router.shengsuanyun.com/api"
        ssy_models = s.providers["anthropic_shengsuanyun"].models or []
        assert ssy_models
        assert any(str(m).startswith("anthropic/claude-") for m in ssy_models)

    def test_deepseek_and_qwen_context_windows(self) -> None:
        assert CONTEXT_WINDOWS.get("deepseek") == 131072
        assert CONTEXT_WINDOWS.get("qwen") == 131072
        assert CONTEXT_WINDOWS.get("MiniMax") == 204800
        assert CONTEXT_WINDOWS.get("doubao") == 131072

    def test_each_provider_entry_validates(self) -> None:
        data = json.loads(_repo_clawcode_json().read_text(encoding="utf-8"))
        for _key, p in data.get("providers", {}).items():
            Provider.model_validate(p)

    def test_agents_reference_existing_provider_keys(self) -> None:
        data = json.loads(_repo_clawcode_json().read_text(encoding="utf-8"))
        keys = set(data.get("providers", {}))
        for name, cfg in data.get("agents", {}).items():
            pk = cfg.get("provider_key")
            assert pk in keys, f"agents.{name} provider_key {pk!r} not in providers"


class TestResolveProviderFromModel:
    @pytest.mark.parametrize(
        "model,explicit_key,expect_name",
        [
            ("gpt-4o", None, "openai"),
            ("claude-3-5-sonnet-20241022", None, "anthropic"),
            ("gemini-1.5-pro", None, "gemini"),
            ("deepseek-chat", None, "openai"),
            ("deepseek-reasoner", None, "openai"),
            ("grok-2-latest", None, "xai"),
            ("openai/gpt-4o", None, "openrouter"),
            ("anthropic/claude-sonnet-4.5", None, "anthropic"),
            ("meta-llama/llama-3.3-70b-instruct", None, "openrouter"),
            ("qwen-plus", None, "openai"),
            ("qwen-long", None, "openai"),
            ("qwq-32b-preview", None, "openai"),
            ("dashscope/custom-model", None, "openai"),
            ("moonshot-v1-8k", None, "openai"),
            ("kimi-k2-turbo-preview", None, "openai"),
            ("kimi-k2.5", None, "openai"),
            ("mistral-large-latest", None, "openai"),
            ("llama-3.3-70b-versatile", None, "groq"),
            ("some-model", "groq", "groq"),
            ("some-model", "openrouter", "openrouter"),
            ("some-model", "xai", "xai"),
            ("some-model", "bedrock", "bedrock"),
            ("some-model", "copilot", "copilot"),
            ("anthropic/claude-sonnet-4.5", "anthropic_shengsuanyun", "anthropic"),
            ("glm-5", None, "openai"),
            ("MiniMax-M2.7", None, "openai"),
            ("minimax/custom-model", None, "openai"),
            ("abab6.5s-chat", None, "openai"),
            ("doubao-seed-2-0-lite-260215", None, "openai"),
            ("ep-20250212143041-abcde", None, "openai"),
            ("volcengine/custom-model", None, "openai"),
        ],
    )
    def test_inference(
        self, model: str, explicit_key: str | None, expect_name: str
    ) -> None:
        s = Settings.model_validate(
            json.loads(_repo_clawcode_json().read_text(encoding="utf-8"))
        )
        if explicit_key:
            ac = AgentConfig(model=model, provider_key=explicit_key)
        else:
            ac = AgentConfig(model=model)
        name, pkey = resolve_provider_from_model(model, s, ac)
        assert name == expect_name
        if explicit_key:
            assert pkey == explicit_key


class TestReferenceProviderModels:
    @pytest.mark.parametrize(
        "slot,expect_substr",
        [
            ("openai_deepseek", "deepseek-chat"),
            ("openai_glm", "glm-5"),
            ("openai_moonshot", "moonshot"),
            ("openai_qwen", "qwen-plus"),
            ("openai_qwen_intl", "qwen-flash"),
            ("openai_qwen_us", "qwen-long"),
            ("openai_qwen_finance", "qwen-vl-plus"),
            ("groq", "llama"),
            ("openrouter", "gpt-4o"),
            ("anthropic_shengsuanyun", "claude-sonnet"),
            ("xai", "grok"),
            ("openai_minimax", "MiniMax-M2.7"),
            ("openai_volcengine", "doubao-seed"),
        ],
    )
    def test_slot_matches_clawcode_json_catalog(self, slot: str, expect_substr: str) -> None:
        models = provider_models_from_reference(slot)
        assert models
        assert any(expect_substr in m for m in models)


class TestModelDialogBuildsList:
    def test_builds_list_when_slot_enabled(self) -> None:
        s = Settings.model_validate(
            json.loads(_repo_clawcode_json().read_text(encoding="utf-8"))
        )
        prov = dict(s.providers)
        o = prov["openai"]
        prov["openai"] = o.model_copy(update={"disabled": False, "api_key": "test-key"})
        d = ModelDialog(
            providers=prov,
            current_provider="openai",
            current_model="gpt-4o-mini",
            agents=s.agents,
        )
        labels = [m["display_name"] for m in d._model_list]
        assert any("gpt-4o" in x for x in labels)


class TestCoerceToolParams:
    def test_prefixed_empty_braces_then_json_object(self) -> None:
        """Simulates stream-concat / model quirks like ``view {}{"file_path": "README.md"}``."""
        c = BaseToolCall(
            id="x",
            name="view",
            input='{}{"file_path": "README.md"}',
        )
        p = _coerce_tool_params(c)
        assert p.get("file_path") == "README.md"

    def test_raw_empty_prefix_then_json_object(self) -> None:
        """Gateways may echo ``raw={}`` before the real JSON object."""
        c = BaseToolCall(
            id="x",
            name="view",
            input='raw={} {"file_path": "README.md"}',
        )
        assert _coerce_tool_params(c).get("file_path") == "README.md"

    def test_view_raw_empty_prefix(self) -> None:
        c = BaseToolCall(
            id="x",
            name="view",
            input='view raw={} {"file_path": "ARCHITECTURE.md"}',
        )
        assert _coerce_tool_params(c).get("file_path") == "ARCHITECTURE.md"


class TestAnthropicToolHistoryShape:
    def test_tool_rows_become_user_with_tool_result_blocks(self) -> None:
        rows = [
            {
                "role": "assistant",
                "content": "call",
                "tool_calls": [
                    {
                        "id": "tu_1",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": json.dumps({"command": "ls"}),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tu_1", "content": "out"},
        ]
        out = AnthropicProvider._openai_history_to_anthropic_messages(rows)
        assert out[0]["role"] == "assistant"


class TestOpenAICompatDeepSeekAdapter:
    def test_deepseek_injects_extra_body_thinking_when_tools_present(self) -> None:
        p = OpenAIProvider(
            model="deepseek-chat",
            api_key="test-key",
            base_url="https://api.deepseek.com",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "get_weather", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        thinking = extra.get("thinking")
        assert isinstance(thinking, dict)
        assert thinking.get("type") == "enabled"

    def test_non_deepseek_does_not_inject_extra_body(self) -> None:
        p = OpenAIProvider(
            model="gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        assert "extra_body" not in params

    def test_agent_converts_thinking_to_reasoning_content_for_deepseek(self) -> None:
        p = OpenAIProvider(
            model="deepseek-chat",
            api_key="test-key",
            base_url="https://api.deepseek.com",
        )
        a = Agent(
            provider=p,
            tools=[],
            message_service=object(),  # not used by _convert_history_to_provider
            session_service=object(),  # not used by _convert_history_to_provider
            system_prompt="sys",
            max_iterations=1,
        )
        history = [
            Message(
                id="m1",
                session_id="s",
                role=MessageRole.ASSISTANT,
                parts=[
                    ThinkingContent(content="reason"),
                    TextContent(content="answer"),
                ],
            )
        ]
        rows = a._convert_history_to_provider(history, tools_present=True)
        assert rows[0]["role"] == "system"
        assert rows[1]["role"] == "assistant"
        assert rows[1].get("reasoning_content") == "reason"


class TestOpenAICompatGLMAdapter:
    def test_glm_injects_thinking_and_preserved_thinking_when_tools_present(self) -> None:
        p = OpenAIProvider(
            model="glm-5",
            api_key="test-key",
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        thinking = extra.get("thinking")
        assert isinstance(thinking, dict)
        assert thinking.get("type") == "enabled"
        assert thinking.get("clear_thinking") is False

    def test_glm_injects_tool_stream_when_streaming_with_tools(self) -> None:
        p = OpenAIProvider(
            model="glm-5",
            api_key="test-key",
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=True,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        assert extra.get("tool_stream") is True

    def test_non_glm_does_not_inject_tool_stream(self) -> None:
        p = OpenAIProvider(
            model="gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=True,
        )
        extra = params.get("extra_body")
        assert extra is None


class TestOpenAICompatMoonshotAdapter:
    def test_moonshot_migrates_max_tokens_to_max_completion_tokens(self) -> None:
        p = OpenAIProvider(
            model="kimi-k2-turbo-preview",
            api_key="test-key",
            base_url="https://api.moonshot.cn/v1",
            max_tokens=256,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            stream=False,
        )
        assert params.get("max_completion_tokens") == 256
        assert "max_tokens" not in params

    def test_kimi_k25_with_tools_sets_thinking_enabled(self) -> None:
        p = OpenAIProvider(
            model="kimi-k2.5",
            api_key="test-key",
            base_url="https://api.moonshot.cn/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        thinking = extra.get("thinking")
        assert isinstance(thinking, dict)
        assert thinking.get("type") == "enabled"
        assert params.get("max_completion_tokens") == 123
        assert "max_tokens" not in params

    def test_non_moonshot_openai_keeps_max_tokens(self) -> None:
        p = OpenAIProvider(
            model="gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            max_tokens=128,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            stream=False,
        )
        assert params.get("max_tokens") == 128
        assert "max_completion_tokens" not in params
        assert "extra_body" not in params

    def test_agent_converts_thinking_to_reasoning_content_for_moonshot(self) -> None:
        p = OpenAIProvider(
            model="kimi-k2.5",
            api_key="test-key",
            base_url="https://api.moonshot.cn/v1",
        )
        a = Agent(
            provider=p,
            tools=[],
            message_service=object(),  # not used by _convert_history_to_provider
            session_service=object(),  # not used by _convert_history_to_provider
            system_prompt="sys",
            max_iterations=1,
        )
        history = [
            Message(
                id="m1",
                session_id="s",
                role=MessageRole.ASSISTANT,
                parts=[
                    ThinkingContent(content="reason"),
                    TextContent(content="answer"),
                ],
            )
        ]
        rows = a._convert_history_to_provider(history, tools_present=True)
        assert rows[0]["role"] == "system"
        assert rows[1]["role"] == "assistant"
        assert rows[1].get("reasoning_content") == "reason"


class TestOpenAICompatVolcengineAdapter:
    def test_volcengine_injects_thinking_when_tools_present(self) -> None:
        p = OpenAIProvider(
            model="doubao-seed-2-0-lite-260215",
            api_key="test-key",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        thinking = extra.get("thinking")
        assert isinstance(thinking, dict)
        assert thinking.get("type") == "enabled"

    def test_volcengine_without_tools_does_not_force_thinking(self) -> None:
        p = OpenAIProvider(
            model="doubao-seed-2-0-lite-260215",
            api_key="test-key",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            stream=False,
        )
        assert "extra_body" not in params

    def test_non_volcengine_does_not_inject_volcengine_fields(self) -> None:
        p = OpenAIProvider(
            model="gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        if isinstance(extra, dict):
            thinking = extra.get("thinking")
            if isinstance(thinking, dict):
                assert thinking.get("type") != "enabled"

    def test_volcengine_ep_prefix_matches_custom_proxy_base_url_with_tools(self) -> None:
        """Endpoint-id models via reverse proxy: host is not volces.com but ep- still selects adapter."""
        p = OpenAIProvider(
            model="ep-20250212143041-abcde",
            api_key="test-key",
            base_url="https://gateway.example.org/openai/v1",
            max_tokens=64,
        )
        assert p.openai_compat_adapter.vendor == "volcengine"
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        thinking = extra.get("thinking")
        assert isinstance(thinking, dict)
        assert thinking.get("type") == "enabled"

    def test_agent_converts_thinking_to_reasoning_content_for_volcengine(self) -> None:
        p = OpenAIProvider(
            model="doubao-seed-2-0-lite-260215",
            api_key="test-key",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )
        a = Agent(
            provider=p,
            tools=[],
            message_service=object(),  # not used by _convert_history_to_provider
            session_service=object(),  # not used by _convert_history_to_provider
            system_prompt="sys",
            max_iterations=1,
        )
        history = [
            Message(
                id="m1",
                session_id="s",
                role=MessageRole.ASSISTANT,
                parts=[
                    ThinkingContent(content="reason"),
                    TextContent(content="answer"),
                ],
            )
        ]
        rows = a._convert_history_to_provider(history, tools_present=True)
        assert rows[0]["role"] == "system"
        assert rows[1]["role"] == "assistant"
        assert rows[1].get("reasoning_content") == "reason"


class TestOpenAICompatQwenAdapter:
    def test_qwen_injects_enable_thinking_when_tools_present(self) -> None:
        p = OpenAIProvider(
            model="qwen-plus",
            api_key="test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        assert extra.get("enable_thinking") is True

    def test_qwen_without_tools_does_not_force_enable_thinking(self) -> None:
        p = OpenAIProvider(
            model="qwen-plus",
            api_key="test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            stream=False,
        )
        assert "extra_body" not in params

    def test_non_qwen_does_not_inject_qwen_fields(self) -> None:
        p = OpenAIProvider(
            model="gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        if isinstance(extra, dict):
            assert extra.get("enable_thinking") is not True

    def test_qwen_model_prefix_matches_custom_proxy_base_url(self) -> None:
        p = OpenAIProvider(
            model="qwen-plus",
            api_key="test-key",
            base_url="https://gateway.example.org/openai/v1",
            max_tokens=64,
        )
        assert p.openai_compat_adapter.vendor == "qwen"
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        assert extra.get("enable_thinking") is True

    def test_agent_converts_thinking_to_reasoning_content_for_qwen(self) -> None:
        p = OpenAIProvider(
            model="qwen-plus",
            api_key="test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        a = Agent(
            provider=p,
            tools=[],
            message_service=object(),  # not used by _convert_history_to_provider
            session_service=object(),  # not used by _convert_history_to_provider
            system_prompt="sys",
            max_iterations=1,
        )
        history = [
            Message(
                id="m1",
                session_id="s",
                role=MessageRole.ASSISTANT,
                parts=[
                    ThinkingContent(content="reason"),
                    TextContent(content="answer"),
                ],
            )
        ]
        rows = a._convert_history_to_provider(history, tools_present=True)
        assert rows[0]["role"] == "system"
        assert rows[1]["role"] == "assistant"
        assert rows[1].get("reasoning_content") == "reason"


class TestOpenAICompatMiniMaxAdapter:
    def test_minimax_injects_reasoning_split_when_tools_present(self) -> None:
        p = OpenAIProvider(
            model="MiniMax-M2.7",
            api_key="test-key",
            base_url="https://api.minimaxi.com/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        assert extra.get("reasoning_split") is True

    def test_minimax_without_tools_does_not_force_reasoning_split(self) -> None:
        p = OpenAIProvider(
            model="MiniMax-M2.7",
            api_key="test-key",
            base_url="https://api.minimaxi.com/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            stream=False,
        )
        assert "extra_body" not in params

    def test_non_minimax_does_not_inject_minimax_fields(self) -> None:
        p = OpenAIProvider(
            model="gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
            max_tokens=123,
        )
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        if isinstance(extra, dict):
            assert extra.get("reasoning_split") is not True

    def test_minimax_model_prefix_matches_custom_proxy_base_url(self) -> None:
        p = OpenAIProvider(
            model="MiniMax-M2.7",
            api_key="test-key",
            base_url="https://gateway.example.org/openai/v1",
            max_tokens=64,
        )
        assert p.openai_compat_adapter.vendor == "minimax"
        params = p._build_request_params(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "t", "description": "", "parameters": {}}],
            stream=False,
        )
        extra = params.get("extra_body")
        assert isinstance(extra, dict)
        assert extra.get("reasoning_split") is True

    def test_agent_converts_thinking_to_reasoning_content_for_minimax(self) -> None:
        p = OpenAIProvider(
            model="MiniMax-M2.7",
            api_key="test-key",
            base_url="https://api.minimaxi.com/v1",
        )
        a = Agent(
            provider=p,
            tools=[],
            message_service=object(),  # not used by _convert_history_to_provider
            session_service=object(),  # not used by _convert_history_to_provider
            system_prompt="sys",
            max_iterations=1,
        )
        history = [
            Message(
                id="m1",
                session_id="s",
                role=MessageRole.ASSISTANT,
                parts=[
                    ThinkingContent(content="reason"),
                    TextContent(content="answer"),
                ],
            )
        ]
        rows = a._convert_history_to_provider(history, tools_present=True)
        assert rows[0]["role"] == "system"
        assert rows[1]["role"] == "assistant"
        assert rows[1].get("reasoning_content") == "reason"

    @pytest.mark.asyncio
    async def test_send_messages_falls_back_to_reasoning_details(self) -> None:
        class _FakeCompletions:
            async def create(self, **kwargs: Any) -> Any:  # noqa: ARG002
                msg = SimpleNamespace(
                    content="",
                    reasoning_content=None,
                    reasoning_details=[{"text": "think-1"}, {"text": "think-2"}],
                    tool_calls=[],
                )
                choice = SimpleNamespace(message=msg, finish_reason="stop")
                usage = SimpleNamespace(
                    prompt_tokens=1,
                    completion_tokens=2,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                )
                return SimpleNamespace(choices=[choice], usage=usage)

        p = OpenAIProvider.__new__(OpenAIProvider)
        p._model = "MiniMax-M2.7"
        p._max_tokens = 64
        p._reasoning_effort = "medium"
        p._caching_enabled = False
        p._base_url = "https://api.minimaxi.com/v1"
        p._compat_adapter = None
        p._client = SimpleNamespace(
            chat=SimpleNamespace(completions=_FakeCompletions())
        )

        out = await p.send_messages(messages=[{"role": "user", "content": "hi"}], tools=None)
        assert out.thinking == "think-1think-2"
        assert out.content == "think-1think-2"

    @pytest.mark.asyncio
    async def test_stream_response_concatenates_reasoning_details_chunks(self) -> None:
        """Lock streaming fallback: each delta.reasoning_details slice appends to thinking."""

        async def _chunk_stream() -> Any:
            parts = [
                [{"text": "alpha"}],
                [{"text": "beta"}, {"text": "gamma"}],
                [{"text": "delta"}],
            ]
            for details in parts:
                delta = SimpleNamespace(
                    content=None,
                    reasoning_content=None,
                    tool_calls=None,
                    reasoning_details=details,
                )
                yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)
            yield SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=3,
                    completion_tokens=4,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
            )

        class _FakeCompletions:
            async def create(self, **kwargs: Any) -> Any:  # noqa: ARG002
                return _chunk_stream()

        p = OpenAIProvider.__new__(OpenAIProvider)
        p._model = "MiniMax-M2.7"
        p._max_tokens = 64
        p._reasoning_effort = "medium"
        p._caching_enabled = False
        p._base_url = "https://api.minimaxi.com/v1"
        p._compat_adapter = None
        p._client = SimpleNamespace(
            chat=SimpleNamespace(completions=_FakeCompletions())
        )

        events: list[Any] = []
        async for ev in p.stream_response(messages=[{"role": "user", "content": "hi"}], tools=None):
            events.append(ev)

        thinking_deltas = [e.thinking for e in events if e.type == ProviderEventType.THINKING_DELTA]
        assert thinking_deltas == ["alpha", "betagamma", "delta"]

        complete = next(e for e in events if e.type == ProviderEventType.COMPLETE)
        assert complete.response is not None
        assert complete.response.thinking == "alphabetagammadelta"
        assert complete.response.content == ""


class TestOpenAICompatOpenRouterAdapter:
    def test_openrouter_matches_by_base_url(self) -> None:
        p = OpenAIProvider(
            model="openai/gpt-4o",
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            max_tokens=128,
        )
        assert p.openai_compat_adapter.vendor == "openrouter"

    def test_openrouter_moves_vendor_fields_to_extra_body(self) -> None:
        adapter = OpenRouterAdapter()
        params = {
            "model": "openai/gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "models": ["anthropic/claude-3.5-sonnet"],
            "provider": {"sort": "price"},
            "parallel_tool_calls": False,
        }
        patched = adapter.patch_request_params(params, tools_present=True, stream=False)
        assert "models" not in patched
        assert "provider" not in patched
        assert "parallel_tool_calls" not in patched
        extra = patched.get("extra_body")
        assert isinstance(extra, dict)
        assert extra.get("models") == ["anthropic/claude-3.5-sonnet"]
        assert extra.get("provider") == {"sort": "price"}
        assert extra.get("parallel_tool_calls") is False
        assert extra.get("include_reasoning") is True

    @pytest.mark.asyncio
    async def test_send_messages_falls_back_to_reasoning_field(self) -> None:
        class _FakeCompletions:
            async def create(self, **kwargs: Any) -> Any:  # noqa: ARG002
                msg = SimpleNamespace(
                    content="",
                    reasoning_content=None,
                    reasoning_details=None,
                    reasoning="or-reason",
                    tool_calls=[],
                )
                choice = SimpleNamespace(message=msg, finish_reason="stop")
                usage = SimpleNamespace(
                    prompt_tokens=1,
                    completion_tokens=2,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                )
                return SimpleNamespace(choices=[choice], usage=usage)

        p = OpenAIProvider.__new__(OpenAIProvider)
        p._model = "openai/gpt-4o"
        p._max_tokens = 64
        p._reasoning_effort = "medium"
        p._caching_enabled = False
        p._base_url = "https://openrouter.ai/api/v1"
        p._compat_adapter = None
        p._client = SimpleNamespace(
            chat=SimpleNamespace(completions=_FakeCompletions())
        )

        out = await p.send_messages(messages=[{"role": "user", "content": "hi"}], tools=None)
        assert out.thinking == "or-reason"
        assert out.content == "or-reason"

    @pytest.mark.asyncio
    async def test_stream_response_concatenates_reasoning_chunks(self) -> None:
        async def _chunk_stream() -> Any:
            for part in ["r1", "r2", "r3"]:
                delta = SimpleNamespace(
                    content=None,
                    reasoning_content=None,
                    reasoning_details=None,
                    reasoning=part,
                    tool_calls=None,
                )
                yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=None)
            yield SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=2,
                    completion_tokens=3,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
            )

        class _FakeCompletions:
            async def create(self, **kwargs: Any) -> Any:  # noqa: ARG002
                return _chunk_stream()

        p = OpenAIProvider.__new__(OpenAIProvider)
        p._model = "openai/gpt-4o"
        p._max_tokens = 64
        p._reasoning_effort = "medium"
        p._caching_enabled = False
        p._base_url = "https://openrouter.ai/api/v1"
        p._compat_adapter = None
        p._client = SimpleNamespace(
            chat=SimpleNamespace(completions=_FakeCompletions())
        )

        events: list[Any] = []
        async for ev in p.stream_response(messages=[{"role": "user", "content": "hi"}], tools=None):
            events.append(ev)

        thinking_deltas = [e.thinking for e in events if e.type == ProviderEventType.THINKING_DELTA]
        assert thinking_deltas == ["r1", "r2", "r3"]
        complete = next(e for e in events if e.type == ProviderEventType.COMPLETE)
        assert complete.response is not None
        assert complete.response.thinking == "r1r2r3"
        assert complete.response.content == ""

    @pytest.mark.asyncio
    async def test_stream_interleaved_reasoning_and_tool_calls_openrouter_style(self) -> None:
        """Mimic OpenRouter-style SSE: reasoning deltas interleaved with streaming tool_calls."""

        def _delta(**kwargs: Any) -> Any:
            return SimpleNamespace(
                content=kwargs.get("content"),
                reasoning_content=kwargs.get("reasoning_content"),
                reasoning_details=kwargs.get("reasoning_details"),
                reasoning=kwargs.get("reasoning"),
                tool_calls=kwargs.get("tool_calls"),
            )

        def _tc(
            index: int,
            call_id: str | None = None,
            name: str = "",
            arguments: str = "",
        ) -> Any:
            return SimpleNamespace(
                index=index,
                id=call_id,
                function=SimpleNamespace(name=name, arguments=arguments),
            )

        async def _chunk_stream() -> Any:
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=_delta(reasoning="I'll use search. "))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=_delta(
                            tool_calls=[
                                _tc(0, "call_or_abc", "search_gutenberg_books", ""),
                            ]
                        )
                    )
                ],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=_delta(reasoning="Building JSON args. "))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=_delta(
                            tool_calls=[_tc(0, None, "", '{"search_ter')]
                        )
                    )
                ],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=_delta(reasoning=[{"text": "…"}, {"text": "done."}])
                    )
                ],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=_delta(tool_calls=[_tc(0, None, "", 'ms":["Joyce"]}')])
                    )
                ],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=10,
                    completion_tokens=20,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=0),
                ),
            )

        class _FakeCompletions:
            async def create(self, **kwargs: Any) -> Any:  # noqa: ARG002
                return _chunk_stream()

        p = OpenAIProvider.__new__(OpenAIProvider)
        p._model = "anthropic/claude-sonnet-4.5"
        p._max_tokens = 64
        p._reasoning_effort = "medium"
        p._caching_enabled = False
        p._base_url = "https://openrouter.ai/api/v1"
        p._compat_adapter = None
        p._client = SimpleNamespace(
            chat=SimpleNamespace(completions=_FakeCompletions())
        )

        tools = [
            {
                "name": "search_gutenberg_books",
                "description": "Search books",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

        events: list[Any] = []
        async for ev in p.stream_response(
            messages=[{"role": "user", "content": "Joyce books?"}],
            tools=tools,
        ):
            events.append(ev)

        types = [e.type for e in events]
        assert types.count(ProviderEventType.THINKING_DELTA) == 3
        assert types.count(ProviderEventType.TOOL_USE_START) == 1
        assert types.count(ProviderEventType.TOOL_USE_STOP) == 1
        assert types.count(ProviderEventType.COMPLETE) == 1

        thinking_parts = [e.thinking for e in events if e.type == ProviderEventType.THINKING_DELTA]
        assert thinking_parts == [
            "I'll use search. ",
            "Building JSON args. ",
            "…done.",
        ]

        start_ev = next(e for e in events if e.type == ProviderEventType.TOOL_USE_START)
        assert start_ev.tool_call is not None
        assert start_ev.tool_call.id == "call_or_abc"

        complete = next(e for e in events if e.type == ProviderEventType.COMPLETE)
        assert complete.response is not None
        assert complete.response.thinking == "".join(thinking_parts)
        assert complete.response.content == ""
        assert len(complete.response.tool_calls) == 1
        tc0 = complete.response.tool_calls[0]
        assert isinstance(tc0, LLMToolCall)
        assert tc0.id == "call_or_abc"
        assert tc0.name == "search_gutenberg_books"
        assert tc0.input == {"search_terms": ["Joyce"]}


class TestAnthropicBlockDeltaParsing:
    def test_text_delta_typed(self) -> None:
        class D:
            type = "text_delta"
            text = "hi"

        assert AnthropicProvider._text_from_block_delta(D()) == "hi"

    def test_text_proxy_without_type_field(self) -> None:
        class D:
            text = "hello"

        assert AnthropicProvider._text_from_block_delta(D()) == "hello"

    def test_skips_partial_json(self) -> None:
        class D:
            text = "x"
            partial_json = "{"

        assert AnthropicProvider._text_from_block_delta(D()) is None


class TestAnthropicSystemMessageSplit:
    """Messages API forbids role=system inside ``messages`` (strict proxies enforce it)."""

    def test_strips_system_role_and_merges_into_param(self) -> None:
        p = AnthropicProvider(
            model="anthropic/claude-sonnet-4.6",
            api_key="sk-test",
            system_message="from_provider",
        )
        rows = [
            {"role": "system", "content": "from_agent"},
            {"role": "user", "content": "hi"},
        ]
        core, inline = AnthropicProvider._split_system_from_messages(rows)
        assert core == [{"role": "user", "content": "hi"}]
        assert inline == "from_agent"
        sys_val = p._system_request_value(inline)
        assert sys_val != omit
        assert isinstance(sys_val, list) and len(sys_val) == 1
        assert sys_val[0].get("type") == "text"
        assert "from_agent" in (sys_val[0].get("text") or "")
        assert "from_provider" in (sys_val[0].get("text") or "")

    def test_omit_when_no_system_anywhere(self) -> None:
        p = AnthropicProvider(model="claude-3-5-haiku-20241022", api_key="sk-test")
        assert p._system_request_value("") is omit

    def test_system_is_list_without_caching(self) -> None:
        p = AnthropicProvider(
            model="anthropic/claude-sonnet-4.6",
            api_key="sk-test",
            system_message="only_provider",
            caching_enabled=False,
        )
        v = p._system_request_value("")
        assert isinstance(v, list) and len(v) == 1
        assert v[0] == {"type": "text", "text": "only_provider"}


class TestAnthropicToolSchemaConversion:
    """Bedrock-style gateways require ``input_schema`` on each tool (not ``parameters``)."""

    def test_toolinfo_shape_maps_parameters_to_input_schema(self) -> None:
        p = AnthropicProvider(model="anthropic/claude-sonnet-4.6", api_key="sk-test")
        raw = {
            "name": "bash",
            "description": "run shell",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            "required": ["command"],
        }
        out = p._convert_tool(raw)
        assert out["name"] == "bash"
        assert "input_schema" in out
        assert out["input_schema"]["type"] == "object"
        assert "command" in out["input_schema"]["properties"]
        assert "parameters" not in out

    def test_openai_function_shape_still_works(self) -> None:
        p = AnthropicProvider(model="claude-3-5-haiku-20241022", api_key="sk-test")
        out = p._convert_tool(
            {
                "type": "function",
                "function": {
                    "name": "x",
                    "description": "d",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        )
        assert out["name"] == "x"
        assert out["input_schema"]["type"] == "object"


class TestAnthropicStrictEmptyText:
    """Bedrock-backed proxies reject whitespace-only text blocks."""

    def test_whitespace_user_string_becomes_placeholder(self) -> None:
        p = AnthropicProvider(
            model="anthropic/claude-sonnet-4.6",
            api_key="sk-test",
            caching_enabled=False,
        )
        out = p._convert_messages([{"role": "user", "content": "  \n\t  "}])
        assert out and out[0]["role"] == "user"
        assert out[0]["content"] == "."
        assert str(out[0]["content"]).strip() == out[0]["content"]

    def test_empty_tool_result_body_becomes_placeholder(self) -> None:
        p = AnthropicProvider(
            model="anthropic/claude-sonnet-4.6",
            api_key="sk-test",
            caching_enabled=False,
        )
        rows = [
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [
                    {
                        "id": "tu_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tu_1", "content": "   "},
        ]
        out = p._convert_messages(rows)
        assert out[-1]["role"] == "user"
        blk = out[-1]["content"][0]
        assert blk["type"] == "tool_result"
        assert blk["content"] == "."
        assert str(blk["content"]).strip() == blk["content"]


class TestOpenAIMessageConversion:
    @staticmethod
    def _bare_openai_provider() -> OpenAIProvider:
        p = OpenAIProvider.__new__(OpenAIProvider)
        p._model = "deepseek-chat"
        p._max_tokens = 8192
        p._reasoning_effort = "medium"
        p._caching_enabled = False
        return p

    def test_assistant_tool_calls_then_tool_rows(self) -> None:
        prov = self._bare_openai_provider()
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "call",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        ]
        out = prov._convert_messages(msgs)
        assert out[-2]["role"] == "assistant" and out[-2].get("tool_calls")
        assert out[-1]["role"] == "tool"
        assert out[-1].get("tool_call_id") == "call_1"

    def test_explicit_tool_row_has_tool_call_id(self) -> None:
        prov = self._bare_openai_provider()
        out = prov._convert_messages(
            [
                {"role": "user", "content": "x"},
                {"role": "tool", "tool_call_id": "c1", "content": "y"},
            ]
        )
        assert out[-1]["role"] == "tool"
        assert "tool_call_id" in out[-1]

    def test_suppress_final_content_for_tool_echo_json(self) -> None:
        noisy = '{"file_path":"a.py","content":"print(1)","arguments":{"x":1}}'
        assert OpenAIProvider._should_suppress_final_content(noisy) is True

    def test_not_suppress_normal_short_text(self) -> None:
        assert OpenAIProvider._should_suppress_final_content("Done. Tool result prepared.") is False


class TestToolCallContentDataclass:
    def test_construct_without_explicit_type(self) -> None:
        """Regression: Agent appends ToolCallContent(id=..., name=..., input=...)."""
        t = ToolCallContent(id="call_1", name="bash", input={})
        assert t.type == "tool_use"
        assert t.name == "bash"


class TestNormalizeToolSequences:
    def test_pads_missing_tool_rows(self) -> None:
        from clawcode.llm.agent import _normalize_tool_message_sequences_for_api

        msgs = [
            {"role": "system", "content": "s"},
            {
                "role": "assistant",
                "content": "x",
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "bash", "arguments": "{}"}},
                    {"id": "b", "type": "function", "function": {"name": "bash", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "out-a"},
        ]
        _normalize_tool_message_sequences_for_api(msgs)
        assert [m["role"] for m in msgs] == ["system", "assistant", "tool", "tool"]
        assert msgs[2]["tool_call_id"] == "a"
        assert msgs[3]["tool_call_id"] == "b"
        assert "missing" in msgs[3]["content"].lower()

    def test_reorders_to_match_tool_calls(self) -> None:
        from clawcode.llm.agent import _normalize_tool_message_sequences_for_api

        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "first", "type": "function", "function": {"name": "x", "arguments": "{}"}},
                    {"id": "second", "type": "function", "function": {"name": "y", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "second", "content": "2"},
            {"role": "tool", "tool_call_id": "first", "content": "1"},
        ]
        _normalize_tool_message_sequences_for_api(msgs)
        assert msgs[1]["tool_call_id"] == "first"
        assert msgs[2]["tool_call_id"] == "second"
        assert msgs[1]["content"] == "1"
        assert msgs[2]["content"] == "2"


class TestAgentHistoryStrictToolChain:
    def test_tool_json_backfills_preceding_assistant(self) -> None:
        ag = Agent.__new__(Agent)
        ag._system_prompt = "SYS"

        u = Message(id="1", session_id="s", role=MessageRole.USER, parts=[])
        u.content = "hello"
        a = Message(id="2", session_id="s", role=MessageRole.ASSISTANT, parts=[])
        a.content = "I'll run a command"
        t = Message(id="3", session_id="s", role=MessageRole.TOOL, parts=[])
        t.content = json.dumps(
            [
                {
                    "tool_call_id": "call_abc",
                    "name": "bash",
                    "arguments": "{}",
                    "content": "listed",
                    "is_error": False,
                }
            ]
        )

        rows = Agent._convert_history_to_provider(ag, [u, a, t])
        assert rows[0]["role"] == "system"
        # Last three: assistant (patched), tool
        assert rows[-2]["role"] == "assistant"
        assert rows[-2].get("tool_calls")
        assert rows[-2]["tool_calls"][0]["id"] == "call_abc"
        assert rows[-1]["role"] == "tool"
        assert rows[-1]["tool_call_id"] == "call_abc"

    def test_tool_round_assistant_does_not_replay_thinking(self) -> None:
        ag = Agent.__new__(Agent)
        ag._system_prompt = "SYS"

        a = Message(id="2", session_id="s", role=MessageRole.ASSISTANT, parts=[])
        a.parts = [
            TextContent(content="I'll call write."),
            ToolCallContent(id="call_x", name="write", input={"file_path": "x.py"}),
        ]
        a.thinking = "very long hidden reasoning"

        rows = Agent._convert_history_to_provider(ag, [a])
        assistant_rows = [r for r in rows if r.get("role") == "assistant" and r.get("tool_calls")]
        assert assistant_rows
        assert "[Thinking]" not in (assistant_rows[-1].get("content") or "")


class TestSummarizerProviderKeyRespected:
    @pytest.mark.asyncio
    async def test_summarizer_service_uses_provider_key_slot(self, monkeypatch: Any) -> None:
        """Regression: summarizer must use agents.summarizer.provider_key slot (base_url/timeout included)."""
        s = Settings()
        s.providers["openai_custom"] = Provider(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            disabled=False,
            timeout=9,
        )
        s.agents[AgentName.SUMMARIZER].model = "deepseek-reasoner"
        s.agents[AgentName.SUMMARIZER].provider_key = "openai_custom"

        msg_svc = SimpleNamespace()
        sess_svc = SimpleNamespace()

        captured: dict[str, Any] = {}

        def _fake_create_provider(
            provider_name: str, model_id: str, api_key: str | None = None, **kwargs: Any
        ) -> Any:
            captured["provider_name"] = provider_name
            captured["model_id"] = model_id
            captured["api_key"] = api_key
            captured.update(kwargs)
            return SimpleNamespace(model=model_id, max_tokens=4096, send_messages=None)

        monkeypatch.setattr(
            "clawcode.llm.providers.create_provider", _fake_create_provider, raising=True
        )

        svc = SummarizerService(s, msg_svc, sess_svc)
        _ = svc._get_provider()

        assert captured["provider_name"] == "openai"
        assert captured["model_id"] == "deepseek-reasoner"
        assert captured["api_key"] == "sk-test"
        assert captured["base_url"] == "https://example.invalid/v1"
        assert captured["timeout"] == 9


class TestSummarizerResponseFallbacks:
    def test_response_text_prefers_content_over_thinking(self) -> None:
        r = ProviderResponse(content="visible", thinking="hidden")
        assert Summarizer._response_text(r) == "visible"

    def test_response_text_falls_back_to_thinking_when_content_blank(self) -> None:
        r = ProviderResponse(content="   ", thinking="only-thinking")
        assert Summarizer._response_text(r) == "only-thinking"
