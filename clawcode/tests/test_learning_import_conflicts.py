from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.learning.params import ImportArgs
from clawcode.learning.service import LearningService


def test_import_merge_strategy_and_conflict_skip(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)

    personal = settings.get_data_directory() / "learning" / "instincts" / "personal" / "base.md"
    personal.parent.mkdir(parents=True, exist_ok=True)
    personal.write_text(
        "---\n"
        "id: prefer-functional\n"
        "trigger: \"when coding\"\n"
        "confidence: 0.70\n"
        "domain: code-style\n"
        "source: session-observation\n"
        "---\n\n"
        "## Action\nPrefer functional style.\n",
        encoding="utf-8",
    )

    incoming = tmp_path / "incoming.md"
    incoming.write_text(
        "---\n"
        "id: prefer-functional\n"
        "trigger: \"when coding\"\n"
        "confidence: 0.91\n"
        "domain: code-style\n"
        "source: inherited\n"
        "---\n\n"
        "## Action\nPrefer functional style.\n\n"
        "---\n"
        "id: avoid-functional\n"
        "trigger: \"when coding\"\n"
        "confidence: 0.88\n"
        "domain: code-style\n"
        "source: inherited\n"
        "---\n\n"
        "## Action\nAvoid functional style.\n",
        encoding="utf-8",
    )

    msg = svc.import_instincts_advanced(
        ImportArgs(source=str(incoming), force=True, merge_strategy="higher")
    )
    assert "updated 1" in msg.lower() or "updated: 1" in msg.lower() or "updated 1," in msg.lower()
    assert "conflict-skip" in msg
