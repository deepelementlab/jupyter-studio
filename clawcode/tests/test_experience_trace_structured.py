from __future__ import annotations

from clawcode.learning.experience_builder import build_experience_capsule
from clawcode.learning.models import Instinct


def test_structured_trace_in_builder() -> None:
    obs = [{"tool": "ReadFile"}, {"tool": "Edit"}, {"tool": "ReadFile"}]
    cap = build_experience_capsule(
        observations=obs,
        instincts=[
            Instinct(
                id="i1",
                trigger="when editing",
                confidence=0.8,
                domain="workflow",
                source="session-observation",
                content="## Action\nA",
            )
        ],
        session_id="s1",
    )
    assert cap.solution_trace.steps
    assert hasattr(cap.solution_trace.steps[0], "step_type")
    assert cap.solution_trace.tool_sequence
    assert hasattr(cap.solution_trace.tool_sequence[0], "tool_name")
