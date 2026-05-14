from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..config.settings import Settings

RoutingMode = Literal["auto", "manual", "hybrid"]
RoutingStrategy = Literal["quality-first", "balanced", "speed-first", "cost-first"]


@dataclass
class AvailableModel:
    provider_key: str
    provider_name: str
    model_id: str
    tags: list[str]


@dataclass
class MultiPlanRoutingArgs:
    requirement: str = ""
    mode: RoutingMode = "hybrid"
    strategy: RoutingStrategy = "balanced"
    model_backend: str = ""
    model_frontend: str = ""
    model_synthesis: str = ""
    fallback: bool = True
    explain_routing: bool = False


def _infer_provider_name(provider_key: str, model_id: str) -> str:
    k = (provider_key or "").lower()
    m = (model_id or "").lower()
    if "anthropic" in k or "claude" in m:
        return "anthropic"
    if "gemini" in k or "gemini" in m:
        return "gemini"
    if "groq" in k:
        return "groq"
    if "xai" in k or "grok" in m:
        return "xai"
    if "openrouter" in k:
        return "openrouter"
    if "openai" in k:
        return "openai"
    return k or "unknown"


def _infer_tags(provider_name: str, model_id: str) -> list[str]:
    p = (provider_name or "").lower()
    m = (model_id or "").lower()
    tags: set[str] = set()
    if "claude" in m or p == "anthropic":
        tags.update({"claude", "reasoning", "quality"})
    if "gemini" in m or p == "gemini":
        tags.update({"gemini", "frontend", "multimodal"})
    if "gpt" in m or m.startswith("o1") or m.startswith("o3") or p == "openai":
        tags.update({"gpt", "general"})
    if "deepseek" in m:
        tags.update({"deepseek", "cost-efficient", "reasoning"})
    if "glm" in m:
        tags.update({"glm", "cost-efficient", "general"})
    if "qwen" in m:
        tags.update({"qwen", "cost-efficient", "general"})
    if not tags:
        tags.add("general")
    return sorted(tags)


def discover_available_models(settings: Settings) -> list[AvailableModel]:
    out: list[AvailableModel] = []
    providers = getattr(settings, "providers", {}) or {}
    for key, cfg in providers.items():
        if bool(getattr(cfg, "disabled", False)):
            continue
        models = list(getattr(cfg, "models", []) or [])
        if not models:
            continue
        for model in models:
            model_id = str(model or "").strip()
            if not model_id:
                continue
            provider_name = _infer_provider_name(str(key), model_id)
            out.append(
                AvailableModel(
                    provider_key=str(key),
                    provider_name=provider_name,
                    model_id=model_id,
                    tags=_infer_tags(provider_name, model_id),
                )
            )
    # deterministic order for tests and stable routing
    out.sort(key=lambda x: (x.provider_key, x.model_id))
    return out


def _stage_preferred_tags(stage: str) -> list[str]:
    if stage == "frontend_analysis":
        return ["gemini", "gpt", "general"]
    if stage == "backend_analysis":
        return ["claude", "gpt", "deepseek", "glm", "reasoning", "general"]
    if stage == "synthesis":
        return ["claude", "gpt", "reasoning", "general"]
    return ["general"]


def _score_model(
    model: AvailableModel, *, stage: str, strategy: RoutingStrategy, index: int = 0
) -> float:
    tags = set(model.tags)
    score = 0.0
    for i, t in enumerate(_stage_preferred_tags(stage)):
        if t in tags:
            score += max(0.0, 6.0 - i)
    # strategy adjustment (coarse, config-driven candidate pool decides final practical models)
    if strategy == "quality-first":
        if "quality" in tags or "reasoning" in tags:
            score += 2.0
    elif strategy == "speed-first":
        if "cost-efficient" in tags:
            score += 1.0
    elif strategy == "cost-first":
        if "cost-efficient" in tags:
            score += 2.0
    # stable tie breaker
    score -= index * 0.0001
    return score


def select_candidates_for_stage(
    pool: list[AvailableModel], *, stage: str, strategy: RoutingStrategy
) -> list[AvailableModel]:
    ranked = sorted(
        enumerate(pool),
        key=lambda x: _score_model(x[1], stage=stage, strategy=strategy, index=x[0]),
        reverse=True,
    )
    return [x[1] for x in ranked]


def _find_model(pool: list[AvailableModel], model_id: str) -> AvailableModel | None:
    wanted = (model_id or "").strip().lower()
    if not wanted:
        return None
    for m in pool:
        if m.model_id.lower() == wanted:
            return m
    return None


def build_routing_plan(
    settings: Settings,
    args: MultiPlanRoutingArgs,
    *,
    coder_model: str = "",
) -> dict[str, Any]:
    pool = discover_available_models(settings)
    stages = ["backend_analysis", "frontend_analysis", "synthesis"]
    selected: dict[str, dict[str, str]] = {}
    candidate_chains: dict[str, list[dict[str, str]]] = {}
    fallback_events: list[dict[str, str]] = []

    overrides = {
        "backend_analysis": args.model_backend,
        "frontend_analysis": args.model_frontend,
        "synthesis": args.model_synthesis,
    }

    for stage in stages:
        ranked = select_candidates_for_stage(pool, stage=stage, strategy=args.strategy)
        chain = [{"model_id": m.model_id, "provider_key": m.provider_key} for m in ranked[:6]]
        candidate_chains[stage] = chain

        explicit = overrides.get(stage, "")
        chosen = _find_model(pool, explicit) if explicit else None
        if chosen is None and ranked:
            chosen = ranked[0]
        if chosen is None:
            # last-resort fallback to coder model (may not exist in enabled providers)
            selected[stage] = {"model_id": coder_model or "", "provider_key": ""}
            if args.fallback and chain:
                fallback_events.append(
                    {
                        "stage": stage,
                        "reason": "no_selected_model_in_pool",
                        "fallback_to": chain[0]["model_id"],
                    }
                )
                selected[stage] = chain[0]
        else:
            selected[stage] = {"model_id": chosen.model_id, "provider_key": chosen.provider_key}

    discovered_pool = [
        {
            "provider_key": m.provider_key,
            "provider_name": m.provider_name,
            "model_id": m.model_id,
            "tags": list(m.tags),
        }
        for m in pool
    ]
    return {
        "mode": args.mode,
        "strategy": args.strategy,
        "fallback": bool(args.fallback),
        "selected_by_stage": selected,
        "candidate_chains": candidate_chains,
        "fallback_events": fallback_events,
        "discovered_pool": discovered_pool,
    }


def _stage_preferred_tags_backend_workflow(stage: str) -> list[str]:
    """Slot tags for `/multi-backend`: authority vs auxiliary vs merge."""
    if stage == "backend_authority":
        return ["claude", "reasoning", "deepseek", "glm", "gpt", "quality", "general"]
    if stage == "auxiliary_reference":
        return ["gemini", "gpt", "general", "multimodal"]
    if stage == "backend_synthesis":
        return ["claude", "gpt", "reasoning", "general"]
    return ["general"]


def _score_model_backend(
    model: AvailableModel, *, stage: str, strategy: RoutingStrategy, index: int = 0
) -> float:
    tags = set(model.tags)
    score = 0.0
    for i, t in enumerate(_stage_preferred_tags_backend_workflow(stage)):
        if t in tags:
            score += max(0.0, 6.0 - i)
    if strategy == "quality-first":
        if "quality" in tags or "reasoning" in tags:
            score += 2.0
    elif strategy == "speed-first":
        if "cost-efficient" in tags:
            score += 1.0
    elif strategy == "cost-first":
        if "cost-efficient" in tags:
            score += 2.0
    score -= index * 0.0001
    return score


def _select_backend_stage(
    pool: list[AvailableModel], *, stage: str, strategy: RoutingStrategy
) -> list[AvailableModel]:
    ranked = sorted(
        enumerate(pool),
        key=lambda x: _score_model_backend(x[1], stage=stage, strategy=strategy, index=x[0]),
        reverse=True,
    )
    return [x[1] for x in ranked]


def build_backend_routing_plan(
    settings: Settings,
    args: MultiPlanRoutingArgs,
    *,
    coder_model: str = "",
) -> dict[str, Any]:
    """Config-driven routing for `/multi-backend` (authority / auxiliary / synthesis)."""
    pool = discover_available_models(settings)
    stages = ["backend_authority", "auxiliary_reference", "backend_synthesis"]
    selected: dict[str, dict[str, str]] = {}
    candidate_chains: dict[str, list[dict[str, str]]] = {}
    fallback_events: list[dict[str, str]] = []

    overrides = {
        "backend_authority": args.model_backend,
        "auxiliary_reference": args.model_frontend,
        "backend_synthesis": args.model_synthesis,
    }

    for stage in stages:
        ranked = _select_backend_stage(pool, stage=stage, strategy=args.strategy)
        chain = [{"model_id": m.model_id, "provider_key": m.provider_key} for m in ranked[:6]]
        candidate_chains[stage] = chain

        explicit = overrides.get(stage, "")
        chosen = _find_model(pool, explicit) if explicit else None
        if chosen is None and ranked:
            chosen = ranked[0]
        if chosen is None:
            selected[stage] = {"model_id": coder_model or "", "provider_key": ""}
            if args.fallback and chain:
                fallback_events.append(
                    {
                        "stage": stage,
                        "reason": "no_selected_model_in_pool",
                        "fallback_to": chain[0]["model_id"],
                    }
                )
                selected[stage] = chain[0]
        else:
            selected[stage] = {"model_id": chosen.model_id, "provider_key": chosen.provider_key}

    discovered_pool = [
        {
            "provider_key": m.provider_key,
            "provider_name": m.provider_name,
            "model_id": m.model_id,
            "tags": list(m.tags),
        }
        for m in pool
    ]
    return {
        "workflow": "backend",
        "mode": args.mode,
        "strategy": args.strategy,
        "fallback": bool(args.fallback),
        "selected_by_stage": selected,
        "candidate_chains": candidate_chains,
        "fallback_events": fallback_events,
        "discovered_pool": discovered_pool,
    }


def _stage_preferred_tags_frontend_workflow(stage: str) -> list[str]:
    """Slot tags for `/multi-frontend`: UI authority vs backend-angled auxiliary vs merge."""
    if stage == "frontend_authority":
        return ["gemini", "multimodal", "frontend", "gpt", "general", "quality"]
    if stage == "auxiliary_reference":
        return ["claude", "reasoning", "deepseek", "glm", "gpt", "general"]
    if stage == "frontend_synthesis":
        return ["claude", "gpt", "reasoning", "gemini", "general"]
    return ["general"]


def _score_model_frontend(
    model: AvailableModel, *, stage: str, strategy: RoutingStrategy, index: int = 0
) -> float:
    tags = set(model.tags)
    score = 0.0
    for i, t in enumerate(_stage_preferred_tags_frontend_workflow(stage)):
        if t in tags:
            score += max(0.0, 6.0 - i)
    if strategy == "quality-first":
        if "quality" in tags or "reasoning" in tags:
            score += 2.0
    elif strategy == "speed-first":
        if "cost-efficient" in tags:
            score += 1.0
    elif strategy == "cost-first":
        if "cost-efficient" in tags:
            score += 2.0
    score -= index * 0.0001
    return score


def _select_frontend_stage(
    pool: list[AvailableModel], *, stage: str, strategy: RoutingStrategy
) -> list[AvailableModel]:
    ranked = sorted(
        enumerate(pool),
        key=lambda x: _score_model_frontend(x[1], stage=stage, strategy=strategy, index=x[0]),
        reverse=True,
    )
    return [x[1] for x in ranked]


def build_frontend_routing_plan(
    settings: Settings,
    args: MultiPlanRoutingArgs,
    *,
    coder_model: str = "",
) -> dict[str, Any]:
    """Config-driven routing for `/multi-frontend` (UI authority / auxiliary / synthesis)."""
    pool = discover_available_models(settings)
    stages = ["frontend_authority", "auxiliary_reference", "frontend_synthesis"]
    selected: dict[str, dict[str, str]] = {}
    candidate_chains: dict[str, list[dict[str, str]]] = {}
    fallback_events: list[dict[str, str]] = []

    overrides = {
        "frontend_authority": args.model_frontend,
        "auxiliary_reference": args.model_backend,
        "frontend_synthesis": args.model_synthesis,
    }

    for stage in stages:
        ranked = _select_frontend_stage(pool, stage=stage, strategy=args.strategy)
        chain = [{"model_id": m.model_id, "provider_key": m.provider_key} for m in ranked[:6]]
        candidate_chains[stage] = chain

        explicit = overrides.get(stage, "")
        chosen = _find_model(pool, explicit) if explicit else None
        if chosen is None and ranked:
            chosen = ranked[0]
        if chosen is None:
            selected[stage] = {"model_id": coder_model or "", "provider_key": ""}
            if args.fallback and chain:
                fallback_events.append(
                    {
                        "stage": stage,
                        "reason": "no_selected_model_in_pool",
                        "fallback_to": chain[0]["model_id"],
                    }
                )
                selected[stage] = chain[0]
        else:
            selected[stage] = {"model_id": chosen.model_id, "provider_key": chosen.provider_key}

    discovered_pool = [
        {
            "provider_key": m.provider_key,
            "provider_name": m.provider_name,
            "model_id": m.model_id,
            "tags": list(m.tags),
        }
        for m in pool
    ]
    return {
        "workflow": "frontend",
        "mode": args.mode,
        "strategy": args.strategy,
        "fallback": bool(args.fallback),
        "selected_by_stage": selected,
        "candidate_chains": candidate_chains,
        "fallback_events": fallback_events,
        "discovered_pool": discovered_pool,
    }

