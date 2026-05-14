from __future__ import annotations

from clawcode.learning.ecap_serializer import to_ecap_json
from clawcode.learning.experience_models import ExperienceCapsule


def test_experience_privacy_metadata_present() -> None:
    cap = ExperienceCapsule(ecap_id="ecap-p1", title="Privacy", problem_type="general")
    cap.governance.privacy_level = "balanced"
    cap.governance.redaction_applied = True
    txt = to_ecap_json(cap)
    assert "privacy_level" in txt
    assert "redaction_applied" in txt
