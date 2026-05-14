from __future__ import annotations

from clawcode.config.settings import Settings
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_params import ExperienceApplyArgs, ExperienceFeedbackArgs
from clawcode.learning.experience_store import load_capsule, save_capsule
from clawcode.learning.models import Instinct
from clawcode.learning.service import LearningService
from clawcode.learning.store import write_instincts_file
from clawcode.learning.team_experience_models import TeamExperienceCapsule, TeamParticipant
from clawcode.learning.team_experience_params import (
    TeamExperienceApplyArgs,
    TeamExperienceCreateArgs,
    TeamExperienceFeedbackArgs,
)
from clawcode.learning.team_experience_store import load_team_capsule, save_team_capsule


def test_ecap_apply_contains_triple_context(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    cap = ExperienceCapsule(ecap_id="ecap-triple-1", title="triple", problem_type="debug")
    cap.knowledge_triple.instinct_ref.instinct_ids = ["ins-1", "ins-2"]
    cap.knowledge_triple.skill_ref.skill_name = "deploy-pattern"
    cap.knowledge_triple.skill_ref.skill_version = "1.0.0"
    cap.knowledge_triple.experience_fn.gap = 0.3
    cap.knowledge_triple.experience_fn.score = 0.7
    save_capsule(settings, cap)
    ok, prompt = svc.build_experience_apply_prompt(ExperienceApplyArgs(ecap_id="ecap-triple-1", mode="concise"))
    assert ok
    assert "Instinct refs:" in prompt
    assert "ExperienceFn:" in prompt
    assert "Skill ref:" in prompt


def test_feedback_updates_experience_function_score(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    save_capsule(settings, ExperienceCapsule(ecap_id="ecap-fb-1", title="fb", problem_type="general"))
    svc.experience_feedback(ExperienceFeedbackArgs(ecap_id="ecap-fb-1", result="success", score=0.9, note="ok"))
    one = load_capsule(settings, "ecap-fb-1")
    assert one is not None
    assert one.knowledge_triple.experience_fn.score > 0.0
    assert one.knowledge_triple.experience_fn.gap < 1.0


def test_tecap_role_ecap_and_feedback_updates_team_fn(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    ecap = ExperienceCapsule(ecap_id="ecap-role-1", title="role", problem_type="incident")
    ecap.knowledge_triple.experience_fn.score = 0.8
    save_capsule(settings, ecap)
    tecap = TeamExperienceCapsule(tecap_id="tecap-role-1", title="team", problem_type="incident")
    tecap.participants = [TeamParticipant(agent_id="planner"), TeamParticipant(agent_id="reviewer")]
    tecap.role_ecap_map = {"planner": "ecap-role-1", "reviewer": ""}
    save_team_capsule(settings, tecap)
    ok, prompt = svc.build_team_experience_apply_prompt(
        TeamExperienceApplyArgs(tecap_id="tecap-role-1", mode="concise", explain=True)
    )
    assert ok
    assert "Role ECAP map:" in prompt
    svc.team_experience_feedback(
        TeamExperienceFeedbackArgs(tecap_id="tecap-role-1", result="success", score=0.8, note="good")
    )
    after = load_team_capsule(settings, "tecap-role-1")
    assert after is not None
    assert after.team_experience_fn.score > 0.0
    assert after.team_experience_fn.gap < 1.0


def test_knowledge_evolution_metrics_include_role_coverage(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    ecap = ExperienceCapsule(ecap_id="ecap-k-1", title="k1", problem_type="general")
    ecap.knowledge_triple.experience_fn.gap = 0.2
    ecap.knowledge_triple.experience_fn.score = 0.8
    save_capsule(settings, ecap)
    tecap = TeamExperienceCapsule(tecap_id="tecap-k-1", title="t1", problem_type="general")
    tecap.participants = [TeamParticipant(agent_id="lead"), TeamParticipant(agent_id="dev")]
    tecap.role_ecap_map = {"lead": "ecap-k-1", "dev": ""}
    tecap.team_experience_fn.gap = 0.4
    tecap.team_experience_fn.score = 0.6
    save_team_capsule(settings, tecap)
    rows = svc._knowledge_evolution_metrics()
    assert rows["ecap_count"] == 1
    assert rows["tecap_count"] == 1
    assert rows["role_ecap_coverage"] == 0.5


def test_online_updater_tracks_ci_and_samples() -> None:
    cap = ExperienceCapsule(ecap_id="x")
    fn = cap.knowledge_triple.experience_fn
    fn.score = 0.4
    fn.learning_rate = 0.3
    fn.decay = 0.95
    LearningService._online_update_experience_fn(fn, observed_score=0.9, result="success")
    assert fn.sample_count == 1
    assert 0.0 <= fn.ci_lower <= fn.ci_upper <= 1.0
    assert fn.score > 0.4
    assert fn.effectiveness_level in {"seed", "validated", "trusted", "deprecated"}


def test_tecap_create_inline_role_ecap_map(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    seed = ExperienceCapsule(ecap_id="ecap-inline-1", title="inline", problem_type="incident")
    seed.knowledge_triple.skill_ref.skill_name = "skill-a"
    save_capsule(settings, seed)
    text = svc.create_team_experience(
        TeamExperienceCreateArgs(
            objective="Handle incident",
            problem_type="incident",
            participants="lead,reviewer",
            role_ecap_mode="inline",
        )
    )
    assert "Created TECAP" in text
    tecap_id = text.split("`")[1]
    cap = load_team_capsule(settings, tecap_id)
    assert cap is not None
    assert isinstance(cap.role_ecap_map.get("lead"), dict)
    val = cap.role_ecap_map.get("lead") or {}
    assert isinstance(val, dict)
    assert val.get("mode") == "inline"


def test_experience_feedback_writes_instinct_delta_log(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    cap = ExperienceCapsule(ecap_id="ecap-instinct-1", title="instinct", problem_type="general")
    cap.knowledge_triple.instinct_ref.instinct_ids = ["use-readfile-before-editing"]
    save_capsule(settings, cap)
    svc.experience_feedback(ExperienceFeedbackArgs(ecap_id="ecap-instinct-1", result="success", score=0.8, note="ok"))
    log = settings.ensure_data_directory() / "learning" / "experience" / "instinct_delta.jsonl"
    assert log.exists()
    txt = log.read_text(encoding="utf-8")
    assert "ecap:ecap-instinct-1:success" in txt


def test_experience_tuning_gate_shape(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    cap = ExperienceCapsule(ecap_id="ecap-gate-1", title="g", problem_type="general")
    cap.knowledge_triple.experience_fn.score = 0.8
    cap.knowledge_triple.experience_fn.confidence = 0.8
    cap.knowledge_triple.experience_fn.sample_count = 3
    cap.knowledge_triple.experience_fn.ci_lower = 0.7
    cap.knowledge_triple.experience_fn.ci_upper = 0.85
    save_capsule(settings, cap)
    gate = svc._experience_tuning_gate("general")
    assert "allowed" in gate
    assert "avg_confidence" in gate
    assert "avg_ci_width" in gate


def test_configurable_routing_weights_for_ecap(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.experience_routing_weight_base_score = 1.0
    settings.closed_loop.experience_routing_weight_confidence = 0.0
    settings.closed_loop.experience_routing_weight_model_scope = 0.0
    settings.closed_loop.experience_routing_weight_agent_scope = 0.0
    settings.closed_loop.experience_routing_weight_skill_scope = 0.0
    settings.closed_loop.experience_routing_penalty_risk_gap = 0.0
    settings.closed_loop.experience_routing_penalty_quality_gap = 0.0
    svc = LearningService(settings)
    cap = ExperienceCapsule(ecap_id="ecap-route-1", title="r1", problem_type="general")
    cap.knowledge_triple.experience_fn.score = 0.77
    save_capsule(settings, cap)
    rows = svc.retrieve_capsules(ExperienceApplyArgs(problem_type="general", top_k=1))
    assert rows
    got = float(rows[0].model_profile.capability_profile.get("routing_score", -1.0))
    assert abs(got - 0.77) < 1e-6


def test_configurable_instinct_delta_amplitude(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.experience_instinct_delta_ecap_success = 0.11
    svc = LearningService(settings)
    inst_file = settings.ensure_data_directory() / "learning" / "instincts" / "personal" / "seed.md"
    write_instincts_file(
        inst_file,
        [
            Instinct(
                id="inst-a",
                trigger="when testing",
                confidence=0.4,
                domain="workflow",
                source="test",
                content="x",
            )
        ],
    )
    cap = ExperienceCapsule(ecap_id="ecap-instinct-delta", title="d", problem_type="general")
    cap.knowledge_triple.instinct_ref.instinct_ids = ["inst-a"]
    save_capsule(settings, cap)
    svc.experience_feedback(ExperienceFeedbackArgs(ecap_id="ecap-instinct-delta", result="success", score=0.8, note="ok"))
    txt = inst_file.read_text(encoding="utf-8")
    assert "confidence: 0.51" in txt


def test_configurable_tuning_gate_thresholds(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.experience_tuning_gate_min_confidence = 0.9
    settings.closed_loop.experience_tuning_gate_max_ci_width = 0.1
    settings.closed_loop.experience_tuning_gate_min_samples = 5.0
    svc = LearningService(settings)
    cap = ExperienceCapsule(ecap_id="ecap-gate-cfg", title="g2", problem_type="general")
    cap.knowledge_triple.experience_fn.score = 0.8
    cap.knowledge_triple.experience_fn.confidence = 0.8
    cap.knowledge_triple.experience_fn.sample_count = 3
    cap.knowledge_triple.experience_fn.ci_lower = 0.7
    cap.knowledge_triple.experience_fn.ci_upper = 0.85
    save_capsule(settings, cap)
    gate = svc._experience_tuning_gate("general")
    assert gate["allowed"] is False
    assert gate["thresholds"]["min_confidence"] == 0.9
