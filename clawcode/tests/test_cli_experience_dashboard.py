from __future__ import annotations

import json

from click.testing import CliRunner

from clawcode.cli.commands import cli
from clawcode.config.settings import Settings


def test_cli_experience_dashboard_json_contract(tmp_path, monkeypatch) -> None:
    async def _fake_load_settings(*, working_directory=None, debug=False):
        s = Settings()
        if working_directory:
            s.working_directory = str(working_directory)
        return s

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def experience_dashboard_query(self, *, include_alerts: bool = True, domain: str | None = None):
            return {
                "schema_version": "experience-dashboard-query-v1",
                "experience_dashboard": {"schema_version": "experience-dashboard-v1", "domain": domain or ""},
                "experience_alerts": {"level": "ok", "alerts": []},
                "experience_policy_advice": {"guard_mode": "normal", "suggestions": []},
                "experience_health": "ok",
            }

    import clawcode.cli.commands as commands_mod
    import clawcode.learning.service as learning_service_mod

    monkeypatch.setattr(commands_mod, "load_settings", _fake_load_settings)
    monkeypatch.setattr(learning_service_mod, "LearningService", _FakeSvc)

    r = CliRunner().invoke(
        cli,
        ["experience-dashboard", "--cwd", str(tmp_path), "--json", "--no-alerts", "--domain", "backend"],
    )
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert payload["schema_version"] == "experience-dashboard-query-v1"
    assert payload["experience_dashboard"]["schema_version"] == "experience-dashboard-v1"
    assert payload["experience_dashboard"]["domain"] == "backend"


def test_cli_experience_dashboard_text_sections(tmp_path, monkeypatch) -> None:
    async def _fake_load_settings(*, working_directory=None, debug=False):
        s = Settings()
        if working_directory:
            s.working_directory = str(working_directory)
        return s

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def experience_dashboard_query(self, *, include_alerts: bool = True, domain: str | None = None):
            return {
                "schema_version": "experience-dashboard-query-v1",
                "experience_dashboard": {
                    "schema_version": "experience-dashboard-v1",
                    "generated_at": "t0",
                    "domain": domain or "",
                    "metrics": {"ecap_effectiveness_avg": 0.7},
                    "window_metrics": {"7": {"ecap_effectiveness_avg": 0.68}},
                    "ab_comparison": {"enabled": True, "delta": 0.1, "buckets": {"a": 0.6, "b": 0.7}},
                },
                "experience_alerts": {"level": "warning", "alerts": [{"metric": "x", "level": "warning", "value": 0.1, "reason": "r"}]},
                "experience_policy_advice": {"guard_mode": "normal", "suggestions": [{"target": "foo", "op": "set", "value": 1}]},
                "experience_health": "warning",
            }

    import clawcode.cli.commands as commands_mod
    import clawcode.learning.service as learning_service_mod

    monkeypatch.setattr(commands_mod, "load_settings", _fake_load_settings)
    monkeypatch.setattr(learning_service_mod, "LearningService", _FakeSvc)

    r = CliRunner().invoke(
        cli,
        ["experience-dashboard", "--cwd", str(tmp_path), "--domain", "backend"],
    )
    assert r.exit_code == 0
    out = r.output
    assert "## Current metrics" in out
    assert "## Window metrics" in out
    assert "## Alerts" in out
    assert "## Adaptive policy advice" in out
    assert "## A/B comparison" in out
