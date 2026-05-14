"""Tests for `/orchestrate` workflow parsing and prompt building."""

from __future__ import annotations

from clawcode.tui.orchestrate_workflow import (
    WORKFLOW_CHAINS,
    build_orchestrate_prompt,
    parse_orchestrate_args,
)


def test_workflow_chains_match_plan() -> None:
    assert WORKFLOW_CHAINS["feature"] == [
        "planner",
        "tdd-guide",
        "code-reviewer",
        "security-reviewer",
    ]
    assert WORKFLOW_CHAINS["bugfix"] == ["planner", "tdd-guide", "code-reviewer"]
    assert WORKFLOW_CHAINS["refactor"] == ["architect", "code-reviewer", "tdd-guide"]
    assert WORKFLOW_CHAINS["security"] == ["security-reviewer", "code-reviewer", "architect"]


def test_parse_feature_quoted_task() -> None:
    o, err = parse_orchestrate_args('feature "Add auth"')
    assert err == ""
    assert o is not None
    assert o.show_list == ""
    assert o.workflow == "feature"
    assert o.agents == WORKFLOW_CHAINS["feature"]
    assert o.task == "Add auth"


def test_parse_custom_agents_and_task() -> None:
    o, err = parse_orchestrate_args('custom architect,tdd-guide "Refactor X"')
    assert err == ""
    assert o is not None
    assert o.workflow == "custom"
    assert o.agents == ["architect", "tdd-guide"]
    assert o.task == "Refactor X"


def test_parse_custom_unknown_agent() -> None:
    o, err = parse_orchestrate_args('custom bad-agent "task"')
    assert o is None
    assert "Unknown agent" in err


def test_parse_show_list() -> None:
    o, err = parse_orchestrate_args("show")
    assert err == ""
    assert o is not None
    assert o.show_list == "show"
    o2, err2 = parse_orchestrate_args("list")
    assert err2 == ""
    assert o2 is not None
    assert o2.show_list == "list"


def test_build_orchestrate_prompt_contains_handoff_and_report() -> None:
    p = build_orchestrate_prompt(
        workflow="feature",
        agents=WORKFLOW_CHAINS["feature"],
        task="Ship login",
    )
    assert "## HANDOFF:" in p
    assert "ORCHESTRATION REPORT" in p
    assert "planner -> tdd-guide" in p or "planner" in p
    assert "Ship login" in p
