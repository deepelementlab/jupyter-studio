# `designteam` per-role design config

Lightweight **YAML** files (one per Tier-1 role) complement [`.claw/agents/designteam-*.md`](../agents/) agent prompts. They hold **structured** hints: outputs, methods, references to UI benchmarks—without duplicating long-form instructions.

## Tier-1 (built-in roster)

| Agent id | Config file |
|----------|-------------|
| `designteam-user-researcher` | [user-researcher.yaml](./user-researcher.yaml) |
| `designteam-interaction-designer` | [interaction-designer.yaml](./interaction-designer.yaml) |
| `designteam-ui-designer` | [ui-designer.yaml](./ui-designer.yaml) |
| `designteam-product-designer` | [product-designer.yaml](./product-designer.yaml) |
| `designteam-visual-ops-designer` | [visual-ops-designer.yaml](./visual-ops-designer.yaml) |
| `designteam-experience-design-expert` | [experience-design-expert.yaml](./experience-design-expert.yaml) |

## Tier-2 (optional extensions)

Not registered as built-in agents; orchestrator may **simulate** or recommend human follow-up:

| Role id | Use when |
|---------|----------|
| `designteam-content-designer` | Microcopy, tone, empty/error strings at scale |
| `designteam-design-systems` | Tokens, component contracts, governance |
| `designteam-accessibility` | Regulated or WCAG-audit-heavy deliveries |
| `designteam-service-designer` | Deep service blueprint / multi-channel B2B |

## Runtime loading

When you run **`/designteam`**, the orchestrator prompt may include summaries of existing YAML under this folder (see `clawcode/tui/designteam_design_config.py`). Missing files are skipped.
