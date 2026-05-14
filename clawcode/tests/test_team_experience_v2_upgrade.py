from __future__ import annotations

import json

from clawcode.config.settings import Settings
from clawcode.learning.team_experience_models import TeamExperienceCapsule
from clawcode.learning.team_experience_params import (
    parse_team_experience_create_args,
    parse_team_experience_apply_args,
    parse_team_experience_export_args,
)
from clawcode.learning.team_experience_store import (
    export_team_capsule,
    load_team_capsule,
    save_team_capsule,
)
from clawcode.learning.service import LearningService


def test_tecap_v1_read_upgrades_to_v2(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    # Save v1-like payload directly to storage.
    data_dir = settings.ensure_data_directory()
    caps = data_dir / "learning" / "team-experience" / "capsules"
    caps.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "tecap-v1",
        "tecap_id": "tv1",
        "title": "Old",
        "problem_type": "debug",
        "team_context": {"objective": "x", "constraints": [], "repo_fingerprint": "r", "participants": []},
        "participants": [],
        "collaboration_trace": {"steps": [{"owner_agent": "a1", "step_type": "execute", "input_summary": "i", "output_summary": "o"}]},
        "coordination_patterns": ["p1"],
        "anti_patterns": [],
        "outcome": {"result": "success", "verification": [], "risk_left": [], "delivery_metrics": {}},
        "transfer": {"applicability_conditions": [], "team_migration_hints": []},
        "related_ecap_ids": [],
        "related_instinct_ids": [],
        "governance": {"privacy_level": "balanced", "redaction_applied": True, "created_at": "", "updated_at": "", "feedback_score": 0.0, "feedback_count": 0, "deprecated": False},
    }
    (caps / "tv1.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    cap = load_team_capsule(settings, "tv1")
    assert cap is not None
    assert cap.schema_version == "tecap-v3"
    assert cap.quality_gates
    assert cap.team_topology is not None


def test_tecap_retrieval_scoring_and_explain(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    a = TeamExperienceCapsule(tecap_id="ta", title="A", problem_type="incident")
    a.team_context.repo_fingerprint = "clawteam"
    a.coordination_patterns = ["incident-response"]
    a.governance.feedback_score = 0.9
    a.outcome.result = "success"
    a.coordination_metrics.handoff_success_rate = 0.9
    save_team_capsule(settings, a)

    b = TeamExperienceCapsule(tecap_id="tb", title="B", problem_type="incident")
    b.team_context.repo_fingerprint = "other-team"
    b.coordination_patterns = ["misc"]
    b.governance.feedback_score = 0.2
    b.outcome.result = "partial"
    b.coordination_metrics.handoff_success_rate = 0.1
    save_team_capsule(settings, b)

    args, err = parse_team_experience_apply_args(
        "--problem-type incident --team clawteam --workflow incident-response --top-k 1 --explain"
    )
    assert err == ""
    assert args is not None
    rows = svc.retrieve_team_capsules(args)
    assert len(rows) == 1
    assert rows[0].tecap_id == "ta"
    assert rows[0].match_explain
    ok, prompt = svc.build_team_experience_apply_prompt(args)
    assert ok
    assert "Match explain:" in prompt


def test_tecap_export_json_v1_compatible(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    cap = TeamExperienceCapsule(tecap_id="tv1c", title="Compat", problem_type="general")
    cap.coordination_metrics.handoff_success_rate = 0.5
    save_team_capsule(settings, cap)
    out = export_team_capsule(settings, cap, fmt="json", v1_compatible=True)
    obj = json.loads(out.read_text(encoding="utf-8"))
    assert obj["schema_version"] == "tecap-v1"
    assert "team_topology" not in obj
    assert "coordination_metrics" not in obj


def test_tecap_params_strategy_and_export_flag() -> None:
    a, err = parse_team_experience_apply_args("tid --strategy aggressive --explain")
    assert err == ""
    assert a is not None
    assert a.strategy == "aggressive"
    assert a.explain is True

    e, err2 = parse_team_experience_export_args("tid --format json --v1-compatible")
    assert err2 == ""
    assert e is not None
    assert e.v1_compatible is True

    c, err3 = parse_team_experience_create_args("Improve CI flow --role-ecap-mode inline --participants a,b")
    assert err3 == ""
    assert c is not None
    assert c.role_ecap_mode == "inline"
