from __future__ import annotations

from clawcode.claw_learning.ops_observability import summarize_clawteam_deeploop_events


def test_summarize_clawteam_deeploop_events_basic() -> None:
    events = [
        {
            "event_type": "clawteam_iteration_completed",
            "payload": {"gap_delta": -0.1, "handoff_success_rate": 0.9},
        },
        {
            "event_type": "clawteam_iteration_completed",
            "payload": {"gap_delta": 0.2, "handoff_success_rate": 0.7},
        },
        {
            "event_type": "clawteam_deeploop_decision",
            "payload": {"decision": "continue"},
        },
        {
            "event_type": "clawteam_deeploop_decision",
            "payload": {"decision": "stop"},
        },
    ]
    s = summarize_clawteam_deeploop_events(events)
    assert s["schema_version"] == "clawteam-deeploop-events-summary-v1"
    assert s["iteration_count"] == 2
    assert abs(s["avg_abs_gap_delta"] - 0.15) < 1e-6
    assert s["handoff_success_series"] == [0.9, 0.7]
    assert s["decision_counts"] == {"continue": 1, "stop": 1}
