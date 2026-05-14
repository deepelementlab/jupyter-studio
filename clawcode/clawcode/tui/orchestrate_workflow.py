"""Built-in `/orchestrate`: sequential multi-role workflow with HANDOFF documents."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

WORKFLOW_CHAINS: dict[str, list[str]] = {
    "feature": ["planner", "tdd-guide", "code-reviewer", "security-reviewer"],
    "bugfix": ["planner", "tdd-guide", "code-reviewer"],
    "refactor": ["architect", "code-reviewer", "tdd-guide"],
    "security": ["security-reviewer", "code-reviewer", "architect"],
}

ALLOWED_AGENTS: frozenset[str] = frozenset(
    {"planner", "tdd-guide", "code-reviewer", "security-reviewer", "architect"}
)


@dataclass
class OrchestrateArgs:
    """show_list: empty for main run, or 'show' / 'list'."""

    show_list: str
    workflow: str
    agents: list[str]
    task: str


def parse_orchestrate_args(tail: str) -> tuple[OrchestrateArgs | None, str]:
    raw = (tail or "").strip()
    if not raw:
        return (
            None,
            (
                "Usage: `/orchestrate <feature|bugfix|refactor|security> <task description>`\n"
                "Or: `/orchestrate custom <agent1,agent2,...> <task description>`\n"
                "Agents: planner, tdd-guide, code-reviewer, security-reviewer, architect\n\n"
                "Examples:\n"
                "- `/orchestrate feature \"Add user authentication\"`\n"
                "- `/orchestrate custom architect,tdd-guide,code-reviewer \"Redesign cache\"`\n"
                "- `/orchestrate show` / `/orchestrate list`"
            ),
        )
    try:
        argv = shlex.split(raw)
    except ValueError as e:
        return None, f"Invalid `/orchestrate` args: {e}"
    if not argv:
        return None, "Please provide a workflow type and task."

    head = argv[0].strip().lower()
    if head in {"show", "list"}:
        return OrchestrateArgs(show_list=head, workflow="", agents=[], task=""), ""

    if head == "custom":
        if len(argv) < 3:
            return (
                None,
                "Usage: `/orchestrate custom <agent1,agent2,...> <task description>`\n"
                "Example: `/orchestrate custom architect,tdd-guide \"Refactor module X\"`",
            )
        agents_part = argv[1].strip()
        task = " ".join(argv[2:]).strip()
        if not task:
            return None, "Please provide a task description after the agent list."
        agents = [a.strip() for a in agents_part.split(",") if a.strip()]
        if not agents:
            return None, "Custom workflow needs at least one agent."
        for a in agents:
            if a not in ALLOWED_AGENTS:
                return None, f"Unknown agent `{a}`. Allowed: {', '.join(sorted(ALLOWED_AGENTS))}."
        return OrchestrateArgs(show_list="", workflow="custom", agents=agents, task=task), ""

    if head not in WORKFLOW_CHAINS:
        return (
            None,
            f"Unknown workflow `{head}`. Use: feature, bugfix, refactor, security, or custom.",
        )
    task = " ".join(argv[1:]).strip()
    if not task:
        return None, f"Please provide a task description after `{head}`."
    return (
        OrchestrateArgs(show_list="", workflow=head, agents=list(WORKFLOW_CHAINS[head]), task=task),
        "",
    )


def _agent_discipline(agent: str) -> str:
    if agent == "planner":
        return (
            "**Planner (this phase only — no production code changes)**\n"
            "- Analyze requirements, dependencies, and risks.\n"
            "- Produce a concrete implementation plan (sections, steps, key files).\n"
            "- End with the HANDOFF block; do not implement or mutate project files in this phase.\n"
        )
    if agent == "tdd-guide":
        return (
            "**TDD guide**\n"
            "- Read the previous HANDOFF.\n"
            "- Follow strict TDD: scaffold → RED → GREEN → refactor → coverage gate (target ≥80%, "
            "higher for critical paths).\n"
            "- You may modify files and run tests; document commands and results.\n"
        )
    if agent == "code-reviewer":
        return (
            "**Code reviewer (read-first; suggest fixes)**\n"
            "- Review diffs/changes from prior phases; severity-ranked findings; actionable fixes.\n"
            "- Prefer not to make large unsolicited edits unless the user expects fixes in this phase.\n"
        )
    if agent == "security-reviewer":
        return (
            "**Security reviewer**\n"
            "- Audit for secrets, injection, auth/authz, unsafe patterns; severity-ordered findings.\n"
            "- Read-first; integrate with prior HANDOFF context.\n"
        )
    if agent == "architect":
        return (
            "**Architect**\n"
            "- Structural/design analysis, trade-offs, refactor or migration plan as needed.\n"
            "- Align with HANDOFF context; prefer clear diagrams or bullet structure in output.\n"
        )
    return ""


def build_orchestrate_prompt(*, workflow: str, agents: list[str], task: str) -> str:
    chain_s = " -> ".join(agents)
    agent_sections = []
    for i, ag in enumerate(agents):
        agent_sections.append(f"### Step {i + 1}: `{ag}`\n{_agent_discipline(ag)}")
    agents_body = "\n".join(agent_sections)

    return (
        "You are running clawcode built-in `/orchestrate` (sequential multi-role workflow).\n\n"
        f"- **Workflow type:** `{workflow}`\n"
        f"- **Agent chain:** {chain_s}\n"
        f"- **Task:** {task.strip()}\n\n"
        "## Global rules\n"
        "1. Execute **one agent role at a time** in the order above. Finish each phase completely "
        "before starting the next.\n"
        "2. After each phase (except the last), emit a markdown block exactly in this shape:\n\n"
        "```markdown\n"
        "## HANDOFF: [previous-agent] -> [next-agent]\n\n"
        "### Context\n"
        "[Summary of what was done]\n\n"
        "### Findings\n"
        "[Key discoveries or decisions]\n\n"
        "### Files Modified\n"
        "[List of files touched, or \"none\"]\n\n"
        "### Open Questions\n"
        "[Unresolved items for next agent]\n\n"
        "### Recommendations\n"
        "[Suggested next steps]\n"
        "```\n\n"
        "3. The next phase must **read** the latest HANDOFF and continue from there.\n"
        "4. **Optional parallel phase:** If two later steps are independent (e.g. separate read-only "
        "reviews), you may run them via subagents or interleaved sections, then **merge** findings "
        "before the final report.\n"
        "5. After the final agent, output the **ORCHESTRATION REPORT** using this template:\n\n"
        "```\n"
        "ORCHESTRATION REPORT\n"
        "====================\n"
        f"Workflow: {workflow}\n"
        f"Task: <one line>\n"
        f"Agents: {chain_s}\n\n"
        "SUMMARY\n"
        "-------\n"
        "[One paragraph]\n\n"
        "AGENT OUTPUTS\n"
        "-------------\n"
        "[Bullet per agent]\n\n"
        "FILES CHANGED\n"
        "-------------\n"
        "[List]\n\n"
        "TEST RESULTS\n"
        "------------\n"
        "[If applicable]\n\n"
        "SECURITY STATUS\n"
        "---------------\n"
        "[If applicable]\n\n"
        "RECOMMENDATION\n"
        "--------------\n"
        "SHIP / NEEDS WORK / BLOCKED\n"
        "```\n\n"
        "## Phases (discipline per role)\n\n"
        f"{agents_body}\n"
    )
