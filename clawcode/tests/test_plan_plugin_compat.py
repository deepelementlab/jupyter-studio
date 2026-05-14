from __future__ import annotations

from pathlib import Path

from clawcode.agents.loader import load_merged_agent_definitions


def test_agent_frontmatter_plan_compat_fields(tmp_path: Path) -> None:
    agents_dir = tmp_path / ".claw" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "planx.md").write_text(
        """---
name: planx
description: custom plan agent
permissionMode: ask
background: true
mcpServers: [a, b]
hooks: [PlanStart, PlanReady]
unknownField: keep-me
---
You are planx.
""",
        encoding="utf-8",
    )

    merged = load_merged_agent_definitions(str(tmp_path))
    dfn = merged["planx"]
    assert dfn.permission_mode == "ask"
    assert dfn.background is True
    assert dfn.mcp_servers == ["a", "b"]
    assert dfn.hooks == ["PlanStart", "PlanReady"]
    assert dfn.extra.get("unknownField") == "keep-me"


def test_agent_loader_priority_claw_over_legacy(tmp_path: Path) -> None:
    claw_agents = tmp_path / ".claw" / "agents"
    clawcode_agents = tmp_path / ".clawcode" / "agents"
    claude_agents = tmp_path / ".claude" / "agents"
    claw_agents.mkdir(parents=True)
    clawcode_agents.mkdir(parents=True)
    claude_agents.mkdir(parents=True)

    (claude_agents / "x.md").write_text("---\nname: x\n---\nfrom claude", encoding="utf-8")
    (clawcode_agents / "x.md").write_text("---\nname: x\n---\nfrom clawcode", encoding="utf-8")
    (claw_agents / "x.md").write_text("---\nname: x\n---\nfrom claw", encoding="utf-8")

    merged = load_merged_agent_definitions(str(tmp_path))
    assert merged["x"].prompt == "from claw"

