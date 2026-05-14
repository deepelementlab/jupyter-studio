from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_store import export_capsule, list_capsules, load_capsule, save_capsule


def test_experience_store_save_list_load_export(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    cap = ExperienceCapsule(
        ecap_id="ecap-test-1",
        title="Test Capsule",
        problem_type="debug",
    )
    p = save_capsule(settings, cap)
    assert p.exists()
    rows = list_capsules(settings)
    assert any(x.ecap_id == "ecap-test-1" for x in rows)
    one = load_capsule(settings, "ecap-test-1")
    assert one is not None
    assert one.title == "Test Capsule"
    out = export_capsule(settings, one, fmt="md")
    assert out.exists()
