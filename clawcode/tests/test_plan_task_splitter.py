from __future__ import annotations

from clawcode.llm.plan_store import PlanTaskItem
from clawcode.llm.plan_tasks import compose_task_execution_prompt, split_plan_to_tasks


def test_split_plan_to_tasks_from_bullets() -> None:
    plan = """
## Steps
- Add plan store bundle
- Add right panel
- Add tests
"""
    tasks = split_plan_to_tasks(plan)
    assert len(tasks) >= 3
    assert tasks[0].title == "Add plan store bundle"


def test_split_plan_to_tasks_fallback() -> None:
    tasks = split_plan_to_tasks("plain paragraph without bullets")
    assert len(tasks) >= 1
    assert tasks[0].status == "pending"


def test_compose_task_execution_prompt() -> None:
    task = PlanTaskItem(id="task-1", title="Implement parser", details="touch only parser module")
    prompt = compose_task_execution_prompt("# Plan", task)
    assert "Current task" in prompt
    assert "Implement parser" in prompt
