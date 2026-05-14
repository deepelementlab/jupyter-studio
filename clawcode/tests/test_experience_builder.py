from __future__ import annotations

from clawcode.learning.experience_builder import build_experience_capsule
from clawcode.learning.models import Instinct


def test_experience_builder_generates_capsule() -> None:
    observations = [
        {"tool": "ReadFile", "is_error": False},
        {"tool": "Shell", "is_error": False},
        {"tool": "Edit", "is_error": False},
    ]
    instincts = [
        Instinct(
            id="grep-before-edit",
            trigger="when modifying code",
            confidence=0.8,
            domain="workflow",
            source="session-observation",
            content="## Action\nSearch first.",
        )
    ]
    cap = build_experience_capsule(
        observations=observations,
        instincts=instincts,
        session_id="s1",
        source_provider="openai",
        source_model="gpt-x",
        reasoning_effort="high",
    )
    assert cap.ecap_id
    assert cap.solution_trace.tool_sequence
    assert cap.links.related_instinct_ids == ["grep-before-edit"]
