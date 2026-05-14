from __future__ import annotations

from clawcode.learning.ecap_privacy import sanitize_ecap
from clawcode.learning.experience_models import ExperienceCapsule, ExperienceStep


def test_privacy_sanitize_strict() -> None:
    cap = ExperienceCapsule(ecap_id="e1", title="t", problem_type="general")
    cap.context.repo_fingerprint = "/home/user/repo?token=abc"
    cap.solution_trace.steps = [
        ExperienceStep(
            summary="see /tmp/a.py and email me@test.com token=abc",
            params_summary="token=abc",
        )
    ]
    out = sanitize_ecap(cap, level="strict")
    assert out.context.repo_fingerprint == ""
    assert (
        "[EMAIL]" in out.solution_trace.steps[0].summary
        or "[REDACTED]" in out.solution_trace.steps[0].summary
        or "[PATH]" in out.solution_trace.steps[0].summary
    )
