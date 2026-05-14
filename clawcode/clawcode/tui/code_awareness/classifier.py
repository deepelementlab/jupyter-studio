"""LLM-backed architecture classification with fallback rules."""

from __future__ import annotations

import json
import time
from json import JSONDecodeError
from typing import Any

from ...config.constants import AgentName
from ...config.settings import Settings
from ...llm.providers import create_provider, resolve_provider_from_model
from .bfs_outline import build_bfs_outline, read_readme_snippet
from .scanner import classify_path
from .state import ArchitectureMap

_LAYER_CANONICAL: dict[str, str] = {
    "core": "Core / Logic",
    "core / logic": "Core / Logic",
    "api": "API / Interface",
    "api / interface": "API / Interface",
    "config": "Config",
    "test": "Test",
    "docs": "Docs",
    "assets": "Assets",
    "other": "Other",
}

_STAGE1_BFS_MAX_DEPTH = 3
_STAGE1_BFS_MAX_TOTAL_PATHS = 400
_STAGE1_BFS_MAX_CHILDREN_PER_DIR = 30
_STAGE1_README_MAX_CHARS = 3500


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from mixed model output."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty response")
    # Fast path: strict object
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed
    raise ValueError("response is not a JSON object")


def _extract_json_object_loose(raw: str) -> dict[str, Any]:
    """Recover JSON object from markdown/codefence/wrapped text."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty response")

    # 1) fenced code blocks
    if "```" in text:
        chunks = text.split("```")
        for chunk in chunks:
            candidate = chunk.strip()
            if not candidate:
                continue
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

    # 2) first balanced {...}
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:
                        break
        start = text.find("{", start + 1)

    # 3) final strict attempt for better error messages
    return _extract_json_object(text)


def _normalize_layer(layer: str) -> str:
    key = (layer or "").strip().lower()
    canonical = _LAYER_CANONICAL.get(key)
    if canonical:
        return canonical
    cleaned = " ".join((layer or "").strip().split())
    if not cleaned:
        return "Other"
    return cleaned[:64]


def _fallback_dir_to_layer(directories: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for rel in directories:
        result[rel] = classify_path(rel).value
    return result


def _build_layers(dir_to_layer: dict[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for rel, layer in sorted(dir_to_layer.items()):
        grouped.setdefault(layer, []).append(rel)
    return grouped


def _build_layer_order(
    layers: dict[str, list[str]],
    preferred_order: list[str],
) -> list[str]:
    out: list[str] = []
    for name in preferred_order:
        if name in layers and name not in out:
            out.append(name)
    for name in sorted(layers.keys()):
        if name not in out:
            out.append(name)
    return out


def _extract_layer_meta(parsed: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Extract layer descriptions and order from parsed JSON payload."""
    layer_desc: dict[str, str] = {}
    layer_order: list[str] = []
    architecture_layers = parsed.get("architecture_layers")
    if isinstance(architecture_layers, list):
        for item in architecture_layers:
            if not isinstance(item, dict):
                continue
            name = _normalize_layer(str(item.get("name", "")))
            if not name:
                continue
            desc = " ".join(str(item.get("description", "")).strip().split())
            if desc:
                layer_desc[name] = desc[:200]
            if name not in layer_order:
                layer_order.append(name)
    raw_desc = parsed.get("layer_descriptions")
    if isinstance(raw_desc, dict):
        for k, v in raw_desc.items():
            name = _normalize_layer(str(k))
            desc = " ".join(str(v).strip().split())
            if name and desc:
                layer_desc[name] = desc[:200]
                if name not in layer_order:
                    layer_order.append(name)
    return layer_desc, layer_order


async def _analyze_layers_with_llm(
    *,
    provider: Any,
    working_directory: str,
) -> tuple[dict[str, str], list[str], str | None, dict[str, Any]]:
    """Stage 1: infer project-specific layers and short descriptions."""
    outline = build_bfs_outline(
        working_directory,
        max_depth=_STAGE1_BFS_MAX_DEPTH,
        max_total_paths=_STAGE1_BFS_MAX_TOTAL_PATHS,
        max_children_per_dir=_STAGE1_BFS_MAX_CHILDREN_PER_DIR,
    )
    readme_snippet = read_readme_snippet(
        working_directory,
        max_chars=_STAGE1_README_MAX_CHARS,
    )
    base_prompt = (
        "Analyze this project's architecture from top-down directory outline and project context.\n"
        "Do not output directory-to-layer mapping in this step.\n"
        "Return strict JSON only:\n"
        '{"architecture_layers":[{"name":"Layer","description":"brief"}],'
        '"layer_descriptions":{"Layer":"brief"},'
        '"layer_order":["Layer"]}\n'
        "Rules:\n"
        "- Keep layer names concise and meaningful\n"
        "- Prefer 4-10 layers\n"
        "- layer_order should reflect top-down architecture flow\n"
        "- top_level_dirs are expected to be fully covered in your architecture decomposition\n"
        "- deeper levels may be sampled; infer based on names and hierarchy\n"
        "- Avoid one huge catch-all layer for most of the codebase; "
        "if you see internal/, pkg/, src/, or subtrees like domain/, app/, infra/, "
        "platform/, use separate layers for those roles instead of lumping them into Other\n"
        "- In Go-style layouts, internal/ usually holds private application code — "
        "propose layers that reflect domain vs delivery vs infrastructure, not a single Other bucket\n"
        "Project context (README snippet):\n"
        + (readme_snippet or "<no-readme>")
        + "\nDirectory outline:\n"
        + json.dumps(outline, ensure_ascii=False)
    )
    outline_stats = dict(outline.get("stats", {}))
    parse_err: str | None = None
    parsed: Any = None
    for attempt in range(2):
        prompt = base_prompt
        if attempt == 1:
            prompt += (
                "\nIMPORTANT:\n"
                "- Return JSON object only.\n"
                "- No markdown/code fences.\n"
            )
        response = await provider.send_messages(
            messages=[
                {"role": "system", "content": "You are a strict JSON generator."},
                {"role": "user", "content": prompt},
            ],
            tools=None,
        )
        raw = (response.content or "").strip()
        try:
            parsed = _extract_json_object_loose(raw)
            parse_err = None
            break
        except (JSONDecodeError, ValueError, TypeError) as exc:
            parse_err = str(exc)
            continue
    if not isinstance(parsed, dict):
        return {}, [], parse_err or "failed to parse layer analysis response", outline_stats
    desc, order = _extract_layer_meta(parsed)
    if not order and desc:
        order = list(desc.keys())
    if not order:
        return {}, [], "missing architecture_layers/layer_order", outline_stats
    return desc, order, None, outline_stats


async def _classify_batch_with_llm(
    *,
    provider: Any,
    directories: list[str],
    strict_prompt_prefix: str,
) -> tuple[dict[str, str], dict[str, str], list[str], str | None]:
    """Classify one directory batch via LLM and return mapping/meta/error."""
    base_prompt = (
        strict_prompt_prefix
        + "\nDirectories:\n"
        + json.dumps(directories, ensure_ascii=False)
    )
    parse_err: str | None = None
    parsed: Any = None
    for attempt in range(2):
        prompt = base_prompt
        if attempt == 1:
            prompt += (
                "\nIMPORTANT:\n"
                "- Return JSON only.\n"
                "- Do not wrap with markdown or explanations.\n"
            )
        response = await provider.send_messages(
            messages=[
                {"role": "system", "content": "You are a strict JSON generator."},
                {"role": "user", "content": prompt},
            ],
            tools=None,
        )
        raw = (response.content or "").strip()
        try:
            parsed = _extract_json_object_loose(raw)
            parse_err = None
            break
        except (JSONDecodeError, ValueError, TypeError) as exc:
            parse_err = str(exc)
            continue

    if parsed is None:
        return {}, {}, [], parse_err or "failed to parse model response"
    if not isinstance(parsed, dict):
        return {}, {}, [], "response is not a JSON object"
    if "dir_to_layer" not in parsed:
        return {}, {}, [], "missing dir_to_layer field"
    raw_map = parsed.get("dir_to_layer", {}) if isinstance(parsed, dict) else {}
    if not isinstance(raw_map, dict):
        return {}, {}, [], "invalid dir_to_layer shape"
    if not any(rel in raw_map for rel in directories):
        return {}, {}, [], "dir_to_layer does not contain batch paths"
    result: dict[str, str] = {}
    for rel in directories:
        layer = _normalize_layer(str(raw_map.get(rel, "Other")))
        result[rel] = layer
    layer_desc, layer_order = _extract_layer_meta(parsed)
    return result, layer_desc, layer_order, None


async def classify_architecture_map(
    *,
    working_directory: str,
    settings: Settings,
    directories: list[str],
) -> ArchitectureMap:
    """Return architecture mapping, preferring LLM and falling back to rules."""
    now = time.time()
    model_info: dict[str, Any] = {
        "available": False,
        "last_attempt_at": now,
    }
    if not directories:
        return ArchitectureMap(
            project_root=working_directory,
            updated_at=now,
            source="fallback_rules",
            model_info=model_info,
            layers={},
            dir_to_layer={},
        )

    try:
        agent_cfg = settings.get_agent_config(AgentName.CODER)
        provider_name, provider_key = resolve_provider_from_model(
            agent_cfg.model,
            settings,
            agent_cfg,
        )
        provider_cfg = settings.providers.get(provider_key)
        api_key = getattr(provider_cfg, "api_key", None) if provider_cfg else None
        base_url = getattr(provider_cfg, "base_url", None) if provider_cfg else None
        provider = create_provider(
            provider_name=provider_name,
            model_id=agent_cfg.model,
            api_key=api_key,
            base_url=base_url,
        )
        model_info = {
            "available": True,
            "provider": provider_name,
            "provider_key": provider_key,
            "model": agent_cfg.model,
            "last_attempt_at": now,
        }
        # Two-stage prompting:
        # stage1 -> infer architecture layers, stage2 -> map directories to those layers.
        stage1_desc, stage1_order, stage1_err, stage1_outline_stats = await _analyze_layers_with_llm(
            provider=provider,
            working_directory=working_directory,
        )
        model_info["stage1_outline_stats"] = stage1_outline_stats
        if stage1_order:
            model_info["two_stage"] = True
        if stage1_err:
            model_info["stage1_error"] = stage1_err
        strict_prompt_prefix = (
            "Map directories to project-specific architecture layers.\n"
            "Return strict JSON object only, format:\n"
            '{"dir_to_layer":{"path":"Layer"}}\n'
            "Rules:\n"
            "- use exact path keys from input\n"
            "- every path must exist in output\n"
            "- choose layer names from provided layer_order when possible\n"
            "- Map paths by meaning: e.g. internal/domain → domain/core layer, "
            "internal/app or internal/api → application/delivery, internal/infra → infrastructure, "
            "internal/platform → shared platform — do NOT assign the whole internal/* subtree to Other "
            "just because it is under internal/\n"
            "- Prefer adding/using a distinct layer name from layer_order over Other when the folder name "
            "clearly indicates a role (domain, app, infra, platform, tools, etc.)\n"
            "- Use Other only for paths that genuinely do not fit any layer you defined\n"
            "Layer context:\n"
            + json.dumps(
                {
                    "layer_order": stage1_order,
                    "layer_descriptions": stage1_desc,
                },
                ensure_ascii=False,
            )
        )
        dir_to_layer: dict[str, str] = {}
        layer_descriptions: dict[str, str] = dict(stage1_desc)
        llm_layer_order: list[str] = list(stage1_order)
        batch_size = 120
        llm_batches = 0
        fallback_batches = 0
        errors: list[str] = []
        for i in range(0, len(directories), batch_size):
            batch = directories[i:i + batch_size]
            mapped, desc, order, err = await _classify_batch_with_llm(
                provider=provider,
                directories=batch,
                strict_prompt_prefix=strict_prompt_prefix,
            )
            if err is None and mapped:
                dir_to_layer.update(mapped)
                layer_descriptions.update(desc)
                for name in order:
                    if name not in llm_layer_order:
                        llm_layer_order.append(name)
                llm_batches += 1
            else:
                fb = _fallback_dir_to_layer(batch)
                dir_to_layer.update(fb)
                fallback_batches += 1
                if err:
                    errors.append(err)

        source = "llm" if llm_batches > 0 else "fallback_rules"
        if fallback_batches > 0:
            model_info["partial_fallback"] = True
            model_info["fallback_batches"] = fallback_batches
            model_info["llm_batches"] = llm_batches
            if errors:
                model_info["error"] = errors[-1]
                model_info["last_error"] = errors[-1]
        if stage1_err and "error" not in model_info:
            model_info["error"] = stage1_err
            model_info["last_error"] = stage1_err
        layers = _build_layers(dir_to_layer)
        return ArchitectureMap(
            project_root=working_directory,
            updated_at=now,
            source=source,
            model_info=model_info,
            layers=layers,
            dir_to_layer=dir_to_layer,
            layer_descriptions=layer_descriptions,
            layer_order=_build_layer_order(layers, llm_layer_order),
        )
    except Exception as exc:
        err = str(exc) or exc.__class__.__name__
        model_info["error"] = err
        model_info["last_error"] = err
        dir_to_layer = _fallback_dir_to_layer(directories)
        return ArchitectureMap(
            project_root=working_directory,
            updated_at=now,
            source="fallback_rules",
            model_info=model_info,
            layers=_build_layers(dir_to_layer),
            dir_to_layer=dir_to_layer,
            layer_descriptions={},
            layer_order=[],
        )

