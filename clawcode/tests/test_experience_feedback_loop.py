from __future__ import annotations

from clawcode.config.settings import Settings
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_params import ExperienceFeedbackArgs
from clawcode.learning.experience_store import load_capsule, save_capsule
from clawcode.learning.service import LearningService


def test_feedback_updates_capsule_state(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    save_capsule(settings, ExperienceCapsule(ecap_id="fb1", title="fb", problem_type="debug"))
    msg = svc.experience_feedback(
        ExperienceFeedbackArgs(ecap_id="fb1", result="fail", score=0.1, note="bad transfer")
    )
    assert "Recorded feedback" in msg
    one = load_capsule(settings, "fb1")
    assert one is not None
    assert one.governance.feedback_count >= 1
    assert one.transfer.anti_patterns
