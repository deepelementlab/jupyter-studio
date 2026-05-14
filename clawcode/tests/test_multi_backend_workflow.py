"""Unit tests for `/multi-backend` routing meta and prompt builder."""

from __future__ import annotations

from pathlib import Path

from clawcode.config.settings import Provider, Settings
from clawcode.tui.multi_backend_workflow import build_backend_routing_meta, build_multi_backend_prompt
from clawcode.tui.multi_plan_routing import MultiPlanRoutingArgs, build_backend_routing_plan


def test_build_backend_routing_plan_has_workflow_and_stages(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    args = MultiPlanRoutingArgs(requirement="retry logic", strategy="balanced")
    meta = build_backend_routing_plan(settings, args, coder_model="glm-5")
    assert meta["workflow"] == "backend"
    for stage in ("backend_authority", "auxiliary_reference", "backend_synthesis"):
        assert stage in meta["selected_by_stage"]
        assert meta["selected_by_stage"][stage].get("model_id")
    assert meta["selected_by_stage"]["backend_authority"]["model_id"] == "claude-opus-4"


def test_build_backend_routing_meta_matches_plan(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
    }
    args = MultiPlanRoutingArgs(requirement="x")
    direct = build_backend_routing_plan(settings, args, coder_model="deepseek-chat")
    via = build_backend_routing_meta(settings, args, coder_model="deepseek-chat")
    assert via == direct


def test_build_backend_routing_respects_disabled_provider(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "openai_deepseek": Provider(disabled=True, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    args = MultiPlanRoutingArgs(requirement="task")
    meta = build_backend_routing_meta(settings, args, coder_model="glm-5")
    pool_ids = {e["model_id"] for e in meta["discovered_pool"]}
    assert "deepseek-chat" not in pool_ids
    assert "glm-5" in pool_ids


def test_build_multi_backend_prompt_contains_execute_and_orchestrator() -> None:
    routing_meta = {
        "workflow": "backend",
        "strategy": "balanced",
        "selected_by_stage": {
            "backend_authority": {"model_id": "m1", "provider_key": "p1"},
            "auxiliary_reference": {"model_id": "m2", "provider_key": "p2"},
        },
    }
    prompt = build_multi_backend_prompt("harden webhook handler", routing_meta, audit_on=False)
    assert "Backend Orchestrator" in prompt
    assert "### Phase 4 Execute" in prompt
    assert "harden webhook handler" in prompt
    assert "User disabled audit hints" in prompt
    assert "`backend_authority`" in prompt
