"""Tests for Claude Code–aligned Anthropic credential resolution (claw_support.anthropic_resolve)."""

from __future__ import annotations

import clawcode.llm.claw_support.anthropic_resolve as ar

# Expected tuples mirror common Claude Code client lists — see
# claw_support/ANTHROPIC_CLAUDE_COMPAT.md when updating.
_ANTHROPIC_COMPAT_COMMON_BETAS = (
    "interleaved-thinking-2025-05-14",
    "fine-grained-tool-streaming-2025-05-14",
)
_ANTHROPIC_COMPAT_OAUTH_BETAS = (
    "claude-code-20250219",
    "oauth-2025-04-20",
)
_ANTHROPIC_COMPAT_VERSION_FALLBACK = "2.1.74"


def test_anthropic_compat_beta_lists_match_adapter() -> None:
    assert tuple(ar._COMMON_BETAS) == _ANTHROPIC_COMPAT_COMMON_BETAS
    assert tuple(ar._OAUTH_ONLY_BETAS) == _ANTHROPIC_COMPAT_OAUTH_BETAS


def test_anthropic_compat_claude_code_version_fallback() -> None:
    assert ar._CLAUDE_CODE_VERSION_FALLBACK == _ANTHROPIC_COMPAT_VERSION_FALLBACK
