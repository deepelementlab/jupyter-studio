"""Built-in `api-design` skill from ``plugin/builtin_plugins``."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.slash import dispatch_slash, plugin_skill_autocomplete_entries


def test_builtin_api_design_skill_loaded(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    names = {sk.name for sk in pm.get_all_skills()}
    assert "api-design" in names
    ad = next(sk for sk in pm.get_all_skills() if sk.name == "api-design")
    assert "REST API" in ad.description or "pagination" in ad.description.lower()
    assert ad.plugin_name == "clawcode-skills"


def test_dispatch_api_design_wraps_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    out = dispatch_slash("/api-design pagination for users list", settings, pm)
    assert out is not None
    assert out.consume_without_llm is False
    text = out.llm_user_text or ""
    assert "[Skill /api-design" in text
    assert "Pagination" in text or "pagination" in text.lower()
    assert "User request:" in text


def test_plugin_skill_autocomplete_entries_includes_api_design(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    rows = plugin_skill_autocomplete_entries(pm)
    names = [n for n, _ in rows]
    assert "api-design" in names
    row = next((d for n, d in rows if n == "api-design"), "")
    assert "REST" in row or "Skill" in row


def test_plugins_disabled_skips_skill_load(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = False
    pm = PluginManager(settings)
    pm.discover_and_load()
    assert pm.get_all_skills() == []
