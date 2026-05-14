"""Built-in `strategic-compact` skill from ``plugin/builtin_plugins``."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.slash import dispatch_slash, plugin_skill_autocomplete_entries


def test_builtin_strategic_compact_skill_loaded(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    names = {sk.name for sk in pm.get_all_skills()}
    assert "strategic-compact" in names
    sk = next(s for s in pm.get_all_skills() if s.name == "strategic-compact")
    assert "compact" in sk.description.lower() or "context" in sk.description.lower()
    assert sk.plugin_name == "clawcode-skills"


def test_dispatch_strategic_compact_wraps_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    out = dispatch_slash("/strategic-compact when to compact before implementation phase", settings, pm)
    assert out is not None
    assert out.consume_without_llm is False
    text = out.llm_user_text or ""
    assert "[Skill /strategic-compact" in text
    assert "Strategic" in text or "compact" in text.lower()
    assert "Planning" in text or "Research" in text or "Phase" in text
    assert "User request:" in text


def test_plugin_skill_autocomplete_entries_includes_strategic_compact(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    rows = plugin_skill_autocomplete_entries(pm)
    names = [n for n, _ in rows]
    assert "strategic-compact" in names
    row = next((d for n, d in rows if n == "strategic-compact"), "")
    assert "compact" in row.lower() or "Skill" in row
