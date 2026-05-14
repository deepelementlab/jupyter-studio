from __future__ import annotations

import json
from pathlib import Path

from clawcode.config.settings import Settings
from clawcode.learning.params import StatusArgs
from clawcode.learning.service import LearningService


def _seed_instincts(path: Path) -> None:
    path.write_text(
        "---\n"
        "id: keep-functional\n"
        "trigger: \"when writing functions\"\n"
        "confidence: 0.82\n"
        "domain: code-style\n"
        "source: session-observation\n"
        "---\n\n"
        "## Action\nPrefer functional patterns.\n\n"
        "---\n"
        "id: use-tests-first\n"
        "trigger: \"when adding feature\"\n"
        "confidence: 0.45\n"
        "domain: testing\n"
        "source: inherited\n"
        "---\n\n"
        "## Action\nWrite tests first.\n",
        encoding="utf-8",
    )


def test_status_filters_and_json_output(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    p = settings.get_data_directory() / "learning" / "instincts" / "personal" / "seed.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    _seed_instincts(p)

    txt = svc.status_text(StatusArgs(domain="testing", low_confidence=True))
    assert "use-tests-first" in txt
    assert "keep-functional" not in txt

    j = svc.status_text(StatusArgs(as_json=True, high_confidence=True))
    obj = json.loads(j)
    assert obj["total"] >= 1
    ids = {x["id"] for x in obj["instincts"]}
    assert "keep-functional" in ids
