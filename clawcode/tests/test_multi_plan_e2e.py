"""End-to-end style checks for /multi-plan routing vs provider toggles and show/list."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawcode.config.settings import Provider, Settings
from clawcode.llm.plan_store import PlanStore, PlanTaskItem
from clawcode.tui.builtin_slash import BuiltinSlashContext
from clawcode.tui.builtin_slash_handlers import handle_builtin_slash


@pytest.mark.asyncio
async def test_multi_plan_e2e_disabled_provider_excluded_from_routing_and_artifacts(
    tmp_path: Path,
) -> None:
    """Simulate .clawcode.json-style provider toggles; assert pool/show/list stay consistent."""
    settings = Settings()
    settings.working_directory = str(tmp_path)
    session_id = "sess_e2e_multi_plan"

    settings.providers = {
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }

    out_all = await handle_builtin_slash(
        "multi-plan",
        "rate limit design --explain-routing --strategy balanced",
        settings=settings,
        session_service=None,
    )
    assert out_all.kind == "agent_prompt"
    meta_all = out_all.routing_meta
    pool_all = {e["model_id"] for e in meta_all["discovered_pool"]}
    assert pool_all == {"claude-opus-4", "deepseek-chat", "glm-5"}
    backend_chain = [c["model_id"] for c in meta_all["candidate_chains"]["backend_analysis"]]
    assert "deepseek-chat" in backend_chain

    settings.providers["openai_deepseek"] = Provider(disabled=True, models=["deepseek-chat"])

    out_balanced = await handle_builtin_slash(
        "multi-plan",
        "rate limit design --explain-routing --strategy balanced",
        settings=settings,
        session_service=None,
    )
    assert out_balanced.kind == "agent_prompt"
    meta_balanced = out_balanced.routing_meta
    pool_cut = {e["model_id"] for e in meta_balanced["discovered_pool"]}
    assert "deepseek-chat" not in pool_cut
    assert pool_cut == {"claude-opus-4", "glm-5"}
    backend_chain2 = [c["model_id"] for c in meta_balanced["candidate_chains"]["backend_analysis"]]
    assert "deepseek-chat" not in backend_chain2
    for sel in meta_balanced["selected_by_stage"].values():
        assert isinstance(sel, dict)
        assert sel.get("model_id") != "deepseek-chat"

    out_quality = await handle_builtin_slash(
        "multi-plan",
        "rate limit design --explain-routing --strategy quality-first",
        settings=settings,
        session_service=None,
    )
    assert out_quality.kind == "agent_prompt"
    meta_quality = out_quality.routing_meta
    assert "deepseek-chat" not in {e["model_id"] for e in meta_quality["discovered_pool"]}

    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id=session_id,
        user_request="rate limit design",
        plan_text="# Plan e2e\n\n- one step",
        tasks=[PlanTaskItem(id="task-e2e-1", title="one step")],
        subdir="multi-plan",
        base_name="e2e-rate-limit",
    )
    bundle.routing_meta = dict(meta_balanced)
    store.save_plan_bundle(bundle)

    show_out = await handle_builtin_slash(
        "multi-plan",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id=session_id),
    )
    show_text = show_out.assistant_text or ""
    assert "Routing summary" in show_text
    assert "balanced" in show_text
    assert "deepseek-chat" not in show_text
    assert "claude-opus-4" in show_text or "glm-5" in show_text

    bundle_prev = store.save_bundle_versioned(
        session_id="sess_e2e_other",
        user_request="same scope alt strategy",
        plan_text="# Plan other\n",
        tasks=[PlanTaskItem(id="task-old-1", title="x")],
        subdir="multi-plan",
        base_name="e2e-other",
    )
    bundle_prev.routing_meta = dict(meta_quality)
    store.save_plan_bundle(bundle_prev)

    list_out = await handle_builtin_slash(
        "multi-plan",
        "list",
        settings=settings,
        session_service=None,
    )
    list_text = list_out.assistant_text or ""
    assert "multi-plan artifacts" in list_text
    assert "| Strategy |" in list_text
    assert "balanced" in list_text
    assert "quality-first" in list_text
    assert "deepseek-chat" not in list_text
