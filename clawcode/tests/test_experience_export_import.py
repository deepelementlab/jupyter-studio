from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.learning.experience_models import ExperienceCapsule
from clawcode.learning.experience_params import ExperienceExportArgs, ExperienceImportArgs
from clawcode.learning.experience_store import load_capsule, save_capsule
from clawcode.learning.service import LearningService


def test_experience_export_import(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    save_capsule(
        settings,
        ExperienceCapsule(ecap_id="ecap-exp-1", title="ExportTest", problem_type="review"),
    )
    msg = svc.experience_export(ExperienceExportArgs(ecap_id="ecap-exp-1", format="json"))
    assert "Exported" in msg
    exported = settings.get_data_directory() / "learning" / "experience" / "exports" / "ecap-exp-1.json"
    assert exported.exists()
    msg2 = svc.experience_import(ExperienceImportArgs(source=str(exported), force=True))
    assert "Imported" in msg2 or "already exists" in msg2 or "failed" not in msg2.lower()
    assert load_capsule(settings, "ecap-exp-1") is not None
