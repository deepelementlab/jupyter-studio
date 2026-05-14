"""Built-in `database-migrations` skill from ``plugin/builtin_plugins``."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.slash import dispatch_slash, plugin_skill_autocomplete_entries


def test_builtin_database_migrations_skill_loaded(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    names = {sk.name for sk in pm.get_all_skills()}
    assert "database-migrations" in names
    sk = next(s for s in pm.get_all_skills() if s.name == "database-migrations")
    assert "migration" in sk.description.lower() or "PostgreSQL" in sk.description
    assert sk.plugin_name == "clawcode-skills"


def test_dispatch_database_migrations_wraps_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    out = dispatch_slash(
        "/database-migrations add index CONCURRENTLY on large users table",
        settings,
        pm,
    )
    assert out is not None
    assert out.consume_without_llm is False
    text = out.llm_user_text or ""
    assert "[Skill /database-migrations" in text
    assert "PostgreSQL" in text or "migration" in text.lower()
    assert "CONCURRENTLY" in text or "ALTER TABLE" in text
    assert "User request:" in text


def test_plugin_skill_autocomplete_entries_includes_database_migrations(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    rows = plugin_skill_autocomplete_entries(pm)
    names = [n for n, _ in rows]
    assert "database-migrations" in names
    row = next((d for n, d in rows if n == "database-migrations"), "")
    assert "migration" in row.lower() or "Skill" in row
