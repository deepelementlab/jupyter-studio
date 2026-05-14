"""End-to-end style checks for /multi-frontend routing vs provider toggles and show/list."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawcode.config.settings import Provider, Settings
from clawcode.llm.plan_store import PlanStore, PlanTaskItem
from clawcode.tui.builtin_slash import BuiltinSlashContext
from clawcode.tui.builtin_slash_handlers import handle_builtin_slash


@pytest.mark.asyncio
async def test_multi_frontend_e2e_disabled_provider_excluded_from_routing_and_artifacts(
    tmp_path: Path,
) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    session_id = "sess_e2e_multi_frontend"

    settings.providers = {
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
        "gemini_google": Provider(disabled=False, models=["gemini-2.0-flash"]),
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
    }

    out_all = await handle_builtin_slash(
        "multi-frontend",
        "responsive hero --explain-routing --strategy balanced --audit on",
        settings=settings,
        session_service=None,
    )
    assert out_all.kind == "agent_prompt"
    meta_all = out_all.routing_meta or {}
    pool_all = {e["model_id"] for e in meta_all["discovered_pool"]}
    assert pool_all == {"claude-opus-4", "gemini-2.0-flash", "deepseek-chat"}
    assert meta_all.get("workflow") == "frontend"
    assert meta_all.get("frontend_meta", {}).get("audit") == "on"
    auth_chain = [c["model_id"] for c in meta_all["candidate_chains"]["frontend_authority"]]
    assert "gemini-2.0-flash" in auth_chain

    settings.providers["openai_deepseek"] = Provider(disabled=True, models=["deepseek-chat"])

    out_cut = await handle_builtin_slash(
        "multi-frontend",
        "responsive hero --explain-routing --strategy balanced --audit on",
        settings=settings,
        session_service=None,
    )
    assert out_cut.kind == "agent_prompt"
    meta_cut = out_cut.routing_meta or {}
    pool_cut = {e["model_id"] for e in meta_cut["discovered_pool"]}
    assert "deepseek-chat" not in pool_cut
    assert pool_cut == {"claude-opus-4", "gemini-2.0-flash"}
    auth_chain2 = [c["model_id"] for c in meta_cut["candidate_chains"]["auxiliary_reference"]]
    assert "deepseek-chat" not in auth_chain2
    for sel in meta_cut["selected_by_stage"].values():
        assert isinstance(sel, dict)
        assert sel.get("model_id") != "deepseek-chat"

    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id=session_id,
        user_request="responsive hero",
        plan_text="# Multi-Frontend Result: e2e\n\n- step",
        tasks=[PlanTaskItem(id="task-mf-e2e", title="step")],
        subdir="multi-frontend",
        base_name="e2e-hero",
    )
    bundle.routing_meta = dict(meta_cut)
    bundle.routing_meta["frontend_meta"] = {"audit": "on"}
    store.save_plan_bundle(bundle)

    show_out = await handle_builtin_slash(
        "multi-frontend",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id=session_id),
    )
    show_text = show_out.assistant_text or ""
    assert "latest multi-frontend" in show_text
    assert "Routing summary" in show_text
    assert "deepseek-chat" not in show_text
    assert "gemini-2.0-flash" in show_text or "claude-opus-4" in show_text

    list_out = await handle_builtin_slash(
        "multi-frontend",
        "list",
        settings=settings,
        session_service=None,
    )
    list_text = list_out.assistant_text or ""
    assert "multi-frontend artifacts" in list_text
    assert "| Workflow |" in list_text
    assert "| Audit |" in list_text
