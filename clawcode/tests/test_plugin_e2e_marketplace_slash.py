"""E2E-style tests: local marketplace, install to cache, /plugin slash (no network, no git)."""

from __future__ import annotations

import json
from pathlib import Path

from clawcode.config.settings import PluginConfig, Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.ops import (
    install_plugin_from_marketplace,
    marketplace_add,
    marketplace_list,
    uninstall_plugin,
)
from clawcode.plugin.paths import resolve_plugin_paths
from clawcode.plugin.slash import dispatch_slash
from clawcode.plugin.state import load_plugin_state


def _write_minimal_plugin(root: Path, name: str, skill: str = "alpha") -> None:
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": "0.0.1", "description": "test"}),
        encoding="utf-8",
    )
    sk = root / "skills" / skill
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text(
        f"---\nname: {skill}\ndescription: test skill\n---\n\nDo the thing.\n",
        encoding="utf-8",
    )


def _write_marketplace(mp_root: Path, mp_name: str, plugin_name: str) -> None:
    plug = mp_root / "plugins" / plugin_name
    _write_minimal_plugin(plug, plugin_name)
    (mp_root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    cat = {
        "name": mp_name,
        "owner": {"name": "pytest"},
        "plugins": [
            {
                "name": plugin_name,
                "source": f"./plugins/{plugin_name}",
                "description": "bundled test plugin",
            }
        ],
    }
    (mp_root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(cat), encoding="utf-8"
    )


def test_marketplace_add_install_discover(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    mp_root = tmp_path / "my-marketplace"
    _write_marketplace(mp_root, "acme-mp", "tiny-plugin")

    s = Settings()
    s.working_directory = str(tmp_path)
    s.plugins = PluginConfig(enabled=True, data_root_mode="clawcode")

    mname, _ = marketplace_add(s, str(mp_root))
    assert mname == "acme-mp"
    rows = marketplace_list(s)
    assert len(rows) == 1 and rows[0].name == "acme-mp"

    dest = install_plugin_from_marketplace(s, "tiny-plugin", "acme-mp")
    assert dest.is_dir()
    assert (dest / ".claude-plugin" / "plugin.json").is_file()

    pm = PluginManager(s)
    pm.discover_and_load()
    names = {p.name for p in pm.plugins}
    assert "tiny-plugin" in names
    skills = pm.get_all_skills()
    assert any(sk.name == "alpha" for sk in skills)


def test_plugin_slash_list_and_uninstall(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    mp_root = tmp_path / "mp2"
    _write_marketplace(mp_root, "m2", "p2")

    s = Settings()
    s.working_directory = str(tmp_path)
    s.plugins = PluginConfig(enabled=True, data_root_mode="clawcode")

    marketplace_add(s, str(mp_root))
    install_plugin_from_marketplace(s, "p2", "m2")

    pm = PluginManager(s)
    pm.discover_and_load()

    d = dispatch_slash("/plugin list", s, pm)
    assert d is not None and d.consume_without_llm
    assert d.plugin_reply and "p2" in d.plugin_reply

    d2 = dispatch_slash("/plugin uninstall p2", s, pm)
    assert d2 is not None and d2.consume_without_llm
    assert d2.plugin_reply and "Uninstalled" in d2.plugin_reply

    pm.discover_and_load()
    assert "p2" not in {p.name for p in pm.plugins}
    st = load_plugin_state(resolve_plugin_paths(s).state_file)
    assert "p2" not in st.installed


def test_plugin_slash_install_from_marketplace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    mp_root = tmp_path / "mp3"
    _write_marketplace(mp_root, "m3", "p3")

    s = Settings()
    s.working_directory = str(tmp_path)
    s.plugins = PluginConfig(enabled=True, data_root_mode="clawcode")

    marketplace_add(s, str(mp_root))
    pm = PluginManager(s)
    pm.discover_and_load()
    assert "p3" not in {p.name for p in pm.plugins}

    d = dispatch_slash("/plugin install p3@m3", s, pm)
    assert d is not None and d.consume_without_llm
    assert d.plugin_reply and "Installed" in d.plugin_reply

    pm.discover_and_load()
    assert "p3" in {p.name for p in pm.plugins}


def test_skill_slash_wraps_prompt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    proj = tmp_path / "proj"
    plug = proj / ".clawcode" / "plugins" / "skplug"
    _write_minimal_plugin(plug, "skplug", skill="beta")

    s = Settings()
    s.working_directory = str(proj)
    s.plugins = PluginConfig(enabled=True, data_root_mode="custom", plugins_data_root=str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()

    pm = PluginManager(s)
    pm.discover_and_load()

    d = dispatch_slash("/beta please review", s, pm)
    assert d is not None
    assert not d.consume_without_llm
    assert "Skill /beta" in d.llm_user_text
    assert "please review" in d.llm_user_text
