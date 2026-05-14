"""Built-in `django-patterns` skill from ``plugin/builtin_plugins``."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.slash import dispatch_slash, plugin_skill_autocomplete_entries


def test_builtin_django_patterns_skill_loaded(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    names = {sk.name for sk in pm.get_all_skills()}
    assert "django-patterns" in names
    sk = next(s for s in pm.get_all_skills() if s.name == "django-patterns")
    assert "Django" in sk.description or "DRF" in sk.description
    assert sk.plugin_name == "clawcode-skills"


def test_dispatch_django_patterns_wraps_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    out = dispatch_slash("/django-patterns add DRF model serializer", settings, pm)
    assert out is not None
    assert out.consume_without_llm is False
    text = out.llm_user_text or ""
    assert "[Skill /django-patterns" in text
    assert "Django" in text
    assert "REST" in text or "ORM" in text
    assert "User request:" in text


def test_plugin_skill_autocomplete_entries_includes_django_patterns(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    rows = plugin_skill_autocomplete_entries(pm)
    names = [n for n, _ in rows]
    assert "django-patterns" in names
    row = next((d for n, d in rows if n == "django-patterns"), "")
    assert "Django" in row or "Skill" in row
