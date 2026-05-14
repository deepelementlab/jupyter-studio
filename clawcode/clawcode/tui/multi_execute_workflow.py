from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..config.settings import Settings
from .multi_plan_routing import MultiPlanRoutingArgs, build_routing_plan

ExecuteMode = Literal["auto", "manual", "hybrid"]
AuditMode = Literal["on", "off"]


@dataclass
class MultiExecuteArgs:
    request: str = ""
    mode: ExecuteMode = "hybrid"
    strategy: str = "balanced"
    fallback: bool = True
    audit: AuditMode = "on"
    from_plan: str = ""
    model_backend: str = ""
    model_frontend: str = ""
    model_synthesis: str = ""
    explain_routing: bool = False


def _detect_task_type(text: str) -> str:
    low = (text or "").lower()
    has_fe = any(k in low for k in ["frontend", "ui", "ux", "页面", "交互"])
    has_be = any(k in low for k in ["backend", "api", "service", "数据库", "后端"])
    if has_fe and has_be:
        return "fullstack"
    if has_fe:
        return "frontend"
    if has_be:
        return "backend"
    return "fullstack"


def _parse_plan_markdown_sections(md: str) -> dict[str, str]:
    text = (md or "").replace("\r\n", "\n")
    out: dict[str, str] = {}
    current = "raw"
    buf: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            out[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower()
            buf = []
            continue
        buf.append(line)
    out[current] = "\n".join(buf).strip()
    return out


def build_execute_context(
    *,
    request: str,
    from_plan_path: str = "",
    root: Path | None = None,
) -> dict[str, Any]:
    req = (request or "").strip()
    plan_path = (from_plan_path or "").strip()
    mode = "direct-text"
    plan_text = ""
    sections: dict[str, str] = {}
    if plan_path:
        p = Path(plan_path)
        if not p.is_absolute() and root is not None:
            p = (root / p).resolve()
        if p.exists() and p.is_file():
            mode = "plan-file"
            plan_text = p.read_text(encoding="utf-8", errors="replace")
            sections = _parse_plan_markdown_sections(plan_text)
            if not req:
                req = sections.get("implementation steps", "") or sections.get("technical solution", "")
    task_type = _detect_task_type(req + "\n" + plan_text)
    return {
        "input_mode": mode,
        "request": req,
        "from_plan_path": plan_path,
        "plan_text": plan_text,
        "plan_sections": sections,
        "task_type": task_type,
    }


def build_model_assignment(
    settings: Settings,
    args: MultiExecuteArgs,
    *,
    coder_model: str = "",
) -> dict[str, Any]:
    routing_args = MultiPlanRoutingArgs(
        requirement=args.request,
        mode=args.mode,
        strategy=args.strategy,  # type: ignore[arg-type]
        model_backend=args.model_backend,
        model_frontend=args.model_frontend,
        model_synthesis=args.model_synthesis,
        fallback=args.fallback,
        explain_routing=args.explain_routing,
    )
    return build_routing_plan(settings, routing_args, coder_model=coder_model)


def build_audit_prompt(exe_ctx: dict[str, Any], assignment: dict[str, Any]) -> str:
    req = str(exe_ctx.get("request") or "").strip()
    t = str(exe_ctx.get("task_type") or "fullstack")
    strategy = str(assignment.get("strategy") or "balanced")
    return (
        "Audit phase (required):\n"
        "- Run dual-review perspective on the produced execution plan/result.\n"
        "- Backend-heavy issues prioritize backend model signals.\n"
        "- Frontend/UX issues prioritize frontend model signals.\n"
        "- If conflicts remain, list trade-offs and pick final recommendation explicitly.\n\n"
        f"Task type: {t}\n"
        f"Strategy: {strategy}\n"
        f"Request: {req}\n"
    )


def build_execute_prompt(exe_ctx: dict[str, Any], assignment: dict[str, Any], args: MultiExecuteArgs) -> str:
    req = str(exe_ctx.get("request") or "").strip()
    mode = str(exe_ctx.get("input_mode") or "direct-text")
    task_type = str(exe_ctx.get("task_type") or "fullstack")
    selected = assignment.get("selected_by_stage", {})
    sel_lines: list[str] = []
    if isinstance(selected, dict):
        for stage, one in sorted(selected.items()):
            if not isinstance(one, dict):
                continue
            mid = str(one.get("model_id") or "").strip()
            pkey = str(one.get("provider_key") or "").strip()
            if mid:
                sel_lines.append(f"- {stage}: `{mid}` ({pkey or 'provider?'})")
    selected_text = "\n".join(sel_lines) if sel_lines else "- no routing candidates"

    plan_seed = ""
    if mode == "plan-file":
        raw_plan = str(exe_ctx.get("plan_text") or "").strip()
        if raw_plan:
            cap = 6000
            plan_seed = (
                "Input plan (trimmed if long):\n"
                f"{raw_plan[:cap]}{'\\n...(truncated)' if len(raw_plan) > cap else ''}\n\n"
            )

    audit_block = build_audit_prompt(exe_ctx, assignment) if args.audit == "on" else "Audit phase disabled by `--audit off`.\n"
    return (
        "You are running clawcode built-in `/multi-execute` (multi-model collaborative execution).\n"
        "Goal: produce a concrete execution-ready implementation output, including risks, verification, and audit summary.\n\n"
        "Execution protocol:\n"
        "1) Parse and validate target scope.\n"
        "2) Use model assignment by stage to reason and draft executable changes.\n"
        "3) If stage fails, follow fallback candidate chain and log fallback events.\n"
        "4) Produce final consolidated output with explicit assumptions and test checklist.\n\n"
        f"Input mode: {mode}\n"
        f"Task type: {task_type}\n"
        f"Routing strategy: {assignment.get('strategy')}\n"
        f"Fallback enabled: {assignment.get('fallback')}\n\n"
        "Selected models:\n"
        f"{selected_text}\n\n"
        f"{plan_seed}"
        f"{audit_block}\n"
        "Output format (required):\n"
        "## Multi-Execute Result: <Task Name>\n"
        "## Execution Summary\n"
        "## Change Plan\n"
        "## Verification Checklist\n"
        "## Audit Summary\n"
        "## Risks and Rollback\n\n"
        f"User request:\n{req}\n"
    )

