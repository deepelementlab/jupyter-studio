"""Integration tests against Anthropic's real claude-plugins-official marketplace.

Requires: git on PATH, network, and env ``CLAWCODE_TEST_OFFICIAL_PLUGINS=1``.

Run::
    set CLAWCODE_TEST_OFFICIAL_PLUGINS=1   # Windows cmd
    pytest tests/test_plugin_official_integration.py -v --tb=short

Uses the real catalog at
https://github.com/anthropics/claude-plugins-official
and installs real bundled plugins (``./plugins/...`` entries — no extra git clones),
then exercises the same code path as TUI ``/plugin`` via ``dispatch_slash``.

Common examples (Anthropic catalog names):

- ``agent-sdk-dev`` — Agent SDK 工作流
- ``code-review`` — 代码审查
- ``claude-code-setup`` — 环境/上手
- ``hookify`` — 钩子与自动化
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from clawcode.config.settings import PluginConfig, Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.ops import install_plugin_from_marketplace, marketplace_add
from clawcode.plugin.slash import dispatch_slash

OFFICIAL_REPO = "https://github.com/anthropics/claude-plugins-official.git"
OFFICIAL_MARKETPLACE_NAME = "claude-plugins-official"
SAMPLE_PLUGIN = "agent-sdk-dev"

# Real marketplace entries; all use ``source: ./plugins/<name>`` in the same repo (one shallow clone).
COMMON_OFFICIAL_PLUGINS = (
    "agent-sdk-dev",
    "code-review",
    "claude-code-setup",
    "hookify",
)


def _git_available() -> bool:
    return shutil.which("git") is not None


official_plugins_enabled = os.environ.get("CLAWCODE_TEST_OFFICIAL_PLUGINS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

pytestmark = pytest.mark.skipif(
    not official_plugins_enabled,
    reason="Set CLAWCODE_TEST_OFFICIAL_PLUGINS=1 to run (needs git + network).",
)


@pytest.fixture
def cloned_official(tmp_path: Path) -> Path:
    dest = tmp_path / "claude-plugins-official"
    subprocess.run(
        ["git", "clone", "--depth", "1", OFFICIAL_REPO, str(dest)],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    mp = dest / ".claude-plugin" / "marketplace.json"
    assert mp.is_file(), "cloned repo missing marketplace.json"
    return dest


def test_official_marketplace_add_install_and_plugin_slash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cloned_official: Path,
) -> None:
    if not _git_available():
        pytest.skip("git not on PATH")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    s = Settings()
    s.working_directory = str(tmp_path)
    s.plugins = PluginConfig(enabled=True, data_root_mode="clawcode")

    mname, root = marketplace_add(s, str(cloned_official))
    assert mname == OFFICIAL_MARKETPLACE_NAME
    assert root.resolve() == cloned_official.resolve()

    d_mp = dispatch_slash("/plugin marketplace list", s, None)
    assert d_mp is not None and d_mp.consume_without_llm
    assert OFFICIAL_MARKETPLACE_NAME in (d_mp.plugin_reply or "")

    install_plugin_from_marketplace(s, SAMPLE_PLUGIN, OFFICIAL_MARKETPLACE_NAME)

    pm = PluginManager(s)
    pm.discover_and_load()
    loaded = {p.name for p in pm.plugins}
    assert SAMPLE_PLUGIN in loaded, f"expected {SAMPLE_PLUGIN} in {loaded}"

    d_list = dispatch_slash("/plugin list", s, pm)
    assert d_list is not None and d_list.consume_without_llm
    assert SAMPLE_PLUGIN in (d_list.plugin_reply or "")

    d_un = dispatch_slash(f"/plugin uninstall {SAMPLE_PLUGIN}", s, pm)
    assert d_un is not None and d_un.consume_without_llm
    assert "Uninstalled" in (d_un.plugin_reply or "")

    pm.discover_and_load()
    assert SAMPLE_PLUGIN not in {p.name for p in pm.plugins}


def test_official_multi_common_plugins_plugin_slash_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cloned_official: Path,
) -> None:
    """Install several popular official plugins; exercise /plugin list, disable, enable, install, uninstall."""
    if not _git_available():
        pytest.skip("git not on PATH")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    s = Settings()
    s.working_directory = str(tmp_path)
    s.plugins = PluginConfig(enabled=True, data_root_mode="clawcode")

    marketplace_add(s, str(cloned_official))

    for pname in COMMON_OFFICIAL_PLUGINS:
        install_plugin_from_marketplace(s, pname, OFFICIAL_MARKETPLACE_NAME)

    pm = PluginManager(s)
    pm.discover_and_load()
    loaded = {p.name for p in pm.plugins}
    for pname in COMMON_OFFICIAL_PLUGINS:
        assert pname in loaded, f"missing {pname}, have {loaded}"

    d_list = dispatch_slash("/plugin list", s, pm)
    assert d_list is not None and d_list.consume_without_llm
    reply = d_list.plugin_reply or ""
    for pname in COMMON_OFFICIAL_PLUGINS:
        assert pname in reply, f"/plugin list should mention {pname}"

    d_dis = dispatch_slash("/plugin disable code-review", s, pm)
    assert d_dis is not None and d_dis.consume_without_llm and "Disabled" in (d_dis.plugin_reply or "")

    pm.discover_and_load()
    by_name = {p.name: p for p in pm.plugins}
    assert by_name["code-review"].enabled is False

    d_en = dispatch_slash("/plugin enable code-review", s, pm)
    assert d_en is not None and d_en.consume_without_llm and "Enabled" in (d_en.plugin_reply or "")

    pm.discover_and_load()
    cr = next(p for p in pm.plugins if p.name == "code-review")
    assert cr.enabled is True

    # Slash-driven uninstall + reinstall one plugin (validates /plugin install name@marketplace).
    d_un = dispatch_slash("/plugin uninstall hookify", s, pm)
    assert d_un is not None and "Uninstalled" in (d_un.plugin_reply or "")

    pm.discover_and_load()
    assert "hookify" not in {p.name for p in pm.plugins}

    d_in = dispatch_slash(
        f"/plugin install hookify@{OFFICIAL_MARKETPLACE_NAME}",
        s,
        pm,
    )
    assert d_in is not None and d_in.consume_without_llm and "Installed" in (d_in.plugin_reply or "")

    pm.discover_and_load()
    assert "hookify" in {p.name for p in pm.plugins}

    # Cleanup cache + state for this home root.
    for pname in COMMON_OFFICIAL_PLUGINS:
        dispatch_slash(f"/plugin uninstall {pname}", s, pm)
    pm.discover_and_load()
    remaining = {p.name for p in pm.plugins}
    assert not remaining.intersection(set(COMMON_OFFICIAL_PLUGINS)), remaining
