"""Tests for plugin paths, marketplace parsing, and slash dispatch."""

from __future__ import annotations

import json
from pathlib import Path

from clawcode.config.settings import PluginConfig, Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.marketplace_catalog import load_marketplace_file, plugin_root_prefix
from clawcode.plugin.paths import resolve_plugin_paths
from clawcode.plugin.slash import dispatch_slash, plugin_slash_help


def test_resolve_plugin_paths_default_project_claw(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    s = Settings()
    s.plugins = PluginConfig(data_root_mode="clawcode")
    s.working_directory = str(tmp_path / "proj")
    p = resolve_plugin_paths(s)
    assert p.data_root == (tmp_path / "proj" / ".claw").resolve()
    assert p.cache_dir == p.user_plugins_dir / "cache"
    assert p.state_file == p.data_root / "plugin-state.json"


def test_resolve_plugin_paths_custom(tmp_path: Path) -> None:
    root = tmp_path / "pdata"
    s = Settings()
    s.plugins = PluginConfig(data_root_mode="custom", plugins_data_root=str(root))
    p = resolve_plugin_paths(s)
    assert p.data_root == root.resolve()
    assert p.marketplaces_dir == root / "marketplaces"


def test_marketplace_json_roundtrip(tmp_path: Path) -> None:
    raw = {
        "name": "demo-mp",
        "owner": {"name": "Test"},
        "metadata": {"pluginRoot": "./plugins"},
        "plugins": [{"name": "p1", "source": "./plugins/p1", "description": "d"}],
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    m = load_marketplace_file(path)
    assert m is not None
    assert m.name == "demo-mp"
    assert plugin_root_prefix(m) == "./plugins"


def test_dispatch_plugin_help() -> None:
    s = Settings()
    d = dispatch_slash("/plugin", s, None)
    assert d is not None
    assert d.consume_without_llm
    assert plugin_slash_help().splitlines()[0] in (d.plugin_reply or "")


def test_discover_project_plugin(tmp_path: Path) -> None:
    plug = tmp_path / "proj" / ".claw" / "plugins" / "demo"
    (plug / ".claude-plugin").mkdir(parents=True)
    (plug / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "demo", "version": "1.0.0"}),
        encoding="utf-8",
    )
    (plug / "skills" / "hello").mkdir(parents=True)
    (plug / "skills" / "hello" / "SKILL.md").write_text(
        "---\nname: hello\ndescription: hi\n---\n\nBody.\n",
        encoding="utf-8",
    )

    s = Settings()
    s.working_directory = str(tmp_path / "proj")
    s.plugins = PluginConfig(enabled=True, data_root_mode="custom", plugins_data_root=str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()

    pm = PluginManager(s)
    pm.discover_and_load()
    names = [p.name for p in pm.plugins]
    assert "demo" in names
    sk = pm.get_all_skills()
    assert any(x.name == "hello" for x in sk)
