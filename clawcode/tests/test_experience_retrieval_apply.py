from __future__ import annotations

from clawcode.config.settings import Settings
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_params import ExperienceApplyArgs
from clawcode.learning.experience_store import save_capsule
from clawcode.learning.service import LearningService


def test_retrieval_apply_top_k(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    c1 = ExperienceCapsule(ecap_id="r1", title="A", problem_type="debug")
    c1.model_profile.source_model = "gpt-a"
    c1.governance.feedback_score = 0.2
    save_capsule(settings, c1)
    c2 = ExperienceCapsule(ecap_id="r2", title="B", problem_type="debug")
    c2.model_profile.source_model = "gpt-b"
    c2.governance.feedback_score = 0.9
    save_capsule(settings, c2)

    rows = svc.retrieve_capsules(ExperienceApplyArgs(problem_type="debug", top_k=1))
    assert len(rows) == 1
    assert rows[0].ecap_id == "r2"

    ok, prompt = svc.build_experience_apply_prompt(
        ExperienceApplyArgs(problem_type="debug", top_k=1, mode="concise")
    )
    assert ok
    assert "ECAP: r2" in prompt
