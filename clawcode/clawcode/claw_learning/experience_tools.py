from __future__ import annotations

import json
import hashlib

from ..config import get_settings
from ..learning.service import LearningService
from ..learning.experience_store import list_capsules
from ..claw_skills.skill_store import SkillStore
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..llm.tools.base import ToolCall, ToolContext


class ExperienceEvolveToSkillsTool:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._svc = LearningService(self._settings)
        self._skill_store = SkillStore()

    def info(self):
        from ..llm.tools.base import ToolInfo

        return ToolInfo(
            name="experience_evolve_to_skills",
            description=(
                "Generate reusable skills from recent observations via LearningService.evolve_advanced, "
                "then import generated SKILL.md files into claw_skills store."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "threshold": {"type": "integer", "description": "Cluster threshold (default 2)."},
                    "limit": {"type": "integer", "description": "Max generated skills to import (default 8)."},
                },
                "required": [],
            },
            required=[],
        )

    async def run(self, call: ToolCall, context: ToolContext):
        from ..llm.tools.base import ToolResponse

        args = call.get_input_dict()
        threshold = int(args.get("threshold", 2) or 2)
        limit = int(args.get("limit", 8) or 8)
        try:
            from ..learning.params import EvolveArgs

            txt = self._svc.evolve_advanced(EvolveArgs(execute=True, dry_run=False, threshold=threshold))
            imported = import_evolved_skills_to_store(
                learning_service=self._svc,
                skill_store=self._skill_store,
                limit=max(1, min(limit, 20)),
            )
            payload = {
                "success": True,
                "evolve_output": txt,
                "imported": imported["rows"],
                "summary": imported["summary"],
            }
            return ToolResponse.text(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            return ToolResponse.error(json.dumps({"success": False, "error": f"experience_evolve_to_skills failed: {e}"}, ensure_ascii=False))


def create_experience_evolve_to_skills_tool() -> ExperienceEvolveToSkillsTool:
    return ExperienceEvolveToSkillsTool()


def _ensure_skill_frontmatter(name: str, content: str) -> str:
    if content.startswith("---"):
        return content
    return (
        "---\n"
        f"name: {name}\n"
        f"description: Evolved skill generated from learning observations ({name}).\n"
        "version: 1.0.0\n"
        "---\n\n"
        + content
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def import_evolved_skills_to_store(
    learning_service: LearningService,
    skill_store: SkillStore,
    *,
    limit: int = 8,
) -> dict[str, object]:
    """Import evolved SKILL.md files into claw_skills with conflict-aware summary."""
    src_root = learning_service.paths.evolved_skills_dir
    rows: list[dict[str, str]] = []
    summary = {
        "created": 0,
        "updated": 0,
        "skipped_same_content": 0,
        "gated_by_experience_count": 0,
        "conflicts": 0,
        "read_errors": 0,
        "gated_rows": [],
    }
    if not src_root.exists():
        return {"rows": rows, "summary": summary}

    skill_files = sorted(src_root.rglob("SKILL.md"))
    for skill_md in skill_files[:limit]:
        name = skill_md.parent.name
        try:
            content = skill_md.read_text(encoding="utf-8")
        except OSError:
            summary["read_errors"] += 1
            rows.append({"name": name, "status": "read_error", "source": str(skill_md)})
            continue
        content = _ensure_skill_frontmatter(name, content)
        incoming_hash = _sha256_text(content)
        gate = _experience_gate_decision(learning_service, skill_name=name)
        if not bool(gate.get("allowed", True)):
            summary["gated_by_experience_count"] += 1
            reason = str(gate.get("reason", "experience_gate_blocked"))
            row = {
                "name": name,
                "status": "gated_by_experience",
                "source": str(skill_md),
                "reason": reason,
                "experience_score": gate.get("experience_score", 0.0),
                "confidence": gate.get("confidence", 0.0),
                "ci_width": gate.get("ci_width", 1.0),
                "sample_count": gate.get("sample_count", 0),
                "gate_decision": "blocked",
            }
            rows.append(row)
            summary["gated_rows"].append(row)
            continue

        existing = skill_store.view_skill(name)
        if not existing.get("success"):
            created = skill_store.create_skill(name=name, content=content, category="evolved")
            if created.get("success"):
                summary["created"] += 1
                rows.append(
                    {
                        "name": name,
                        "status": "created",
                        "source": str(skill_md),
                        "target_category": "evolved",
                        "gate_decision": "allowed",
                        "experience_score": gate.get("experience_score", 0.0),
                        "confidence": gate.get("confidence", 0.0),
                        "ci_width": gate.get("ci_width", 1.0),
                        "sample_count": gate.get("sample_count", 0),
                    }
                )
            else:
                summary["conflicts"] += 1
                rows.append({"name": name, "status": "conflict", "source": str(skill_md), "reason": str(created.get("error", ""))})
            continue

        existing_content = str(existing.get("content", ""))
        existing_hash = _sha256_text(existing_content)
        if existing_hash == incoming_hash:
            summary["skipped_same_content"] += 1
            rows.append(
                {
                    "name": name,
                    "status": "skipped_same_content",
                    "source": str(skill_md),
                    "gate_decision": "allowed",
                    "experience_score": gate.get("experience_score", 0.0),
                }
            )
            continue

        edited = skill_store.edit_skill(name=name, content=content)
        if edited.get("success"):
            summary["updated"] += 1
            rows.append(
                {
                    "name": name,
                    "status": "updated",
                    "source": str(skill_md),
                    "gate_decision": "allowed",
                    "experience_score": gate.get("experience_score", 0.0),
                    "confidence": gate.get("confidence", 0.0),
                    "ci_width": gate.get("ci_width", 1.0),
                    "sample_count": gate.get("sample_count", 0),
                }
            )
        else:
            summary["conflicts"] += 1
            rows.append({"name": name, "status": "conflict", "source": str(skill_md), "reason": str(edited.get("error", ""))})
    return {"rows": rows, "summary": summary}


def _experience_gate_decision(learning_service: LearningService, *, skill_name: str) -> dict[str, object]:
    cfg = getattr(learning_service.settings, "closed_loop", None)
    enabled = bool(getattr(cfg, "evolve_experience_gate_enabled", True))
    if not enabled:
        return {"allowed": True, "reason": "gate_disabled", "experience_score": 1.0, "confidence": 1.0, "ci_width": 0.0, "sample_count": 999}
    score_min = float(getattr(cfg, "evolve_experience_gate_min_score", 0.5) or 0.5)
    conf_min = float(getattr(cfg, "evolve_experience_gate_min_confidence", 0.45) or 0.45)
    ci_width_max = float(getattr(cfg, "evolve_experience_gate_max_ci_width", 0.65) or 0.65)
    sample_min = float(getattr(cfg, "evolve_experience_gate_min_samples", 1.0) or 1.0)
    rows = [
        c
        for c in list_capsules(learning_service.settings)
        if (c.knowledge_triple.skill_ref.skill_name or "").strip().lower() == (skill_name or "").strip().lower()
    ]
    if not rows:
        return {
            "allowed": True,
            "reason": "no_experience_data_fallback",
            "experience_score": 1.0,
            "confidence": 1.0,
            "ci_width": 0.0,
            "sample_count": 0,
        }
    scores = [float(x.knowledge_triple.experience_fn.score or 0.0) for x in rows]
    confs = [float(x.knowledge_triple.experience_fn.confidence or 0.0) for x in rows]
    widths = [
        max(0.0, float(x.knowledge_triple.experience_fn.ci_upper or 1.0) - float(x.knowledge_triple.experience_fn.ci_lower or 0.0))
        for x in rows
    ]
    samples = [int(x.knowledge_triple.experience_fn.sample_count or 0) for x in rows]
    score = sum(scores) / max(1, len(scores))
    conf = sum(confs) / max(1, len(confs))
    width = sum(widths) / max(1, len(widths))
    sample = sum(samples) / max(1, len(samples))
    allowed = score >= score_min and conf >= conf_min and width <= ci_width_max and sample >= sample_min
    return {
        "allowed": bool(allowed),
        "reason": "" if allowed else "experience_gate_threshold_not_met",
        "experience_score": round(score, 6),
        "confidence": round(conf, 6),
        "ci_width": round(width, 6),
        "sample_count": round(sample, 3),
    }

