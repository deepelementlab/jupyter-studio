"""Unit tests for `/multi-workflow` routing meta and prompt builder."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Provider, Settings
from clawcode.tui.multi_plan_routing import MultiPlanRoutingArgs, build_routing_plan
from clawcode.tui.multi_workflow import build_fullstack_routing_meta, build_multi_workflow_prompt


def test_build_fullstack_routing_meta_adds_workflow_and_stages(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
        "gemini_google": Provider(disabled=False, models=["gemini-2.0-flash"]),
    }
    args = MultiPlanRoutingArgs(requirement="full stack feature", strategy="balanced")
    meta = build_fullstack_routing_meta(settings, args, coder_model="claude-opus-4")
    assert meta["workflow"] == "fullstack"
    for stage in ("backend_analysis", "frontend_analysis", "synthesis"):
        assert stage in meta["selected_by_stage"]
        assert meta["selected_by_stage"][stage].get("model_id")


def test_build_fullstack_routing_meta_extends_routing_plan(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    args = MultiPlanRoutingArgs(requirement="x")
    base = build_routing_plan(settings, args, coder_model="glm-5")
    via = build_fullstack_routing_meta(settings, args, coder_model="glm-5")
    assert via["workflow"] == "fullstack"
    base_dict = dict(base)
    base_dict["workflow"] = "fullstack"
    assert via == base_dict


def test_build_fullstack_routing_respects_disabled_provider(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "openai_deepseek": Provider(disabled=True, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    args = MultiPlanRoutingArgs(requirement="task")
    meta = build_fullstack_routing_meta(settings, args, coder_model="glm-5")
    pool_ids = {e["model_id"] for e in meta["discovered_pool"]}
    assert "deepseek-chat" not in pool_ids
    assert "glm-5" in pool_ids


def test_build_multi_workflow_prompt_research_rubric_and_parallel_phases() -> None:
    routing_meta = {
        "workflow": "fullstack",
        "strategy": "balanced",
        "selected_by_stage": {
            "backend_analysis": {"model_id": "m1", "provider_key": "p1"},
            "frontend_analysis": {"model_id": "m2", "provider_key": "p2"},
        },
    }
    prompt = build_multi_workflow_prompt("ship cart", routing_meta, audit_on=False)
    assert "Scope boundaries" in prompt
    assert "MCP or tool" in prompt or "MCP" in prompt
    assert "Phase 2 Ideation" in prompt
    assert "wait for both" in prompt.lower()
    assert "ship cart" in prompt
