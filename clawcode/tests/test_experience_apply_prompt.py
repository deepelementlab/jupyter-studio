from __future__ import annotations

from clawcode.config.settings import Settings
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_params import ExperienceApplyArgs
from clawcode.learning.experience_store import save_capsule
from clawcode.learning.service import LearningService


def test_experience_apply_prompt_modes(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    save_capsule(
        settings,
        ExperienceCapsule(
            ecap_id="ecap-apply-1",
            title="ApplyTest",
            problem_type="debug",
        ),
    )
    ok, concise = svc.build_experience_apply_prompt(ExperienceApplyArgs(ecap_id="ecap-apply-1", mode="concise"))
    assert ok
    assert "ECAP" in concise
    ok2, full = svc.build_experience_apply_prompt(ExperienceApplyArgs(ecap_id="ecap-apply-1", mode="full"))
    assert ok2
    assert "ecap_id" in full
