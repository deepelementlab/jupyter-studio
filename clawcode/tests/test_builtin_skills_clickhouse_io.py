"""Built-in `clickhouse-io` skill from ``plugin/builtin_plugins``."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.plugin.manager import PluginManager
from clawcode.plugin.slash import dispatch_slash, plugin_skill_autocomplete_entries


def test_builtin_clickhouse_io_skill_loaded(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    names = {sk.name for sk in pm.get_all_skills()}
    assert "clickhouse-io" in names
    sk = next(s for s in pm.get_all_skills() if s.name == "clickhouse-io")
    assert "ClickHouse" in sk.description or "analytics" in sk.description.lower()
    assert sk.plugin_name == "clawcode-skills"


def test_dispatch_clickhouse_io_wraps_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    out = dispatch_slash("/clickhouse-io design MergeTree partition for daily metrics", settings, pm)
    assert out is not None
    assert out.consume_without_llm is False
    text = out.llm_user_text or ""
    assert "[Skill /clickhouse-io" in text
    assert "MergeTree" in text or "PARTITION" in text or "ClickHouse" in text
    assert "User request:" in text


def test_plugin_skill_autocomplete_entries_includes_clickhouse_io(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.plugins.enabled = True
    pm = PluginManager(settings)
    pm.discover_and_load()
    rows = plugin_skill_autocomplete_entries(pm)
    names = [n for n, _ in rows]
    assert "clickhouse-io" in names
    row = next((d for n, d in rows if n == "clickhouse-io"), "")
    assert "ClickHouse" in row or "Skill" in row
