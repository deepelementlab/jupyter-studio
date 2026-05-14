from __future__ import annotations

from clawcode.learning.ecap_migration import upgrade_ecap_v1_to_v2


def test_upgrade_v1_to_v2_keeps_compat() -> None:
    v1 = {
        "schema_version": "ecap-v1",
        "ecap_id": "ecap-old-1",
        "title": "Old",
        "problem_type": "debug",
        "context": {"repo_fingerprint": "abc"},
        "model_profile": {"source_provider": "openai", "source_model": "gpt"},
        "solution_trace": {"steps": ["do A", "do B"], "tool_sequence": ["ReadFile", "Edit"]},
        "outcome": {"result": "success"},
        "transfer": {"target_model_hints": ["hint"]},
        "links": {"related_instinct_ids": ["i1"]},
        "governance": {"privacy_level": "balanced"},
    }
    cap = upgrade_ecap_v1_to_v2(v1)
    assert cap.schema_version == "ecap-v3"
    assert cap.solution_trace.steps
    assert cap.solution_trace.steps[0].summary == "do A"
    assert cap.knowledge_triple.experience_fn.fn_type == "weighted_gap_v1"
