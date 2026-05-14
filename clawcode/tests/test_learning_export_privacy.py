from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.learning.params import ExportArgs
from clawcode.learning.service import LearningService


def test_export_privacy_and_formats(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    src = settings.get_data_directory() / "learning" / "instincts" / "personal" / "seed.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        "---\n"
        "id: redact-sensitive\n"
        "trigger: \"when sharing\"\n"
        "confidence: 0.8\n"
        "domain: workflow\n"
        "source: session-observation\n"
        "---\n\n"
        "## Action\nRemove tokens from https://x.dev?token=abc and /home/user/repo/file.py\n\n"
        "## Evidence\nuser@example.com hit this path.\n",
        encoding="utf-8",
    )

    out_json = tmp_path / "instincts.json"
    msg = svc.export_instincts_advanced(
        ExportArgs(output=str(out_json), format="json", include_evidence=False)
    )
    assert "Exported" in msg
    txt = out_json.read_text(encoding="utf-8")
    assert "[REDACTED]" in txt or "[PATH]" in txt
    assert "## Evidence" not in txt

    out_yaml = tmp_path / "instincts.yaml"
    svc.export_instincts_advanced(ExportArgs(output=str(out_yaml), format="yaml", include_evidence=True))
    assert out_yaml.exists()
