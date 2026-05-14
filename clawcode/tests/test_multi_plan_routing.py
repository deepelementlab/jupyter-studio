from __future__ import annotations

from clawcode.config.settings import Provider, Settings
from clawcode.tui.multi_plan_routing import (
    MultiPlanRoutingArgs,
    build_routing_plan,
    discover_available_models,
)


def test_discover_available_models_filters_disabled() -> None:
    settings = Settings()
    settings.providers = {
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
        "gemini": Provider(disabled=True, models=["gemini-1.5-pro"]),
    }
    rows = discover_available_models(settings)
    ids = {x.model_id for x in rows}
    assert "deepseek-chat" in ids
    assert "glm-5" in ids
    assert "gemini-1.5-pro" not in ids


def test_build_routing_plan_honors_explicit_overrides() -> None:
    settings = Settings()
    settings.providers = {
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    args = MultiPlanRoutingArgs(
        requirement="x",
        model_backend="glm-5",
        model_frontend="deepseek-chat",
        mode="hybrid",
        strategy="balanced",
    )
    plan = build_routing_plan(settings, args, coder_model="deepseek-chat")
    selected = plan["selected_by_stage"]
    assert selected["backend_analysis"]["model_id"] == "glm-5"
    assert selected["frontend_analysis"]["model_id"] == "deepseek-chat"
    assert plan["discovered_pool"]

