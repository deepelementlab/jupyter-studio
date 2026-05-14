from __future__ import annotations

from pathlib import Path

import pytest

from clawcode.config.settings import Settings
from clawcode.claw_learning import ops_observability
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_store import load_capsule, save_capsule
from clawcode.learning.service import LearningService
from clawcode.learning.team_experience_models import (
    TeamContext,
    TeamExperienceCapsule,
    TeamParticipant,
)
from clawcode.learning.team_experience_store import load_team_capsule, save_team_capsule
from clawcode.tui.builtin_slash_handlers import handle_builtin_slash


def test_retrieve_team_capsules_for_clawteam_prefers_role_overlap(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)

    a = TeamExperienceCapsule(
        tecap_id="tecap-a",
        problem_type="general",
        team_context=TeamContext(repo_fingerprint="active-workspace"),
        participants=[TeamParticipant(agent_id="clawteam-qa"), TeamParticipant(agent_id="clawteam-sre")],
    )
    a.team_experience_fn.score = 0.8
    b = TeamExperienceCapsule(
        tecap_id="tecap-b",
        problem_type="general",
        team_context=TeamContext(repo_fingerprint="active-workspace"),
        participants=[TeamParticipant(agent_id="clawteam-devops")],
    )
    b.team_experience_fn.score = 0.9
    save_team_capsule(settings, a)
    save_team_capsule(settings, b)

    rows = svc.retrieve_team_capsules_for_clawteam(
        problem_type="general",
        participants=["clawteam-qa", "clawteam-sre"],
        team="active-workspace",
        top_k=1,
    )
    assert rows
    assert rows[0].tecap_id == "tecap-a"


def test_writeback_tecap_from_clawteam_appends_iteration_record(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    cap = TeamExperienceCapsule(tecap_id="tecap-wb")
    save_team_capsule(settings, cap)

    out = svc.writeback_tecap_from_clawteam(
        tecap_id="tecap-wb",
        observed_score=0.7,
        result="success",
        iteration_record={
            "iteration": 2,
            "iteration_goal": "reduce gap",
            "role_handoff_result": "ok",
            "gap_before": 0.4,
            "gap_after": 0.2,
            "gap_delta": 0.2,
            "deviation_reason": "",
        },
    )
    assert out["success"] is True
    saved = load_team_capsule(settings, "tecap-wb")
    assert saved is not None
    assert saved.iteration_records
    assert saved.iteration_records[-1].iteration == 2


def test_deeploop_convergence_decision_degrades_on_critical(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    out = svc.deeploop_convergence_decision(
        iteration_records=[{"gap_delta": 0.01, "handoff_success_rate": 0.95}],
        alerts_level="critical",
    )
    assert out["decision"] == "degrade"
    assert out["converged"] is False


def test_writeback_role_ecap_from_clawteam_updates_ecap(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    ecap = ExperienceCapsule(ecap_id="ecap-role")
    ecap.knowledge_triple.experience_fn.score = 0.1
    save_capsule(settings, ecap)
    out = svc.writeback_role_ecap_from_clawteam(
        role_ecap_map={"clawteam-qa": "ecap-role"},
        result="pass",
        observed_score=0.8,
    )
    assert out["count"] == 1


@pytest.mark.asyncio
async def test_e2e_clawteam_deep_loop_prompt_to_finalize_writeback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slash deep_loop prompt exposes iteration contract; finalize chains log + TECAP + ECAP writeback."""
    settings = Settings()
    settings.working_directory = str(tmp_path)

    tecap = TeamExperienceCapsule(
        tecap_id="tecap-e2e",
        problem_type="general",
        team_context=TeamContext(repo_fingerprint="active-workspace"),
        participants=[TeamParticipant(agent_id="clawteam-qa")],
    )
    save_team_capsule(settings, tecap)
    ecap = ExperienceCapsule(ecap_id="ecap-e2e", title="clawteam-qa regression", problem_type="general")
    ecap.knowledge_triple.experience_fn.score = 0.2
    save_capsule(settings, ecap)

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "clawcode.tui.builtin_slash_handlers.emit_ops_event",
        lambda et, payload: events.append((str(et), dict(payload))),
    )
    slash_out = await handle_builtin_slash(
        "clawteam",
        "--deep_loop ship feature with handoff checks",
        settings=settings,
        session_service=None,
    )
    assert slash_out.kind == "agent_prompt"
    prompt = slash_out.agent_user_text or ""
    assert "Deep loop mode: ENABLED" in prompt
    assert "iteration_goal" in prompt
    assert "gap_delta" in prompt
    assert "TECAP context (retrieved)" in prompt
    assert "DEEP_LOOP_WRITEBACK_JSON:" in prompt

    started = [x for x in events if x[0] == "clawteam_deeploop_started"]
    assert started
    p = started[-1][1]
    assert p.get("policy_id") == "clawteam-deeploop-v1"
    assert "domain" in p

    svc = LearningService(settings)
    fin = svc.finalize_clawteam_deeploop_writeback(
        tecap_id="tecap-e2e",
        iteration=1,
        iteration_goal="close gap on handoffs",
        role_handoff_result="all roles ack",
        gap_before=0.5,
        gap_after=0.1,
        deviation_reason="",
        role_ecap_map={"clawteam-qa": "ecap-e2e"},
        observed_score=0.85,
        result="success",
        trace_id="trace-e2e",
        cycle_id="cycle-e2e",
    )
    assert fin.get("skipped") is False
    assert fin["tecap_writeback"].get("success") is True
    assert fin["role_ecap_writeback"]["count"] == 1

    loaded_t = load_team_capsule(settings, "tecap-e2e")
    assert loaded_t is not None
    assert loaded_t.iteration_records
    assert loaded_t.iteration_records[-1].iteration_goal == "close gap on handoffs"

    loaded_e = load_capsule(settings, "ecap-e2e")
    assert loaded_e is not None
    assert loaded_e.knowledge_triple.experience_fn.score > 0.2

    data_dir = settings.get_data_directory()
    deeploop_log = data_dir / "learning" / "team-experience" / "deeploop_iterations.jsonl"
    assert deeploop_log.exists()
    assert "close gap on handoffs" in deeploop_log.read_text(encoding="utf-8")


def test_finalize_clawteam_deeploop_writeback_skipped_when_auto_off(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.clawteam_deeploop_auto_writeback_enabled = False
    svc = LearningService(settings)
    out = svc.finalize_clawteam_deeploop_writeback(
        tecap_id="x",
        iteration=1,
        iteration_goal="g",
        role_handoff_result="ok",
        gap_before=1.0,
        gap_after=0.5,
        role_ecap_map={},
        observed_score=0.5,
    )
    assert out.get("skipped") is True


def test_deeploop_convergence_decision_rollback_matrix_and_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.clawteam_deeploop_max_rollbacks = 1
    svc = LearningService(settings)
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        ops_observability,
        "emit_ops_event",
        lambda et, payload: events.append((str(et), dict(payload))),
    )
    out = svc.deeploop_convergence_decision(
        iteration_records=[{"gap_delta": 0.5, "handoff_success_rate": 0.2}],
        alerts_level="critical",
        rollback_count=1,
        trace_id="trace-rb",
        cycle_id="cycle-rb",
        policy_id="p1",
        domain="backend",
        experiment_id="exp1",
    )
    assert out["decision"] == "rollback"
    decision = [x for x in events if x[0] == "clawteam_deeploop_decision"]
    assert decision
    payload = decision[-1][1]
    assert payload.get("decision") == "rollback"
    assert payload.get("policy_id") == "p1"
    assert payload.get("domain") == "backend"


def test_deeploop_convergence_stop_on_max_iters(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.clawteam_deeploop_max_iters = 2
    svc = LearningService(settings)
    out = svc.deeploop_convergence_decision(
        iteration_records=[{"gap_delta": 0.2, "handoff_success_rate": 0.7}],
        current_iteration=2,
    )
    assert out["decision"] == "stop"
    assert out["reason"] == "max_iters_reached"


def test_finalize_clawteam_deeploop_from_output_parses_machine_line(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    tecap = TeamExperienceCapsule(tecap_id="tecap-out")
    save_team_capsule(settings, tecap)
    ecap = ExperienceCapsule(ecap_id="ecap-out")
    save_capsule(settings, ecap)
    output_text = (
        "iteration summary...\n"
        'DEEP_LOOP_WRITEBACK_JSON: {"iteration": 3, "iteration_goal": "stabilize handoff", '
        '"role_handoff_result": "ok", "gap_before": 0.4, "gap_after": 0.1, '
        '"deviation_reason": "", "handoff_success_rate": 0.9, "observed_score": 0.88, "result": "success"}\n'
    )
    out = svc.finalize_clawteam_deeploop_from_output(
        tecap_id="tecap-out",
        role_ecap_map={"clawteam-qa": "ecap-out"},
        output_text=output_text,
    )
    assert out.get("skipped") is False
    saved = load_team_capsule(settings, "tecap-out")
    assert saved is not None
    assert saved.iteration_records and saved.iteration_records[-1].iteration == 3
