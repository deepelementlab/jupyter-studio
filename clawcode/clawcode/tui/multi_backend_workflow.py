from __future__ import annotations

from typing import Any

from ..config.settings import Settings
from .multi_plan_routing import MultiPlanRoutingArgs, build_backend_routing_plan


def build_backend_routing_meta(
    settings: Settings,
    args: MultiPlanRoutingArgs,
    *,
    coder_model: str = "",
) -> dict[str, Any]:
    return build_backend_routing_plan(settings, args, coder_model=coder_model)


def build_multi_backend_prompt(
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
        "- After implementation, run a structured backend review (security, performance, errors, API contracts).\n"
        "- Integrate findings only after user confirmation.\n\n"
        if audit_on
        else "### Phase 5 Optimize — review\n- User disabled audit hints (`--audit off`); still self-check best-effort.\n\n"
    )

    return (
        "You are running clawcode built-in `/multi-backend` (backend-focused multi-model workflow).\n"
        "You are the **Backend Orchestrator**. Follow the phase sequence strictly; prefix assistant turns with "
        "`[Mode: <Name>]` matching the active phase.\n\n"
        "Collaboration rules:\n"
        "- **Backend authority**: use the `backend_authority` slot model via subagent (`Agent`/`Task`) for deep "
        "backend analysis, architecture, and code-review style feedback.\n"
        "- **Auxiliary reference**: use `auxiliary_reference` for cross-checks (e.g. API/UX edge cases); "
        "treat as **non-authoritative** for backend decisions.\n"
        "- **Synthesis**: use `backend_synthesis` when merging conflicting opinions.\n"
        "- Subagents are **read-only advisors**: they must not write files or run mutating commands. "
        "**You (orchestrator)** perform all filesystem edits and execution.\n\n"
        "Configured model slots (config-driven):\n"
        f"{selected_text}\n\n"
        "## Phase sequence\n\n"
        "### Phase 0 Prepare (optional)\n"
        "- If MCP or search tools improve the task statement, refine the requirement once; otherwise skip.\n\n"
        "### Phase 1 Research `[Mode: Research]`\n"
        "- Gather workspace context (read/search). Rate requirement completeness 0–10; if <7, stop and ask for missing info.\n\n"
        "### Phase 2 Ideation `[Mode: Ideation]`\n"
        "- Call subagent with **backend_authority** model: feasibility, at least two solution options, risks.\n"
        "- Present options; wait for user choice before planning.\n\n"
        "### Phase 3 Plan `[Mode: Plan]`\n"
        "- Subagent (backend_authority / architect-style): structure, modules, dependencies, interfaces.\n"
        "- Produce an implementable plan; get explicit user approval before coding.\n\n"
        "### Phase 4 Execute `[Mode: Execute]`\n"
        "- Implement approved plan with minimal, safe edits. You hold write access; subagents do not.\n\n"
        f"{audit_block}"
        "### Phase 6 Review `[Mode: Review]`\n"
        "- Verify against plan, suggest tests, list follow-ups.\n\n"
        f"User task:\n{req}\n"
    )
