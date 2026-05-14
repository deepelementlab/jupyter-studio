from __future__ import annotations

from clawcode.config.settings import Settings
from clawcode.learning.service import LearningService
from clawcode.learning.store import record_tool_observation


def test_observer_consumes_incremental_observations(tmp_path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    svc = LearningService(settings)
    for i in range(3):
        record_tool_observation(
            settings,
            phase="tool_complete",
            session_id="s1",
            tool_name="ReadFile",
            tool_call_id=f"tc{i}",
            tool_input={"path": "a.py"},
            tool_output="ok",
            is_error=False,
        )
    msg1 = svc.run_observer_once(max_rows=10)
    assert "processed 3" in msg1.lower()
    msg2 = svc.run_observer_once(max_rows=10)
    assert "no new observations" in msg2.lower()
