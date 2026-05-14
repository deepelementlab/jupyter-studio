from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Provider, Settings
from clawcode.tui.multi_execute_workflow import (
    MultiExecuteArgs,
    build_execute_context,
    build_execute_prompt,
    build_model_assignment,
)


def test_build_execute_context_plan_file_mode(tmp_path: Path) -> None:
    plan = tmp_path / "a.plan.md"
    plan.write_text(
        "## Technical Solution\n"
        "Backend API and UI updates\n\n"
        "## Implementation Steps\n"
        "1. Add endpoint\n2. Update frontend\n",
        encoding="utf-8",
    )
    ctx = build_execute_context(request="", from_plan_path=str(plan), root=tmp_path)
    assert ctx["input_mode"] == "plan-file"
    assert ctx["task_type"] == "fullstack"
    assert "implementation steps" in ctx["plan_sections"]


def test_build_model_assignment_respects_disabled_provider() -> None:
    settings = Settings()
    settings.providers = {
        "openai_deepseek": Provider(disabled=True, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    args = MultiExecuteArgs(request="build backend", strategy="balanced")
    meta = build_model_assignment(settings, args, coder_model="glm-5")
    pool_ids = {x["model_id"] for x in meta["discovered_pool"]}
    assert "deepseek-chat" not in pool_ids
    assert "glm-5" in pool_ids


def test_build_execute_prompt_contains_required_sections() -> None:
    settings = Settings()
    settings.providers = {
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    args = MultiExecuteArgs(request="implement retries", strategy="balanced")
    ctx = build_execute_context(request=args.request, root=Path("."))
    assign = build_model_assignment(settings, args, coder_model="glm-5")
    prompt = build_execute_prompt(ctx, assign, args)
    assert "## Multi-Execute Result" in prompt
    assert "## Audit Summary" in prompt
    assert "Execution protocol" in prompt

