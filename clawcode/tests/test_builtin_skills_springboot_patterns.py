"""Built-in `springboot-patterns` skill from ``plugin/builtin_plugins``."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.slash import dispatch_slash, plugin_skill_autocomplete_entries


def test_builtin_springboot_patterns_skill_loaded(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    names = {sk.name for sk in pm.get_all_skills()}
    assert "springboot-patterns" in names
    sk = next(s for s in pm.get_all_skills() if s.name == "springboot-patterns")
    assert "Spring" in sk.description or "Boot" in sk.description
    assert sk.plugin_name == "clawcode-skills"


def test_dispatch_springboot_patterns_wraps_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    out = dispatch_slash("/springboot-patterns add REST controller with validation", settings, pm)
    assert out is not None
    assert out.consume_without_llm is False
    text = out.llm_user_text or ""
    assert "[Skill /springboot-patterns" in text
    assert "Spring Boot" in text
    assert "REST" in text or "Controller" in text
    assert "User request:" in text


def test_plugin_skill_autocomplete_entries_includes_springboot_patterns(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    rows = plugin_skill_autocomplete_entries(pm)
    names = [n for n, _ in rows]
    assert "springboot-patterns" in names
    row = next((d for n, d in rows if n == "springboot-patterns"), "")
    assert "Spring" in row or "Skill" in row
