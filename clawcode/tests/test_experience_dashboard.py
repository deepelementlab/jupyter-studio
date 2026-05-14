from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawcode.config.settings import Settings
from clawcode.learning.experience_alerts import evaluate_experience_alerts
from clawcode.learning.experience_metrics import build_experience_dashboard
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_store import save_capsule
from clawcode.learning.service import LearningService
from clawcode.claw_learning import ops_observability as ops_obs
from clawcode.claw_learning.ops_observability import emit_ops_event


def test_experience_dashboard_schema_v1(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    cap = ExperienceCapsule(ecap_id="ecap-d1", title="d1", problem_type="general")
    cap.knowledge_triple.experience_fn.score = 0.8
    cap.knowledge_triple.experience_fn.confidence = 0.7
    cap.knowledge_triple.experience_fn.ci_lower = 0.6
    cap.knowledge_triple.experience_fn.ci_upper = 0.9
    cap.knowledge_triple.experience_fn.sample_count = 6
    cap.knowledge_triple.experience_fn.gap = 0.2
    save_capsule(settings, cap)

    out = build_experience_dashboard(settings)
    assert out["schema_version"] == "experience-dashboard-v1"
    assert "metrics" in out
    assert "window_metrics" in out
    assert "ecap_effectiveness_avg" in out["metrics"]
    assert "closed_loop_gain_consistency" in out["metrics"]


def test_experience_alert_thresholds_and_trend(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.experience_alert_thresholds["ecap_effectiveness_avg"]["critical_lt"] = 0.95
    settings.closed_loop.experience_alert_thresholds["ecap_gap_convergence"]["critical_drop_gt"] = 0.01

    cap = ExperienceCapsule(ecap_id="ecap-d2", title="d2", problem_type="general")
    cap.knowledge_triple.experience_fn.score = 0.2
    cap.knowledge_triple.experience_fn.confidence = 0.2
    cap.knowledge_triple.experience_fn.ci_lower = 0.0
    cap.knowledge_triple.experience_fn.ci_upper = 1.0
    cap.knowledge_triple.experience_fn.gap = 0.8
    save_capsule(settings, cap)

    dashboard = build_experience_dashboard(settings)
    alerts = evaluate_experience_alerts(settings, dashboard)
    assert alerts["schema_version"] == "experience-alerts-v1"
    assert alerts["level"] in {"warning", "critical"}
    assert len(alerts["alerts"]) >= 1


def test_autonomous_cycle_includes_dashboard_and_alerts(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    result = svc.run_autonomous_cycle(dry_run=True, report_only=False, apply_tuning=False, export_report=True)
    assert "experience_dashboard" in result
    assert "experience_alerts" in result
    assert "experience_health" in result
    assert result["experience_dashboard"]["schema_version"] == "experience-dashboard-v1"


def test_critical_alert_blocks_auto_tuning(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.tuning_auto_apply_enabled = True
    settings.closed_loop.experience_alert_thresholds["ecap_effectiveness_avg"]["critical_lt"] = 1.0

    svc = LearningService(settings)
    result = svc.run_autonomous_cycle(dry_run=True, report_only=False, apply_tuning=True, export_report=False)
    assert result["experience_alerts"]["level"] == "critical"
    assert result["tuning_status"] == "skipped"
    assert (result.get("applied_tuning") or {}).get("skipped") in {
        "critical_experience_alert",
        "experience_gate_blocked",
    }


def test_deeploop_convergence_decision_with_alerts_consistency_gate(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.clawteam_deeploop_consistency_min = 0.5
    svc = LearningService(settings)

    def fake_query(*, include_alerts: bool = True, domain: str | None = None) -> dict:
        return {
            "schema_version": "experience-dashboard-query-v1",
            "experience_dashboard": {"metrics": {"closed_loop_gain_consistency": 0.82}},
            "experience_alerts": {"level": "warning" if include_alerts else "ok", "alerts": []},
        }

    svc.experience_dashboard_query = fake_query  # type: ignore[method-assign]
    out = svc.deeploop_convergence_decision_with_alerts(iteration_records=[])
    assert out["decision"] == "stop"
    assert out["reason"] == "consistency_window_ok"
    assert out["experience_alerts_level"] == "warning"
    assert out["closed_loop_gain_consistency"] == 0.82


def test_deeploop_convergence_decision_with_alerts_forwards_alert_level(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.clawteam_deeploop_consistency_min = 0.0
    svc = LearningService(settings)

    def fake_query(*, include_alerts: bool = True, domain: str | None = None) -> dict:
        return {
            "schema_version": "experience-dashboard-query-v1",
            "experience_dashboard": {"metrics": {"closed_loop_gain_consistency": 0.1}},
            "experience_alerts": {"level": "critical", "alerts": [{"metric": "ecap_effectiveness_avg"}]},
        }

    svc.experience_dashboard_query = fake_query  # type: ignore[method-assign]
    out = svc.deeploop_convergence_decision_with_alerts(
        iteration_records=[{"gap_delta": 1.0, "handoff_success_rate": 0.0}],
        include_experience_alerts=True,
    )
    assert out["experience_alerts_level"] == "critical"
    assert out["closed_loop_gain_consistency"] == 0.1
    assert out["decision"] in {"degrade", "rollback", "continue", "stop"}


def test_experience_dashboard_and_deeploop_event_summary_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clawcode.claw_learning.ops_observability import summarize_clawteam_deeploop_events

    settings = Settings()
    settings.working_directory = str(tmp_path)
    monkeypatch.setattr(ops_obs, "get_settings", lambda: settings)

    cap = ExperienceCapsule(ecap_id="ecap-dloop-1", title="dloop", problem_type="general")
    cap.knowledge_triple.experience_fn.score = 0.75
    cap.knowledge_triple.experience_fn.confidence = 0.65
    cap.knowledge_triple.experience_fn.ci_lower = 0.55
    cap.knowledge_triple.experience_fn.ci_upper = 0.85
    cap.knowledge_triple.experience_fn.sample_count = 5
    cap.knowledge_triple.experience_fn.gap = 0.15
    save_capsule(settings, cap)

    dash = build_experience_dashboard(settings)
    assert "closed_loop_gain_consistency" in dash["metrics"]

    emit_ops_event(
        "clawteam_iteration_completed",
        {
            "gap_delta": -0.05,
            "handoff_success_rate": 0.88,
            "tecap_id": "t1",
            "trace_id": "tr1",
            "cycle_id": "cy1",
        },
    )
    emit_ops_event(
        "clawteam_deeploop_decision",
        {"decision": "continue", "reason": "need_more_iterations", "trace_id": "tr1", "cycle_id": "cy1"},
    )

    path = settings.get_data_directory() / settings.closed_loop.observability_events_file
    assert path.exists()
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    claw_rows = [r for r in rows if str(r.get("event_type", "")).startswith("clawteam_")]
    summary = summarize_clawteam_deeploop_events(claw_rows)
    assert summary["iteration_count"] >= 1
    assert summary["decision_counts"].get("continue", 0) >= 1


def test_experience_dashboard_query_without_autonomous_cycle(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    q = svc.experience_dashboard_query(include_alerts=False)
    assert q["schema_version"] == "experience-dashboard-query-v1"
    assert q["experience_dashboard"]["schema_version"] == "experience-dashboard-v1"
    assert q["experience_alerts"]["alerts"] == []
    assert "experience_policy_advice" in q


def test_experience_dashboard_contains_ab_comparison(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    snap_dir = settings.get_data_directory() / "learning" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    payload_a = {
        "payload": {
            "result": {
                "domain": "backend",
                "long_term_metrics": {"windows": {"7": {"normalized_combined_score": 0.7}}},
            }
        }
    }
    payload_b = {
        "payload": {
            "result": {
                "domain": "frontend",
                "long_term_metrics": {"windows": {"7": {"normalized_combined_score": 0.5}}},
            }
        }
    }
    (snap_dir / "a-autonomous-cycle.json").write_text(json.dumps(payload_a), encoding="utf-8")
    (snap_dir / "b-autonomous-cycle.json").write_text(json.dumps(payload_b), encoding="utf-8")
    out = build_experience_dashboard(settings)
    assert "ab_comparison" in out
    abx = out["ab_comparison"]
    assert abx["enabled"] is True
    assert abs(float(abx["delta"]) - 0.2) < 1e-6
    assert int(abx["sample_size"]) == 2
    assert "confidence" in abx
    assert "is_significant" in abx


def test_policy_auto_apply_with_cooldown_and_rollback(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.experience_policy_auto_apply_enabled = True
    settings.closed_loop.experience_policy_auto_apply_cooldown_cycles = 2
    settings.closed_loop.experience_alert_thresholds["ecap_effectiveness_avg"]["critical_lt"] = -1.0
    cap = ExperienceCapsule(ecap_id="ecap-pol-1", title="p1", problem_type="general")
    cap.knowledge_triple.experience_fn.score = 0.3
    cap.knowledge_triple.experience_fn.confidence = 0.2
    cap.knowledge_triple.experience_fn.ci_lower = 0.0
    cap.knowledge_triple.experience_fn.ci_upper = 1.0
    save_capsule(settings, cap)

    svc = LearningService(settings)
    r1 = svc.run_autonomous_cycle(dry_run=False, report_only=False, apply_tuning=False, export_report=False)
    pa1 = r1.get("experience_policy_apply", {})
    assert pa1.get("enabled") is True
    assert isinstance(pa1.get("applied"), list)

    r2 = svc.run_autonomous_cycle(dry_run=False, report_only=False, apply_tuning=False, export_report=False)
    pa2 = r2.get("experience_policy_apply", {})
    assert pa2.get("enabled") is True
    assert pa2.get("skipped_reason") in {"cooldown", "none", "no_suggestions"}

    settings.closed_loop.experience_alert_thresholds["ecap_effectiveness_avg"]["critical_lt"] = 1.0
    r3 = svc.run_autonomous_cycle(dry_run=False, report_only=False, apply_tuning=False, export_report=False)
    pa3 = r3.get("experience_policy_apply", {})
    assert pa3.get("enabled") is True
    assert "rollback_applied" in pa3
