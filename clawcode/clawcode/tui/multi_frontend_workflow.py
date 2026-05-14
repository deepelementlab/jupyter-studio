from __future__ import annotations

from typing import Any

from ..config.settings import Settings
from .multi_plan_routing import MultiPlanRoutingArgs, build_frontend_routing_plan


def build_frontend_routing_meta(
    settings: Settings,
    args: MultiPlanRoutingArgs,
    *,
    coder_model: str = "",
) -> dict[str, Any]:
    return build_frontend_routing_plan(settings, args, coder_model=coder_model)


def build_multi_frontend_prompt(
    requirement: str,
    routing_meta: dict[str, Any],
    *,
    audit_on: bool = True,
) -> str:
    req = (requirement or "").strip()
    selected = routing_meta.get("selected_by_stage", {})
    sel_lines: list[str] = []
    if isinstance(selected, dict):
        for stage, one in sorted(selected.items()):
            if not isinstance(one, dict):
                continue
            mid = str(one.get("model_id") or "").strip()
            pkey = str(one.get("provider_key") or "").strip()
            if mid:
                sel_lines.append(
                    f"- `{stage}` (subagent advisory): `{mid}` ({pkey or 'provider?'})"
                )
    selected_text = "\n".join(sel_lines) if sel_lines else "- no pool selection"

    audit_block = (
        "### Phase 5 Optimize — review\n"
        "- After implementation, run a structured UI review (accessibility, responsiveness, performance, "
        "design consistency).\n"
        "- Integrate findings only after user confirmation.\n\n"
        if audit_on
        else "### Phase 5 Optimize — review\n- User disabled audit hints (`--audit off`); still self-check best-effort.\n\n"
    )

    return (
        "You are running clawcode built-in `/multi-frontend` (frontend-focused multi-model workflow; "
        "aligned with upstream `/frontend` style guides).\n"
        "You are the **Frontend Orchestrator**. Follow the phase sequence strictly; prefix assistant turns with "
        "`[Mode: <Name>]` matching the active phase.\n\n"
        "Collaboration rules:\n"
        "- **Frontend authority**: use the `frontend_authority` slot model via subagent (`Agent`/`Task`) for "
        "UI/UX analysis, component structure, and visual/interaction feedback.\n"
        "- **Auxiliary reference**: use `auxiliary_reference` for backend-angled cross-checks (API contracts, "
        "data flow); treat as **non-authoritative** for pure UI decisions.\n"
        "- **Synthesis**: use `frontend_synthesis` when merging conflicting opinions.\n"
        "- Subagents are **read-only advisors**: they must not write files or run mutating commands. "
        "**You (orchestrator)** perform all filesystem edits and execution.\n\n"
        "Configured model slots (config-driven):\n"
        f"{selected_text}\n\n"
        "## Phase sequence\n\n"
        "### Phase 0 Prepare (optional)\n"
        "- If MCP or search tools improve the task statement, refine the requirement once; otherwise skip.\n\n"
        "### Phase 1 Research `[Mode: Research]`\n"
        "- Gather workspace context (components, styles, design system). Rate requirement completeness 0–10; "
        "if <7, stop and ask for missing info.\n\n"
        "### Phase 2 Ideation `[Mode: Ideation]`\n"
        "- Call subagent with **frontend_authority** model: UI feasibility, at least two solution options, UX risks.\n"
        "- Present options; wait for user choice before planning.\n\n"
        "### Phase 3 Plan `[Mode: Plan]`\n"
        "- Subagent (frontend_authority): component structure, UI flow, styling approach; follow existing design system.\n"
        "- Produce an implementable plan; get explicit user approval before coding.\n\n"
        "### Phase 4 Execute `[Mode: Execute]`\n"
        "- Implement approved plan with minimal, safe edits. Respect responsiveness and accessibility (a11y). "
        "You hold write access; subagents do not.\n\n"
        f"{audit_block}"
        "### Phase 6 Review `[Mode: Review]`\n"
        "- Verify against plan; note a11y/responsive gaps and follow-ups.\n\n"
        f"User task:\n{req}\n"
    )
