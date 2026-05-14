"""Checklist verification for /spec workflow.

Parses agent output during verification phase to determine which
checklist items pass or fail.
"""

from __future__ import annotations

import re
from typing import Any

from .spec_store import CheckItem, SpecBundle


def parse_verification_results(
    agent_output: str,
    checklist: list[CheckItem],
) -> list[tuple[CheckItem, bool, str]]:
    """Parse agent verification output into (item, passed, evidence) tuples.

    The agent is expected to produce lines like:
      - C1: PASS — evidence text
      - C2: FAIL — evidence text

    If no structured output is found, all items are marked as needing manual review.
    """
    results: list[tuple[CheckItem, bool, str]] = []
    verdicts: dict[str, tuple[bool, str]] = {}

    for m in re.finditer(
        r"(?P<id>C\d+)\s*:\s*(?P<verdict>PASS|FAIL|✓|✗|❌|✅)\s*[:—-]?\s*(?P<evidence>.*?)(?:\n|$)",
        agent_output,
        re.IGNORECASE,
    ):
        cid = m.group("id").upper()
        v = m.group("verdict").upper()
        passed = v in ("PASS", "✓", "✅")
        evidence = m.group("evidence").strip()
        verdicts[cid] = (passed, evidence)

    for item in checklist:
        if item.id in verdicts:
            passed, evidence = verdicts[item.id]
            results.append((item, passed, evidence))
        else:
            results.append((item, False, "Not verified in agent output"))

    return results


def extract_failed_items(
    results: list[tuple[CheckItem, bool, str]],
) -> list[tuple[CheckItem, str]]:
    """Return only the failed items with their evidence."""
    return [(item, evidence) for item, passed, evidence in results if not passed]


def all_items_passed(results: list[tuple[CheckItem, bool, str]]) -> bool:
    """Check if all items passed verification."""
    return all(passed for _, passed, _ in results)


def apply_verification_to_bundle(
    bundle: SpecBundle,
    results: list[tuple[CheckItem, bool, str]],
) -> int:
    """Apply verification results to the bundle's checklist.

    Returns the number of newly verified items.
    """
    newly_verified = 0
    for item, passed, _ in results:
        if passed and not item.verified:
            item.verified = True
            newly_verified += 1
        elif not passed:
            item.verified = False
    bundle.execution.verified_count = sum(1 for c in bundle.checklist if c.verified)
    bundle.execution.failed_count = sum(1 for c in bundle.checklist if not c.verified)
    return newly_verified


def format_failed_checks_for_prompt(
    failed: list[tuple[CheckItem, str]],
) -> str:
    """Format failed checks for the refining prompt."""
    if not failed:
        return "No failed checks."
    lines = []
    for item, evidence in failed:
        lines.append(f"- {item.id}: {item.description}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)
