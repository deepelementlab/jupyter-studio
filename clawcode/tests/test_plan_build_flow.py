from __future__ import annotations

from clawcode.llm.plan_store import PlanBundle, PlanExecutionState, PlanTaskItem
from clawcode.tui.screens.chat import ChatScreen


def test_plan_bundle_execution_state_defaults() -> None:
    bundle = PlanBundle(
        session_id="s",
        user_request="u",
        plan_text="p",
        created_at=1,
        markdown_path="a.md",
        json_path="a.json",
        tasks=[PlanTaskItem(id="task-1", title="A")],
        execution=PlanExecutionState(),
    )
    assert bundle.execution.is_building is False
    assert bundle.execution.current_task_index == -1


def test_plan_task_status_progression() -> None:
    task = PlanTaskItem(id="task-1", title="A")
    assert task.status == "pending"
    task.status = "in_progress"
    task.status = "completed"
    assert task.status == "completed"


def test_plan_execution_state_extended_fields_defaults() -> None:
    st = PlanExecutionState()
    assert st.last_progress_at == 0
    assert st.stall_count == 0
    assert st.last_error == ""
    assert st.interrupted is False
    assert st.retry_count_by_task == {}


def test_plan_bundle_from_dict_backward_compatible_execution() -> None:
    raw = {
        "session_id": "s",
        "user_request": "u",
        "plan_text": "p",
        "created_at": 1,
        "markdown_path": "a.md",
        "json_path": "a.json",
        "tasks": [{"id": "task-1", "title": "A", "status": "pending"}],
        "execution": {
            "is_building": True,
            "current_task_index": 0,
            "started_at": 2,
            "finished_at": 0,
        },
    }
    b = PlanBundle.from_dict(raw)
    assert b.execution.is_building is True
    assert b.execution.current_task_index == 0
    assert b.execution.last_progress_at == 0
    assert b.execution.retry_count_by_task == {}


def test_plan_bundle_from_dict_reads_retry_counter_map() -> None:
    raw = {
        "session_id": "s",
        "user_request": "u",
        "plan_text": "p",
        "created_at": 1,
        "markdown_path": "a.md",
        "json_path": "a.json",
        "tasks": [{"id": "task-1", "title": "A", "status": "failed"}],
        "execution": {
            "is_building": False,
            "current_task_index": 0,
            "last_progress_at": 7,
            "stall_count": 1,
            "last_error": "boom",
            "interrupted": True,
            "retry_count_by_task": {"task-1": 2, "bad": "x"},
        },
    }
    b = PlanBundle.from_dict(raw)
    assert b.execution.last_progress_at == 7
    assert b.execution.stall_count == 1
    assert b.execution.last_error == "boom"
    assert b.execution.interrupted is True
    assert b.execution.retry_count_by_task == {"task-1": 2}


def test_plan_execution_reconcile_clears_stale_is_building_when_all_done() -> None:
    bundle = PlanBundle(
        session_id="s",
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="a.md",
        json_path="a.json",
        tasks=[
            PlanTaskItem(id="task-1", title="A", status="completed"),
            PlanTaskItem(id="task-2", title="B", status="completed"),
        ],
        execution=PlanExecutionState(
            is_building=True,
            current_task_index=1,
            finished_at=0,
        ),
    )
    changed, show_bubble = ChatScreen._plan_execution_reconcile_inplace(bundle)
    assert changed is True
    assert show_bubble is True
    assert bundle.execution.is_building is False
    assert bundle.execution.current_task_index == -1
    assert bundle.execution.finished_at > 0
    assert ChatScreen._is_plan_build_completed(bundle) is True


def test_plan_execution_reconcile_noop_when_still_in_progress() -> None:
    bundle = PlanBundle(
        session_id="s",
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="a.md",
        json_path="a.json",
        tasks=[
            PlanTaskItem(id="task-1", title="A", status="completed"),
            PlanTaskItem(id="task-2", title="B", status="in_progress"),
        ],
        execution=PlanExecutionState(is_building=True, current_task_index=1),
    )
    changed, _ = ChatScreen._plan_execution_reconcile_inplace(bundle)
    assert changed is False
    assert bundle.execution.is_building is True


def test_stall_timeout_uses_reasoner_profile() -> None:
    assert ChatScreen._stall_timeout_for_model("deepseek-reasoner") == ChatScreen._BUILD_STALL_TIMEOUT_REASONER_S
    assert ChatScreen._stall_timeout_for_model("deepseek-r1") == ChatScreen._BUILD_STALL_TIMEOUT_REASONER_S
    assert ChatScreen._stall_timeout_for_model("kimi-k2.5") == ChatScreen._BUILD_STALL_TIMEOUT_REASONER_S
    assert ChatScreen._stall_timeout_for_model("qwq-32b-preview") == ChatScreen._BUILD_STALL_TIMEOUT_REASONER_S
    assert ChatScreen._stall_timeout_for_model("qvq-72b-preview") == ChatScreen._BUILD_STALL_TIMEOUT_REASONER_S
    assert ChatScreen._stall_timeout_for_model("gpt-4o-mini") == ChatScreen._BUILD_STALL_TIMEOUT_S
