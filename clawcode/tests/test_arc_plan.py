from __future__ import annotations

from unittest.mock import MagicMock, patch

from clawcode.config.settings import Settings
from clawcode.tui.screens.chat import ChatScreen


def test_arc_plan_pending_wraps_prompt_and_enables_plan_mode() -> None:
    """When PlanSessionState.mode == arc_plan_pending, we must:
    - enable plan_mode (is_plan_run=True)
    - wrap the agent prompt with the ARC planner template
    """

    screen = ChatScreen(Settings())
    session_id = "sess-arc-plan"
    screen.current_session_id = session_id

    ps = screen._get_plan_state(session_id, create=True)
    assert ps is not None
    ps.mode = "arc_plan_pending"

    input_widget = MagicMock()

    with (
        patch.object(screen, "query_one", side_effect=Exception("skip panel")),
        patch.object(screen, "_start_agent_run") as start_agent_run,
    ):
        screen._finalize_send_after_input(
            display_content="need an API",
            raw_content_for_plan="need an API",
            content_for_agent="need an API",
            attachments=[],
            input_widget=input_widget,
            skip_plan_wrap=False,
        )

    assert start_agent_run.call_count == 1
    kwargs = start_agent_run.call_args.kwargs
    assert kwargs["is_plan_run"] is True

    wrapped = kwargs["content_for_agent"]
    assert "## Your Role" in wrapped
    assert "Worked Example: Adding Stripe Subscriptions" in wrapped
    assert "Do NOT write or modify any code." in wrapped
    assert "## Implementation Steps" in wrapped
    assert "## Testing Strategy" in wrapped
    assert "## Risks" in wrapped

    assert ps.last_user_request == "need an API"

