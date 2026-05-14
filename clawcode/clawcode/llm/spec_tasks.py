"""Task decomposition and topological sort for spec bundles.

Parses the spec markdown into ordered SpecTask items with dependency
relationships and generates a matching checklist.
"""

from __future__ import annotations

import re
from typing import Any

from .spec_store import SpecTask, CheckItem


def split_spec_to_tasks(spec_markdown: str, *, max_tasks: int = 20) -> list[SpecTask]:
    """Parse a spec document into ordered tasks.

    Strategy (by priority):
    1. Explicit ``## T1:`` / ``### T1:`` headings with task IDs
    2. Numbered ``## Step N`` / ``## Phase N`` headings
    3. Top-level ``##`` sections (excluding known non-task headings)
    4. Fallback: single task covering the whole spec
    """
    lines = spec_markdown.split("\n")
    tasks: list[SpecTask] = []

    # Strategy 1: explicit T-prefixed headings
    for m in re.finditer(
        r"^#{1,4}\s+(?P<id>T\d+)\s*[:.]\s*(?P<title>.+)$",
        spec_markdown,
        re.MULTILINE,
    ):
        tasks.append(
            SpecTask(
                id=m.group("id").strip(),
                title=m.group("title").strip(),
                priority="high",
            )
        )
    if tasks:
        return tasks[:max_tasks]

    # Strategy 2: numbered steps/phases
    for m in re.finditer(
        r"^##\s+(?:Step|Phase|Part)\s+(\d+)\s*[:.]\s*(.+)$",
        spec_markdown,
        re.MULTILINE,
    ):
        idx = int(m.group(1))
        title = m.group(2).strip()
        tasks.append(
            SpecTask(
                id=f"T{idx}",
                title=title,
                priority="high" if idx <= 2 else "medium",
                depends_on=[f"T{idx - 1}"] if idx > 1 else [],
            )
        )
    if tasks:
        return tasks[:max_tasks]

    # Strategy 3: ## headings (skip known non-task sections)
    skip_prefixes = {
        "overview", "summary", "introduction", "background",
        "requirement", "non-functional", "constraint", "risk",
        "assumption", "glossary", "reference", "appendix",
        "design", "architecture",
    }
    counter = 0
    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if not m:
            continue
        heading = m.group(1).strip()
        first_word = re.split(r"[\s:]", heading, 1)[0].lower()
        if first_word in skip_prefixes:
            continue
        counter += 1
        tasks.append(
            SpecTask(
                id=f"T{counter}",
                title=heading,
                priority="high" if counter <= 2 else "medium",
                depends_on=[f"T{counter - 1}"] if counter > 1 else [],
            )
        )
    if tasks:
        return tasks[:max_tasks]

    # Strategy 4: fallback
    return [
        SpecTask(id="T1", title="Implement the specification", priority="high"),
        SpecTask(id="T2", title="Verify and test", priority="high", depends_on=["T1"]),
    ]


def generate_checklist_from_tasks(tasks: list[SpecTask]) -> list[CheckItem]:
    """Generate checklist items from task acceptance criteria."""
    items: list[CheckItem] = []
    counter = 0
    for task in tasks:
        if task.acceptance_criteria:
            for criterion in task.acceptance_criteria:
                counter += 1
                cid = f"C{counter}"
                items.append(
                    CheckItem(
                        id=cid,
                        description=criterion,
                        task_ref=task.id,
                    )
                )
                task.checklist_refs.append(cid)
        else:
            counter += 1
            cid = f"C{counter}"
            desc = f"Task {task.id} ({task.title}) is completed and verified"
            items.append(
                CheckItem(
                    id=cid,
                    description=desc,
                    task_ref=task.id,
                )
            )
            task.checklist_refs.append(cid)
    return items


def topological_sort_tasks(tasks: list[SpecTask]) -> list[SpecTask]:
    """Sort tasks respecting dependency ordering.

    Tasks with no dependencies come first.  Tasks whose dependencies
    are all satisfied are placed next.  Unresolvable dependencies are
    ignored (the task is placed at the end).
    """
    if not tasks:
        return tasks

    by_id = {t.id: t for t in tasks}
    sorted_ids: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(tid: str) -> None:
        if tid in visited:
            return
        if tid in visiting:
            return
        visiting.add(tid)
        task = by_id.get(tid)
        if task:
            for dep in task.depends_on:
                if dep in by_id:
                    visit(dep)
        visiting.discard(tid)
        visited.add(tid)
        sorted_ids.append(tid)

    for t in tasks:
        visit(t.id)

    ordered = [by_id[tid] for tid in sorted_ids if tid in by_id]
    for t in tasks:
        if t not in ordered:
            ordered.append(t)
    return ordered


def format_tasks_markdown(tasks: list[SpecTask]) -> str:
    """Render tasks as a markdown document."""
    lines: list[str] = ["# Task Breakdown\n"]
    for t in tasks:
        priority_marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "⚪")
        dep_str = f" [depends: {', '.join(t.depends_on)}]" if t.depends_on else " [depends: none]"
        lines.append(f"## {t.id}: {t.title} {priority_marker}{dep_str}\n")
        if t.description:
            lines.append(f"{t.description}\n")
        if t.files_to_modify:
            lines.append("**Files:** " + ", ".join(f"`{f}`" for f in t.files_to_modify) + "\n")
        if t.acceptance_criteria:
            lines.append("**Acceptance:**")
            for ac in t.acceptance_criteria:
                lines.append(f"- {ac}")
            lines.append("")
        if t.checklist_refs:
            lines.append(f"**Checklist:** {', '.join(t.checklist_refs)}\n")
        lines.append(f"**Status:** {t.status}\n")
    return "\n".join(lines)


def format_checklist_markdown(checklist: list[CheckItem]) -> str:
    """Render checklist as a markdown document."""
    lines: list[str] = ["# Acceptance Checklist\n"]
    for c in checklist:
        mark = "x" if c.verified else " "
        ref = f" (→ {c.task_ref})" if c.task_ref else ""
        lines.append(f"- [{mark}] {c.id}: {c.description}{ref}")
    return "\n".join(lines)
