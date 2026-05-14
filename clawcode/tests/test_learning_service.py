from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawcode.config.settings import Settings
from clawcode.learning.params import EvolveArgs
from clawcode.learning.service import LearningService
from clawcode.learning.store import record_tool_observation


def test_learn_from_observations_creates_personal_instinct_file(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    for _ in range(3):
        record_tool_observation(
            settings,
            phase="tool_start",
            session_id="s1",
            tool_name="ReadFile",
            tool_call_id="tc1",
            tool_input={"path": "a.py"},
            tool_output="",
            is_error=False,
        )
    record_tool_observation(
        settings,
        phase="tool_complete",
        session_id="s1",
        tool_name="ReadFile",
        tool_call_id="tc1",
        tool_input={"path": "a.py"},
        tool_output="ok",
        is_error=False,
    )
    svc = LearningService(settings)
    txt = svc.learn_from_recent_observations()
    assert "Learned" in txt
    personal_dir = settings.get_data_directory() / "learning" / "instincts" / "personal"
    files = list(personal_dir.glob("learned-*.md"))
    assert files


def test_import_export_and_evolve_mvp(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    src = tmp_path / "team-instincts.md"
    src.write_text(
        "---\n"
        "id: test-first-workflow\n"
        "trigger: \"when adding feature\"\n"
        "confidence: 0.8\n"
        "domain: testing\n"
        "source: inherited\n"
        "---\n\n"
        "## Action\nWrite tests first.\n\n"
        "---\n"
        "id: grep-before-edit\n"
        "trigger: \"when modifying code\"\n"
        "confidence: 0.7\n"
        "domain: workflow\n"
        "source: inherited\n"
        "---\n\n"
        "## Action\nSearch before editing.\n\n"
        "---\n"
        "id: validate-before-write\n"
        "trigger: \"when modifying code\"\n"
        "confidence: 0.75\n"
        "domain: workflow\n"
        "source: inherited\n"
        "---\n\n"
        "## Action\nValidate assumptions before writing files.\n",
        encoding="utf-8",
    )
    msg = svc.import_instincts(str(src), force=True)
    assert "Import complete" in msg
    out = tmp_path / "exported.md"
    msg2 = svc.export_instincts(output=str(out), min_confidence=0.7)
    assert "Exported" in msg2
    assert out.exists()
    msg3 = svc.evolve(generate=True)
    assert "Generated" in msg3


def test_run_autonomous_cycle_dry_run_writes_snapshot(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    result = svc.run_autonomous_cycle(
        dry_run=True,
        report_only=False,
        apply_tuning=False,
        export_report=False,
        window_hours=12,
    )
    assert result["schema_version"] == "autonomous-cycle-v2"
    assert result["mode"].startswith("dry-run")
    assert result["idempotency"] in {"fresh_run", "cache_hit"}
    assert result["observe_status"] in {"ok", "error", "skipped"}
    assert result["evolve_status"] in {"ok", "error", "skipped"}
    assert result["import_status"] == "skipped"
    assert isinstance(result["errors"], list)
    assert "ops_report" in result
    assert "tuning_report" in result
    assert "stage_status" in result
    assert "long_term_metrics" in result
    assert "canary_evaluation" in result
    assert "governance_status" in result
    assert "guardrail_triggered" in result
    assert "audit_record_id" in result
    assert "governance_summary" in result
    assert result["json_contract_version"] == "learn-orchestrate-json-v1"
    assert str(result.get("trace_id", "")).startswith("trace-")
    assert str(result.get("cycle_id", "")).startswith("cycle-")
    assert "slo_state" in result
    assert "policy_id" in result
    assert "policy_scope" in result["governance_summary"]
    assert "policy_version" in result["governance_summary"]
    assert "freeze_until_ts" in result["governance_summary"]
    assert "runbook" in result
    snap_dir = settings.get_data_directory() / "learning" / "snapshots"
    assert any("autonomous-cycle" in p.name for p in snap_dir.glob("*.json"))


def test_closed_loop_contract_report_shape(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    report = svc.closed_loop_contract_report()
    assert report["schema_version"] == "closed-loop-contract-v1"
    assert report["total_keys"] >= report["consumed_count"]
    assert report["total_keys"] >= report["unconsumed_count"]
    assert "tuning_auto_apply_enabled" in report["consumed_keys"]
    assert "clawteam_deeploop_consistency_min" in report["consumed_keys"]
    assert report["risk_level"] in {"low", "medium", "high"}


def test_runtime_lock_recycles_stale_lock(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    lock_path, _ = svc._runtime_guard_paths()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text('{"pid":1,"ts":1}', encoding="utf-8")
    acquired = svc._acquire_process_lock()
    assert acquired is True
    svc._release_process_lock()


def test_execute_recovery_actions_handles_known_actions(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    out = svc.execute_recovery_actions(
        [{"id": "prune_idempotency_cache", "enabled": True}, {"id": "unknown_action", "enabled": True}]
    )
    assert "action_results" in out
    assert any(x.get("id") == "prune_idempotency_cache" for x in out["action_results"])


def test_fault_injection_stale_process_lock_recycled_then_autonomous_cycle_runs(tmp_path: Path) -> None:
    """Stale lock file (age > 300s) is removed by _acquire_process_lock; cycle should complete."""
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    lock_path, _ = svc._runtime_guard_paths()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": 999999, "ts": 1}), encoding="utf-8")

    result = svc.run_autonomous_cycle(
        evolve_args=EvolveArgs(execute=False, dry_run=True),
        dry_run=True,
        report_only=True,
        apply_tuning=False,
        export_report=False,
        window_hours=6,
    )
    assert result["idempotency"] == "fresh_run"
    assert result.get("errors", []) == []


def test_fault_injection_corrupt_idempotency_cache_autonomous_cycle_still_runs(tmp_path: Path) -> None:
    """Invalid JSON in idempotency cache is ignored; cycle must not crash."""
    LearningService._cycle_cache.clear()
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    _, cache_path = svc._runtime_guard_paths()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{not valid json", encoding="utf-8")

    assert svc._load_idempotency_cache() == {}

    result = svc.run_autonomous_cycle(
        evolve_args=EvolveArgs(execute=False, dry_run=True),
        dry_run=True,
        report_only=True,
        apply_tuning=False,
        export_report=False,
        window_hours=6,
    )
    assert result["schema_version"] == "autonomous-cycle-v2"
    assert result["idempotency"] == "fresh_run"


def test_fault_injection_prune_idempotency_cache_rewrites_after_corruption(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    _, cache_path = svc._runtime_guard_paths()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("CORRUPT", encoding="utf-8")
    out = svc.execute_recovery_actions([{"id": "prune_idempotency_cache", "enabled": True}])
    assert any(
        x.get("id") == "prune_idempotency_cache" and x.get("executed") is True for x in out["action_results"]
    )
    assert cache_path.exists()
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {}


def test_fault_injection_process_lock_busy_runbook_includes_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate another process holding the lock: cycle skips with runbook + recovery metadata."""
    LearningService._cycle_cache.clear()
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    monkeypatch.setattr(LearningService, "_acquire_process_lock", lambda self: False)

    result = svc.run_autonomous_cycle(
        evolve_args=EvolveArgs(execute=False, dry_run=True),
        dry_run=True,
        report_only=True,
        apply_tuning=False,
        export_report=False,
        window_hours=6,
    )
    assert result["idempotency"] == "lock_busy"
    rb = result.get("runbook", {})
    assert rb.get("code") == "CYCLE_LOCK_BUSY"
    assert "auto_actions" in rb
    assert "action_results" in rb
    assert "next_retry_at" in rb
