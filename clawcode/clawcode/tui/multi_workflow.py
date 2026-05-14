from __future__ import annotations

from typing import Any

from ..config.settings import Settings
from .multi_plan_routing import MultiPlanRoutingArgs, build_routing_plan


def build_fullstack_routing_meta(
    settings: Settings,
    args: MultiPlanRoutingArgs,
    *,
    coder_model: str = "",
) -> dict[str, Any]:
    base = build_routing_plan(settings, args, coder_model=coder_model)
    out = dict(base)
    out["workflow"] = "fullstack"
    return out


def build_multi_workflow_prompt(
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
        "### Phase 5 Optimize `[Mode: Optimize]`\n"
        "- In parallel (two subagent calls), then integrate:\n"
        "  - **`backend_analysis` slot**: reviewer-style — security, performance, error handling, API contracts.\n"
        "  - **`frontend_analysis` slot**: reviewer-style — accessibility, responsiveness, design consistency.\n"
        "- Wait for both advisory outputs before synthesizing; integrate only after user confirmation.\n\n"
        if audit_on
        else "### Phase 5 Optimize `[Mode: Optimize]`\n"
        "- User disabled audit hints (`--audit off`); still run a lightweight self-review (backend + UI angles).\n\n"
    )

    research_block = (
        "### Phase 1 Research `[Mode: Research]`\n"
        "1) **Prompt refinement (optional, at most once)**:\n"
        "   - If the session has an MCP or tool that can rewrite/clarify the user task, use it once and treat the "
        "result as the **effective requirement** for all later phases; if none exists, skip and use the user text.\n"
        "2) **Context retrieval**:\n"
        "   - Use workspace tools (read, search, list directories) to find relevant modules, design system, "
        "APIs, and constraints — same rigor as other multi-* workflows.\n"
        "3) **Requirement completeness score (0–10)** — use this rubric exactly:\n"
        "   - Goal clarity: 0–3\n"
        "   - Expected outcome: 0–3\n"
        "   - Scope boundaries: 0–2\n"
        "   - Constraints (tech, time, compatibility): 0–2\n"
        "   - **If total < 7**: stop and ask clarifying questions; **do not enter Ideation** unless the user "
        "explicitly tells you to skip the gate.\n"
        "   - At end of Research, state the numeric score and a one-line rationale.\n\n"
    )

    return (
        "You are running clawcode built-in `/multi-workflow` (full-stack multi-model collaboration; aligned with "
        "upstream `/workflow`-style guides).\n"
        "You are the **Orchestrator**. Follow the phase sequence; prefix assistant turns with `[Mode: <Name>]`.\n\n"
        "Collaboration rules:\n"
        "- **`backend_analysis` slot**: backend-leaning advisor (feasibility, algorithms, APIs) — **authoritative "
        "for backend decisions**.\n"
        "- **`frontend_analysis` slot**: UI/UX-leaning advisor — **authoritative for UI decisions**; backend "
        "opinions from this slot on pure UI are non-binding.\n"
        "- **`synthesis` slot**: use when merging conflicting cross-cutting opinions.\n"
        "- Subagents are **read-only advisors** (no file writes, no mutating shell). **You** perform all edits.\n"
        "- Phases **Ideation**, **Plan**, and **Optimize** that name two perspectives: run **both** subagent calls "
        "and **wait for both** before synthesizing (order is flexible; completeness matters).\n\n"
        "Configured model slots (config-driven):\n"
        f"{selected_text}\n\n"
        "## Phase sequence\n\n"
        "### Phase 0 Prepare (optional) `[Mode: Prepare]`\n"
        "- If tools/MCP can improve the task statement without blocking, refine once; otherwise skip.\n\n"
        f"{research_block}"
        "### Phase 2 Ideation `[Mode: Ideation]`\n"
        "- **Parallel advisory**: invoke subagent with **`backend_analysis`** model and subagent with "
        "**`frontend_analysis`** model (analyzer-style): technical vs UI feasibility, risks, at least two options each "
        "angle where applicable.\n"
        "- Synthesize into a comparative summary; wait for user selection before Plan.\n\n"
        "### Phase 3 Plan `[Mode: Plan]`\n"
        "- **Parallel advisory**: **`backend_analysis`** (backend architecture) and **`frontend_analysis`** "
        "(UI structure, flow, styling).\n"
        "- You merge into one implementable plan; get explicit user approval before Execute.\n\n"
        "### Phase 4 Execute `[Mode: Execute]`\n"
        "- Implement the approved plan; follow project standards; you hold write access.\n\n"
        f"{audit_block}"
        "### Phase 6 Review `[Mode: Review]`\n"
        "- Verify against plan, tests, and list follow-ups.\n\n"
        f"User task:\n{req}\n"
    )
