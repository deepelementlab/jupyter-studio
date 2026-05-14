"""Unit tests for `/multi-frontend` routing meta and prompt builder."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Provider, Settings
from clawcode.tui.multi_frontend_workflow import build_frontend_routing_meta, build_multi_frontend_prompt
from clawcode.tui.multi_plan_routing import MultiPlanRoutingArgs, build_frontend_routing_plan


def test_build_frontend_routing_plan_has_workflow_and_stages(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
        "gemini_google": Provider(disabled=False, models=["gemini-2.0-flash"]),
    }
    args = MultiPlanRoutingArgs(requirement="dashboard cards", strategy="balanced")
    meta = build_frontend_routing_plan(settings, args, coder_model="claude-opus-4")
    assert meta["workflow"] == "frontend"
    for stage in ("frontend_authority", "auxiliary_reference", "frontend_synthesis"):
        assert stage in meta["selected_by_stage"]
        assert meta["selected_by_stage"][stage].get("model_id")
    assert meta["selected_by_stage"]["frontend_authority"]["model_id"] == "gemini-2.0-flash"


def test_build_frontend_routing_meta_matches_plan(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "gemini_google": Provider(disabled=False, models=["gemini-2.0-flash"]),
    }
    args = MultiPlanRoutingArgs(requirement="x")
    direct = build_frontend_routing_plan(settings, args, coder_model="gemini-2.0-flash")
    via = build_frontend_routing_meta(settings, args, coder_model="gemini-2.0-flash")
    assert via == direct


def test_build_frontend_routing_respects_disabled_provider(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "gemini_google": Provider(disabled=True, models=["gemini-2.0-flash"]),
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
    }
    args = MultiPlanRoutingArgs(requirement="task")
    meta = build_frontend_routing_meta(settings, args, coder_model="claude-opus-4")
    pool_ids = {e["model_id"] for e in meta["discovered_pool"]}
    assert "gemini-2.0-flash" not in pool_ids
    assert "claude-opus-4" in pool_ids


def test_build_multi_frontend_prompt_contains_execute_a11y_and_orchestrator() -> None:
    routing_meta = {
        "workflow": "frontend",
        "strategy": "balanced",
        "selected_by_stage": {
            "frontend_authority": {"model_id": "m1", "provider_key": "p1"},
            "auxiliary_reference": {"model_id": "m2", "provider_key": "p2"},
        },
    }
    prompt = build_multi_frontend_prompt("responsive nav", routing_meta, audit_on=False)
    assert "Frontend Orchestrator" in prompt
    assert "### Phase 4 Execute" in prompt
    assert "responsive nav" in prompt
    assert "accessibility" in prompt.lower()
    assert "User disabled audit hints" in prompt
    assert "`frontend_authority`" in prompt
