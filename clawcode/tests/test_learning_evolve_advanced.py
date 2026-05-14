from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.learning.params import EvolveArgs
from clawcode.learning.service import LearningService


def test_evolve_advanced_threshold_type_and_execute(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    src = settings.get_data_directory() / "learning" / "instincts" / "personal" / "seed.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        "---\n"
        "id: wf-a\ntrigger: \"when modifying code\"\nconfidence: 0.8\ndomain: workflow\nsource: session-observation\n---\n\n## Action\nA\n\n"
        "---\n"
        "id: wf-b\ntrigger: \"when modifying code\"\nconfidence: 0.78\ndomain: workflow\nsource: session-observation\n---\n\n## Action\nB\n\n"
        "---\n"
        "id: wf-c\ntrigger: \"when modifying code\"\nconfidence: 0.81\ndomain: workflow\nsource: session-observation\n---\n\n## Action\nC\n",
        encoding="utf-8",
    )

    preview = svc.evolve_advanced(EvolveArgs(threshold=3, evolve_type="command", dry_run=True))
    assert "candidate cluster" in preview.lower()
    done = svc.evolve_advanced(EvolveArgs(threshold=3, evolve_type="command", execute=True))
    assert "Generated" in done
