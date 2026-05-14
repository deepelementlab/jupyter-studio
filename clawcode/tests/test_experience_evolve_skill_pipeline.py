from __future__ import annotations

from pathlib import Path

from clawcode.claw_learning.experience_tools import import_evolved_skills_to_store
from clawcode.config.settings import Settings
from clawcode.learning.analyzer import build_clusters
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_store import save_capsule
from clawcode.learning.models import Instinct
from clawcode.learning.params import EvolveArgs
from clawcode.learning.service import LearningService
from clawcode.learning.store import write_instincts_file


class _StubSkillStore:
    def __init__(self) -> None:
        self._content: dict[str, str] = {}

    def view_skill(self, name: str, file_path: str | None = None) -> dict[str, object]:
        if name not in self._content:
            return {"success": False, "error": "not found"}
        return {"success": True, "content": self._content[name]}

    def create_skill(self, name: str, content: str, category: str | None = None, *, why: str = "") -> dict[str, object]:
        self._content[name] = content
        return {"success": True}

    def edit_skill(self, name: str, content: str, *, why: str = "") -> dict[str, object]:
        self._content[name] = content
        return {"success": True}


def test_experience_gate_blocks_low_confidence_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.evolve_experience_gate_enabled = True
    settings.closed_loop.evolve_experience_gate_min_score = 0.7
    settings.closed_loop.evolve_experience_gate_min_confidence = 0.8
    svc = LearningService(settings)
    skill_dir = settings.get_data_directory() / "learning" / "evolved" / "skills" / "skill-a"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# skill-a\n", encoding="utf-8")
    cap = ExperienceCapsule(ecap_id="ecap-skill-a", title="x", problem_type="general")
    cap.knowledge_triple.skill_ref.skill_name = "skill-a"
    cap.knowledge_triple.experience_fn.score = 0.4
    cap.knowledge_triple.experience_fn.confidence = 0.3
    cap.knowledge_triple.experience_fn.ci_lower = 0.1
    cap.knowledge_triple.experience_fn.ci_upper = 0.9
    cap.knowledge_triple.experience_fn.sample_count = 1
    save_capsule(settings, cap)
    out = import_evolved_skills_to_store(svc, _StubSkillStore(), limit=5)
    assert out["summary"]["gated_by_experience_count"] == 1
    assert any(r.get("status") == "gated_by_experience" for r in out["rows"])


def test_experience_gate_allows_trusted_skill(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.evolve_experience_gate_enabled = True
    settings.closed_loop.evolve_experience_gate_min_score = 0.6
    settings.closed_loop.evolve_experience_gate_min_confidence = 0.5
    settings.closed_loop.evolve_experience_gate_max_ci_width = 0.3
    settings.closed_loop.evolve_experience_gate_min_samples = 2
    svc = LearningService(settings)
    skill_dir = settings.get_data_directory() / "learning" / "evolved" / "skills" / "skill-b"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# skill-b\n", encoding="utf-8")
    cap = ExperienceCapsule(ecap_id="ecap-skill-b", title="x", problem_type="general")
    cap.knowledge_triple.skill_ref.skill_name = "skill-b"
    cap.knowledge_triple.experience_fn.score = 0.8
    cap.knowledge_triple.experience_fn.confidence = 0.8
    cap.knowledge_triple.experience_fn.ci_lower = 0.7
    cap.knowledge_triple.experience_fn.ci_upper = 0.85
    cap.knowledge_triple.experience_fn.sample_count = 3
    save_capsule(settings, cap)
    out = import_evolved_skills_to_store(svc, _StubSkillStore(), limit=5)
    assert out["summary"]["created"] == 1
    assert out["summary"]["gated_by_experience_count"] == 0


def test_evolve_skill_md_contains_experience_section(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.evolve_experience_enrich_skill_md_enabled = True
    svc = LearningService(settings)
    inst_file = settings.get_data_directory() / "learning" / "instincts" / "personal" / "seed.md"
    write_instincts_file(
        inst_file,
        [
            Instinct("i1", "when modifying code", 0.8, "general", "test", "one"),
            Instinct("i2", "when modifying code", 0.7, "general", "test", "two"),
            Instinct("i3", "when modifying code", 0.9, "general", "test", "three"),
        ],
    )
    cap = ExperienceCapsule(ecap_id="ecap-enrich", title="z", problem_type="general")
    cap.knowledge_triple.instinct_ref.instinct_ids = ["i1", "i2"]
    cap.knowledge_triple.experience_fn.score = 0.8
    cap.knowledge_triple.experience_fn.confidence = 0.75
    save_capsule(settings, cap)
    msg = svc.evolve_advanced(EvolveArgs(execute=True, dry_run=False, threshold=2))
    assert "Generated" in msg
    skill_files = list((settings.get_data_directory() / "learning" / "evolved" / "skills").rglob("SKILL.md"))
    assert skill_files
    txt = skill_files[0].read_text(encoding="utf-8")
    assert "## Experience Summary" in txt


def test_weighted_cluster_fallback_without_experience() -> None:
    instincts = [
        Instinct("a", "when coding", 0.5, "general", "t", "x"),
        Instinct("b", "when coding", 0.5, "general", "t", "x"),
        Instinct("c", "when coding", 0.5, "general", "t", "x"),
    ]
    rows = build_clusters(
        instincts,
        threshold=2,
        weighted_cluster_enabled=True,
        weight_trigger=1.0,
        weight_similarity=0.5,
        weight_consistency=0.5,
        instinct_experience_scores={},
    )
    assert rows
    assert rows[0].experience_score == 0.0


def test_weighted_cluster_promotes_high_effectiveness_group() -> None:
    instincts = [
        Instinct("a1", "when coding", 0.6, "general", "t", "x"),
        Instinct("a2", "when coding", 0.6, "general", "t", "x"),
        Instinct("b1", "when testing", 0.6, "general", "t", "x"),
        Instinct("b2", "when testing", 0.6, "general", "t", "x"),
    ]
    rows = build_clusters(
        instincts,
        threshold=2,
        weighted_cluster_enabled=True,
        weight_trigger=1.0,
        weight_similarity=2.0,
        weight_consistency=0.0,
        instinct_experience_scores={"a1": 0.9, "a2": 0.9, "b1": 0.1, "b2": 0.1},
    )
    assert rows
    assert rows[0].key == "coding"
