from __future__ import annotations

import hashlib
import contextlib
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings


def _events_file_path() -> Path:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    rel = settings.closed_loop.observability_events_file
    return (data_dir / rel).resolve()


def _tuning_state_path() -> Path:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    return (data_dir / "claw_metrics" / "tuning_state.json").resolve()


def _reports_dir_path() -> Path:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    rel = str(getattr(settings.closed_loop, "tuning_export_reports_dir", "claw_metrics/reports") or "claw_metrics/reports")
    return (data_dir / rel).resolve()


@dataclass(frozen=True)
class DomainPolicyTemplate:
    template_id: str
    flush_budget_hit_threshold: int = 3
    flush_dup_skip_threshold: int = 6
    snippet_penalty_threshold: float = 0.22
    snippet_penalty_target: float = 0.30
    flush_max_writes_delta: int = 1
    flush_max_writes_min: int = 1
    flush_max_writes_max: int = 8
    max_recommendations: int = 8


def _base_templates() -> dict[str, DomainPolicyTemplate]:
    return {
        "general": DomainPolicyTemplate("general"),
        "backend": DomainPolicyTemplate(
            "backend",
            flush_budget_hit_threshold=2,
            flush_dup_skip_threshold=5,
            snippet_penalty_threshold=0.24,
            snippet_penalty_target=0.29,
            flush_max_writes_max=10,
        ),
        "frontend": DomainPolicyTemplate(
            "frontend",
            flush_budget_hit_threshold=4,
            flush_dup_skip_threshold=7,
            snippet_penalty_threshold=0.18,
            snippet_penalty_target=0.26,
        ),
        "database": DomainPolicyTemplate(
            "database",
            flush_budget_hit_threshold=2,
            flush_dup_skip_threshold=4,
            snippet_penalty_threshold=0.20,
            snippet_penalty_target=0.28,
            flush_max_writes_delta=2,
            flush_max_writes_max=12,
        ),
        "devops": DomainPolicyTemplate(
            "devops",
            flush_budget_hit_threshold=3,
            flush_dup_skip_threshold=5,
            snippet_penalty_threshold=0.21,
            snippet_penalty_target=0.29,
        ),
    }


def _template_for_domain(domain: str | None) -> DomainPolicyTemplate:
    templates = _base_templates()
    key = (domain or "general").strip().lower() or "general"
    tpl = templates.get(key, templates["general"])
    try:
        overrides = dict(getattr(get_settings().closed_loop, "tuning_domain_templates", {}) or {})
        dom_cfg = overrides.get(key) or {}
        if isinstance(dom_cfg, dict) and dom_cfg:
            values = {k: v for k, v in dom_cfg.items() if k in DomainPolicyTemplate.__dataclass_fields__}
            tpl = DomainPolicyTemplate(**{**tpl.__dict__, **values})
    except Exception:
        pass
    return tpl


def emit_ops_event(event_type: str, payload: dict[str, Any]) -> None:
    try:
        settings = get_settings()
        if not settings.closed_loop.observability_enabled:
            return
        path = _events_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": int(time.time()),
            "event_type": event_type,
            "payload": payload,
            "trace_id": str(payload.get("trace_id", "") or ""),
            "cycle_id": str(payload.get("cycle_id", "") or ""),
            "policy_hash": str(payload.get("policy_hash", "") or ""),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        return


def resolve_domain(explicit_domain: str | None, context: dict[str, Any] | None = None) -> tuple[str, float]:
    if explicit_domain and explicit_domain.strip():
        return explicit_domain.strip().lower(), 1.0
    ctx = context or {}
    title = str(ctx.get("session_title", "") or "").lower()
    query = str(ctx.get("query", "") or "").lower()
    tool_name = str(ctx.get("tool_name", "") or "").lower()
    text = " ".join(x for x in [title, query, tool_name] if x)
    rules: list[tuple[str, list[str]]] = [
        ("frontend", ["react", "vue", "css", "ui", "frontend"]),
        ("backend", ["api", "backend", "service", "endpoint"]),
        ("python", ["python", "pytest", "pip", "uv"]),
        ("golang", ["golang", "go ", "gofmt", "gopls"]),
        ("database", ["sql", "db", "postgres", "mysql", "sqlite"]),
        ("devops", ["docker", "k8s", "kubernetes", "deploy", "ci"]),
    ]
    for domain, keys in rules:
        if any(k in text for k in keys):
            return domain, 0.72
    return "general", 0.35


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    p = payload if isinstance(payload, dict) else {}
    out = dict(row)
    out["payload"] = p
    out["session_id"] = str(p.get("session_id", "") or "")
    out["domain"] = str(p.get("domain", "") or "")
    return out


def load_recent_events(window_hours: int = 24, *, domain: str | None = None, session_id: str | None = None) -> list[dict[str, Any]]:
    try:
        path = _events_file_path()
    except Exception:
        return []
    if not path.exists():
        return []
    cutoff = int(time.time()) - max(1, int(window_hours)) * 3600
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                ts = int(row.get("ts", 0) or 0)
                if ts >= cutoff:
                    rr = _normalize_row(row)
                    if domain and rr.get("domain") != domain:
                        continue
                    if session_id and rr.get("session_id") != session_id:
                        continue
                    out.append(rr)
    except OSError:
        return []
    return out


def build_long_term_metrics(
    *,
    windows_days: tuple[int, ...] = (7, 30, 90),
    domain: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {"windows": {}}
    global_baseline: dict[str, float] = {}
    for days in windows_days:
        hrs = max(24, int(days) * 24)
        rows = load_recent_events(window_hours=hrs, domain=domain, session_id=session_id)
        base_rows = load_recent_events(window_hours=hrs)
        apply_count = 0
        rollback_count = 0
        score_samples: list[float] = []
        for r in rows:
            et = str(r.get("event_type", ""))
            p = r.get("payload", {}) or {}
            if et in {"tuning_apply", "tuning_guarded_apply"}:
                apply_count += int(p.get("applied_count", 0) or 0)
            if et == "tuning_rollback":
                rollback_count += 1
            if et == "experience_feedback":
                try:
                    score_samples.append(float(p.get("score", 0.0) or 0.0))
                except Exception:
                    pass
        avg_score = (sum(score_samples) / len(score_samples)) if score_samples else 0.0
        stability = 1.0 - min(1.0, rollback_count / max(1, apply_count))
        regression_penalty = min(1.0, rollback_count / max(1, len(rows)))
        volatility_penalty = min(1.0, abs(apply_count - rollback_count) / max(1, apply_count + rollback_count))
        combined = max(0.0, min(1.0, (0.50 * stability) + (0.30 * avg_score) - (0.12 * regression_penalty) - (0.08 * volatility_penalty)))
        # baseline correction across domain/session
        b_apply = 0
        b_rollback = 0
        b_scores: list[float] = []
        for r in base_rows:
            et = str(r.get("event_type", ""))
            p = r.get("payload", {}) or {}
            if et in {"tuning_apply", "tuning_guarded_apply"}:
                b_apply += int(p.get("applied_count", 0) or 0)
            if et == "tuning_rollback":
                b_rollback += 1
            if et == "experience_feedback":
                with contextlib.suppress(Exception):
                    b_scores.append(float(p.get("score", 0.0) or 0.0))
        b_avg = (sum(b_scores) / len(b_scores)) if b_scores else 0.0
        b_stability = 1.0 - min(1.0, b_rollback / max(1, b_apply))
        b_reg = min(1.0, b_rollback / max(1, len(base_rows)))
        b_vol = min(1.0, abs(b_apply - b_rollback) / max(1, b_apply + b_rollback))
        baseline_combined = max(0.0, min(1.0, (0.50 * b_stability) + (0.30 * b_avg) - (0.12 * b_reg) - (0.08 * b_vol)))
        global_baseline[str(days)] = round(baseline_combined, 4)
        normalized_combined = max(0.0, min(1.0, 0.5 + (combined - baseline_combined)))
        metrics["windows"][str(days)] = {
            "event_count": len(rows),
            "tuning_apply_count": apply_count,
            "tuning_rollback_count": rollback_count,
            "experience_avg_score": round(avg_score, 4),
            "stability_score": round(stability, 4),
            "regression_penalty": round(regression_penalty, 4),
            "volatility_penalty": round(volatility_penalty, 4),
            "combined_score": round(combined, 4),
            "normalized_combined_score": round(normalized_combined, 4),
            "score": round((0.6 * stability) + (0.4 * avg_score), 4),
        }
    order = [str(x) for x in sorted(int(k) for k in metrics["windows"].keys())]
    trend: list[dict[str, Any]] = []
    for i in range(1, len(order)):
        prev = metrics["windows"][order[i - 1]]
        cur = metrics["windows"][order[i]]
        trend.append(
            {
                "from_days": order[i - 1],
                "to_days": order[i],
                "score_delta": round(float(cur.get("combined_score", 0.0)) - float(prev.get("combined_score", 0.0)), 4),
            }
        )
    metrics["trend"] = trend
    positive = sum(1 for t in trend if float(t.get("score_delta", 0.0) or 0.0) > 0)
    negative = sum(1 for t in trend if float(t.get("score_delta", 0.0) or 0.0) < 0)
    metrics["trend_consistency"] = (
        "improving" if positive > negative else "degrading" if negative > positive else "mixed"
    )
    min_samples = min([int((metrics["windows"][x] or {}).get("event_count", 0) or 0) for x in order] + [0])
    sample_factor = min(1.0, min_samples / 20.0)
    vol_mean = (
        sum(float((metrics["windows"][x] or {}).get("volatility_penalty", 0.0) or 0.0) for x in order) / max(1, len(order))
    )
    metrics["trend_confidence"] = round(max(0.0, min(1.0, (0.7 * sample_factor) + (0.3 * (1.0 - vol_mean)))), 4)
    metrics["normalization"] = {
        "domain": domain or "all",
        "session_id": session_id or "all",
        "method": "baseline_correction",
        "domain_baseline": global_baseline,
        "session_baseline": global_baseline,
        "global_anchor": global_baseline,
    }
    return metrics


def build_ops_report(window_hours: int = 24) -> dict[str, Any]:
    rows = load_recent_events(window_hours=window_hours)
    counts: dict[str, int] = {}
    for r in rows:
        et = str(r.get("event_type", "unknown"))
        counts[et] = counts.get(et, 0) + 1
    return {
        "window_hours": window_hours,
        "event_count": len(rows),
        "counts": counts,
    }


def _single_layer_suggestions(rows: list[dict[str, Any]], *, layer: str, domain: str | None = None, session_id: str | None = None) -> list[dict[str, Any]]:
    tpl = _template_for_domain(domain)
    flush_budget_hits = 0
    flush_dup_skips = 0
    search_penalties: list[float] = []
    for r in rows:
        et = str(r.get("event_type", ""))
        p = r.get("payload", {}) or {}
        if et == "agent_closed_loop_metrics":
            flush_budget_hits += int(p.get("flush_budget_hit", 0) or 0)
            flush_dup_skips += int(p.get("flush_dup_skip", 0) or 0)
        elif et == "search_rank_breakdown":
            try:
                search_penalties.append(float(p.get("snippet_penalty", 0.0) or 0.0))
            except Exception:
                pass
    recs: list[dict[str, Any]] = []
    if flush_budget_hits >= tpl.flush_budget_hit_threshold:
        delta = int(max(-4, min(4, tpl.flush_max_writes_delta)))
        recs.append(
            {
                "param": "closed_loop.flush_max_writes",
                "suggested_delta": delta,
                "reason": f"flush_budget_hits={flush_budget_hits} in window",
                "layer": layer,
                "domain": domain,
                "session_id": session_id,
                "template_id": tpl.template_id,
                "guardrail": {"min": tpl.flush_max_writes_min, "max": tpl.flush_max_writes_max},
            }
        )
    if flush_dup_skips >= tpl.flush_dup_skip_threshold:
        recs.append(
            {
                "param": "closed_loop.flush_duplicate_suppression",
                "suggested_value": True,
                "reason": f"flush_duplicate_skips={flush_dup_skips} in window",
                "layer": layer,
                "domain": domain,
                "session_id": session_id,
                "template_id": tpl.template_id,
            }
        )
    if search_penalties:
        avg_penalty = sum(search_penalties) / len(search_penalties)
        if avg_penalty > tpl.snippet_penalty_threshold:
            recs.append(
                {
                    "param": "closed_loop.search_snippet_penalty_cap",
                    "suggested_value": tpl.snippet_penalty_target,
                    "reason": f"avg_snippet_penalty={avg_penalty:.3f} too high",
                    "layer": layer,
                    "domain": domain,
                    "session_id": session_id,
                    "template_id": tpl.template_id,
                }
            )
    return recs[: max(1, int(tpl.max_recommendations))]


def _merge_layered_recommendations(layered: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    # low -> high, so high priority overrides
    for lname in ["global", "domain", "session"]:
        for rec in layered.get(lname, []):
            key = str(rec.get("param", ""))
            old = merged.get(key)
            if old is not None:
                rec["overridden_by"] = lname
            merged[key] = rec
    return list(merged.values())


def build_layered_tuning_suggestions(
    window_hours: int = 24,
    *,
    domain: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    all_rows = load_recent_events(window_hours=window_hours)
    domain_rows = load_recent_events(window_hours=window_hours, domain=domain) if domain else []
    session_rows = load_recent_events(window_hours=window_hours, session_id=session_id) if session_id else []
    layered = {
        "global": _single_layer_suggestions(all_rows, layer="global"),
        "domain": _single_layer_suggestions(domain_rows, layer="domain", domain=domain),
        "session": _single_layer_suggestions(session_rows, layer="session", domain=domain, session_id=session_id),
    }
    merged = _merge_layered_recommendations(layered)
    return {
        "window_hours": window_hours,
        "samples": {"global": len(all_rows), "domain": len(domain_rows), "session": len(session_rows)},
        "layered_recommendations": layered,
        "recommendations": merged,
    }


def build_tuning_suggestions(window_hours: int = 24) -> dict[str, Any]:
    # backward-compatible global entry, now powered by layered engine
    payload = build_layered_tuning_suggestions(window_hours=window_hours)
    payload["samples"] = payload.get("samples", {}).get("global", 0)
    return payload


def build_layered_comparison_report(
    window_hours: int = 24,
    *,
    domain: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    layered = build_layered_tuning_suggestions(window_hours=window_hours, domain=domain, session_id=session_id)
    json_report = {
        "window_hours": window_hours,
        "domain": domain,
        "session_id": session_id,
        "samples": layered.get("samples", {}),
        "layered_recommendations": layered.get("layered_recommendations", {}),
        "effective_recommendations": layered.get("recommendations", []),
    }
    try:
        topn = int(getattr(get_settings().closed_loop, "tuning_report_top_n", 8) or 8)
    except Exception:
        topn = 8
    effective = list(json_report["effective_recommendations"])[: max(1, topn)]
    lines = [
        "## Layered Tuning Comparison",
        f"- window_hours: {window_hours}",
        f"- domain: {domain or 'auto'}",
        f"- session_id: {session_id or 'n/a'}",
        f"- sample_counts: {json_report['samples']}",
        "",
        "### Effective Recommendations (Top-N)",
    ]
    if not effective:
        lines.append("- none")
    else:
        for rec in effective:
            param = rec.get("param", "")
            layer = rec.get("layer", "")
            reason = rec.get("reason", "")
            val = rec.get("suggested_value", rec.get("suggested_delta"))
            lines.append(f"- [{layer}] `{param}` => `{val}` ({reason})")
    lines.append("")
    lines.append("### JSON Summary")
    lines.append("```json")
    lines.append(json.dumps(json_report, ensure_ascii=False, indent=2))
    lines.append("```")
    return {"json_report": json_report, "markdown_report": "\n".join(lines)}


def _prune_old_reports(dir_path: Path, keep_count: int) -> None:
    if keep_count <= 0:
        return
    files = sorted([p for p in dir_path.glob("*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[keep_count:]:
        with contextlib.suppress(OSError):
            stale.unlink()


def export_layered_report(
    *,
    json_report: dict[str, Any],
    markdown_report: str,
    domain: str | None = None,
) -> dict[str, Any]:
    try:
        settings = get_settings()
        if not bool(getattr(settings.closed_loop, "tuning_export_reports_enabled", True)):
            return {"success": False, "skipped": "tuning_export_reports_enabled=false"}
        reports_dir = _reports_dir_path()
        keep_count = int(getattr(settings.closed_loop, "tuning_export_retention_count", 50) or 50)
    except Exception:
        reports_dir = (Path.cwd() / ".clawcode" / "reports").resolve()
        keep_count = 50
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    dom = (domain or "general").replace("/", "_").replace("\\", "_")
    stem = f"{ts}-{dom}"
    md_path = reports_dir / f"{stem}.md"
    json_path = reports_dir / f"{stem}.json"
    md_path.write_text(markdown_report, encoding="utf-8")
    json_path.write_text(json.dumps(json_report, ensure_ascii=False, indent=2), encoding="utf-8")
    _prune_old_reports(reports_dir, keep_count=keep_count)
    return {"success": True, "md_path": str(md_path), "json_path": str(json_path)}


def _config_file_path() -> Path:
    from ..config.settings import Settings

    p = Settings._find_config_file()
    if p is not None:
        return p
    return Path.cwd() / ".clawcode.json"


def _rollback_state_path() -> Path:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    return (data_dir / "claw_metrics" / "tuning_rollback.json").resolve()


def _governance_audit_path() -> Path:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    return (data_dir / "claw_metrics" / "governance_audit.jsonl").resolve()


def _governance_pending_path() -> Path:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    return (data_dir / "claw_metrics" / "governance_pending.jsonl").resolve()


def _slo_state_path() -> Path:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    return (data_dir / "claw_metrics" / "slo_state.json").resolve()


def _load_slo_state() -> dict[str, Any]:
    p = _slo_state_path()
    if not p.exists():
        return {"frozen_params": {}, "degradation_streak": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"frozen_params": {}, "degradation_streak": {}}
    except Exception:
        return {"frozen_params": {}, "degradation_streak": {}}


def _save_slo_state(state: dict[str, Any]) -> None:
    p = _slo_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_slo_policy_templates(*, domain: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    try:
        cfg = dict(getattr(get_settings().closed_loop, "slo_policy_templates", {}) or {})
    except Exception:
        cfg = {}
    global_tpl = dict(
        {
            "policy_id": "slo-default-v2",
            "policy_version": "2.0.0",
            "degrade_streak_to_freeze": 2,
            "recover_streak_to_unfreeze": 0,
            "freeze_ttl_seconds": 900,
            "cooldown_seconds": 300,
        }
    )
    global_tpl.update(dict(cfg.get("global", {}) or {}))
    scope = "global"
    if domain:
        dom_map = dict(cfg.get("domain", {}) or {})
        d_tpl = dict(dom_map.get(domain, {}) or {})
        if d_tpl:
            global_tpl.update(d_tpl)
            scope = "domain"
    if session_id:
        ses_map = dict(cfg.get("session", {}) or {})
        s_tpl = dict(ses_map.get(session_id, {}) or {})
        if s_tpl:
            global_tpl.update(s_tpl)
            scope = "session"
    global_tpl["policy_scope"] = scope
    global_tpl["policy_hash"] = hashlib.sha1(
        json.dumps(global_tpl, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return global_tpl


def evaluate_slo_guardrail(
    recommendations: list[dict[str, Any]],
    *,
    domain: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Freeze/unfreeze params by degradation streak from long-term metrics."""
    state = _load_slo_state()
    frozen = dict(state.get("frozen_params", {}) or {})
    streaks = dict(state.get("degradation_streak", {}) or {})
    lt = build_long_term_metrics(domain=domain, session_id=session_id)
    trend = list(lt.get("trend", []) or [])
    degrading = bool(trend and any(float(t.get("score_delta", 0.0) or 0.0) < 0 for t in trend))
    updated: list[str] = []
    unfrozen: list[str] = []
    policy = load_slo_policy_templates(domain=domain, session_id=session_id)
    now = int(time.time())
    for k in list(frozen.keys()):
        until_ts = int((frozen.get(k, {}) or {}).get("freeze_until_ts", 0) or 0)
        if until_ts > 0 and until_ts <= now:
            frozen.pop(k, None)
    for rec in recommendations:
        param = str(rec.get("param", "") or "")
        if not param:
            continue
        cur = int(streaks.get(param, 0) or 0)
        cur = cur + 1 if degrading else max(0, cur - 1)
        streaks[param] = cur
        if cur >= int(policy["degrade_streak_to_freeze"]) and param not in frozen:
            frozen[param] = {
                "reason": "degradation_streak",
                "at_ts": now,
                "freeze_until_ts": now + int(policy.get("freeze_ttl_seconds", 900) or 900),
                "policy_id": policy["policy_id"],
            }
            updated.append(param)
        if cur <= int(policy["recover_streak_to_unfreeze"]) and param in frozen:
            frozen.pop(param, None)
            unfrozen.append(param)
    state["frozen_params"] = frozen
    state["degradation_streak"] = streaks
    _save_slo_state(state)
    return {
        "frozen_params": sorted(list(frozen.keys())),
        "newly_frozen": sorted(updated),
        "newly_unfrozen": sorted(unfrozen),
        "slo_state": "frozen" if frozen else "normal",
        "degrading": degrading,
        "policy_id": str(policy["policy_id"]),
        "policy_version": str(policy.get("policy_version", "1.0.0")),
        "policy_scope": str(policy.get("policy_scope", "global")),
        "policy_hash": str(policy.get("policy_hash", "")),
        "freeze_reason": "degradation_streak" if updated else "",
        "freeze_until_ts": max(
            [int((frozen.get(k, {}) or {}).get("freeze_until_ts", 0) or 0) for k in frozen.keys()] + [0]
        ),
    }


def _load_config_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_config_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".claw_cfg_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            if os.path.exists(tmp):
                os.unlink(tmp)


def rollback_last_tuning_apply() -> dict[str, Any]:
    path = _config_file_path()
    rb_path = _rollback_state_path()
    if not rb_path.exists():
        return {"success": False, "error": "rollback_state_not_found"}
    try:
        payload = json.loads(rb_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"success": False, "error": f"rollback_state_invalid:{e}"}
    snapshot = payload.get("config_before")
    if not isinstance(snapshot, dict):
        return {"success": False, "error": "rollback_snapshot_missing"}
    _write_config_json(path, snapshot)
    emit_ops_event("tuning_rollback", {"reason": payload.get("reason", "manual")})
    return {"success": True, "path": str(path), "rollback_ref": payload.get("rollback_ref")}


def record_governance_decision(
    *,
    action: str,
    scope: str = "all",
    operator: str = "system",
    evidence_refs: list[str] | None = None,
    rollback_ref: str | None = None,
    payload: dict[str, Any] | None = None,
    slo_state: str | None = None,
    freeze_reason: str | None = None,
    policy_id: str | None = None,
    policy_scope: str | None = None,
    policy_version: str | None = None,
    policy_hash: str | None = None,
    trace_id: str | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    decision_id = f"gov-{uuid.uuid4().hex[:12]}"
    row = {
        "decision_id": decision_id,
        "action": action,
        "scope": scope,
        "operator": operator,
        "timestamp": int(time.time()),
        "evidence_refs": list(evidence_refs or []),
        "rollback_ref": rollback_ref or "",
        "payload": dict(payload or {}),
        "slo_state": slo_state or "",
        "freeze_reason": freeze_reason or "",
        "policy_id": policy_id or "",
        "policy_scope": policy_scope or "",
        "policy_version": policy_version or "",
        "policy_hash": policy_hash or "",
        "trace_id": trace_id or "",
        "cycle_id": cycle_id or "",
    }
    path = _governance_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    emit_ops_event("governance_decision", {"decision_id": decision_id, "action": action, "scope": scope})
    return row


def apply_tuning_suggestions(
    recommendations: list[dict[str, Any]],
    *,
    apply_scope: str = "all",
    domain: str | None = None,
    session_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    try:
        settings = get_settings()
    except Exception:
        settings = None
    cooldown_minutes = int(getattr(getattr(settings, "closed_loop", object()), "tuning_cooldown_minutes", 120) or 120)
    state_path = None
    now = int(time.time())
    if settings is not None:
        state_path = _tuning_state_path()
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                state = {}
            last_ts = int(state.get("last_applied_ts", 0) or 0)
            if last_ts > 0 and (now - last_ts) < cooldown_minutes * 60:
                return {
                    "success": False,
                    "skipped": "cooldown_active",
                    "remaining_seconds": cooldown_minutes * 60 - (now - last_ts),
                    "applied": [],
                }
    path = _config_file_path()
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    closed_loop = data.get("closed_loop")
    if not isinstance(closed_loop, dict):
        closed_loop = {}
    applied: list[dict[str, Any]] = []
    for rec in recommendations:
        layer = str(rec.get("layer", "global") or "global")
        if apply_scope == "domain" and layer != "domain":
            continue
        if apply_scope == "session" and layer != "session":
            continue
        if apply_scope == "global" and layer != "global":
            continue
        param = str(rec.get("param", ""))
        if not param.startswith("closed_loop."):
            continue
        key = param.split(".", 1)[1]
        if "suggested_value" in rec:
            closed_loop[key] = rec["suggested_value"]
            applied.append(
                {
                    "param": param,
                    "value": rec["suggested_value"],
                    "layer": layer,
                    "domain": rec.get("domain", domain),
                    "session_id": rec.get("session_id", session_id),
                    "overridden_by": rec.get("overridden_by"),
                }
            )
        elif "suggested_delta" in rec:
            cur = int(closed_loop.get(key, 0) or 0)
            nxt = cur + int(rec["suggested_delta"])
            guard = rec.get("guardrail")
            if isinstance(guard, dict):
                gmin = int(guard.get("min", 1) or 1)
                gmax = int(guard.get("max", 999) or 999)
                closed_loop[key] = max(gmin, min(gmax, nxt))
            else:
                closed_loop[key] = max(1, nxt)
            applied.append(
                {
                    "param": param,
                    "value": closed_loop[key],
                    "layer": layer,
                    "domain": rec.get("domain", domain),
                    "session_id": rec.get("session_id", session_id),
                    "overridden_by": rec.get("overridden_by"),
                }
            )
    if dry_run:
        return {"success": True, "dry_run": True, "path": str(path), "applied": applied}
    data["closed_loop"] = closed_loop
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".claw_cfg_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
    if state_path is not None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"last_applied_ts": now, "applied_count": len(applied)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    emit_ops_event("tuning_apply", {"applied_count": len(applied)})
    return {"success": True, "path": str(path), "applied": applied}


def guarded_apply_tuning_suggestions(
    recommendations: list[dict[str, Any]],
    *,
    apply_scope: str = "all",
    domain: str | None = None,
    session_id: str | None = None,
    dry_run: bool = False,
    trace_id: str | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """Apply tuning with guardrails, rollback snapshot, and simple threshold protection."""
    guardrail = evaluate_slo_guardrail(recommendations, domain=domain, session_id=session_id)
    try:
        settings = get_settings()
        approval_enabled = bool(getattr(settings.closed_loop, "tuning_manual_approval_enabled", False))
        high_risk_delta = int(getattr(settings.closed_loop, "tuning_high_risk_delta", 3) or 3)
    except Exception:
        approval_enabled = False
        high_risk_delta = 3
    frozen_params = set(str(x) for x in list(guardrail.get("frozen_params", [])))
    safe_recs: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    # Limit blast radius: at most 8 effective recommendations per apply.
    for rec in list(recommendations)[:8]:
        param = str(rec.get("param", ""))
        if param in frozen_params:
            rejected.append({"rec": rec, "reason": "slo_frozen"})
            continue
        if not param.startswith("closed_loop."):
            rejected.append({"rec": rec, "reason": "unsupported_param"})
            continue
        if "suggested_delta" in rec:
            try:
                delta = int(rec.get("suggested_delta", 0) or 0)
            except Exception:
                rejected.append({"rec": rec, "reason": "invalid_delta"})
                continue
            if abs(delta) > 4:
                rejected.append({"rec": rec, "reason": "delta_too_large"})
                continue
            if approval_enabled and abs(delta) >= max(1, high_risk_delta):
                pending_path = _governance_pending_path()
                pending_path.parent.mkdir(parents=True, exist_ok=True)
                pending_row = {
                    "ts": int(time.time()),
                    "status": "pending_approval",
                    "apply_scope": apply_scope,
                    "domain": domain,
                    "session_id": session_id,
                    "trace_id": trace_id or "",
                    "cycle_id": cycle_id or "",
                    "recommendation": rec,
                }
                with open(pending_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(pending_row, ensure_ascii=False) + "\n")
                rejected.append({"rec": rec, "reason": "pending_approval"})
                continue
        safe_recs.append(rec)
    if not safe_recs:
        audit = record_governance_decision(
            action="guarded_apply_skipped",
            scope=apply_scope,
            operator="autonomous-cycle",
            evidence_refs=["no_safe_recommendations"],
            payload={"rejected_count": len(rejected)},
            slo_state=str(guardrail.get("slo_state", "normal")),
            freeze_reason=str(guardrail.get("freeze_reason", "")),
            policy_id=str(guardrail.get("policy_id", "")),
            policy_scope=str(guardrail.get("policy_scope", "")),
            policy_version=str(guardrail.get("policy_version", "")),
            policy_hash=str(guardrail.get("policy_hash", "")),
            trace_id=trace_id or "",
            cycle_id=cycle_id or "",
        )
        return {
            "success": False,
            "skipped": "no_safe_recommendations",
            "applied": [],
            "rejected": rejected,
            "audit_record_id": audit["decision_id"],
            "slo_state": guardrail.get("slo_state", "normal"),
        }
    path = _config_file_path()
    before = _load_config_json(path)
    applied = apply_tuning_suggestions(
        safe_recs,
        apply_scope=apply_scope,
        domain=domain,
        session_id=session_id,
        dry_run=dry_run,
    )
    applied["rejected"] = rejected
    if dry_run or not bool(applied.get("success")):
        audit = record_governance_decision(
            action="guarded_apply_dry_run" if dry_run else "guarded_apply_failed",
            scope=apply_scope,
            operator="autonomous-cycle",
            evidence_refs=["recommendations_reviewed"],
            payload={"success": bool(applied.get("success")), "applied_count": len(applied.get("applied", []))},
            slo_state=str(guardrail.get("slo_state", "normal")),
            freeze_reason=str(guardrail.get("freeze_reason", "")),
            policy_id=str(guardrail.get("policy_id", "")),
            policy_scope=str(guardrail.get("policy_scope", "")),
            policy_version=str(guardrail.get("policy_version", "")),
            policy_hash=str(guardrail.get("policy_hash", "")),
            trace_id=trace_id or "",
            cycle_id=cycle_id or "",
        )
        applied["audit_record_id"] = audit["decision_id"]
        applied["slo_state"] = guardrail.get("slo_state", "normal")
        return applied
    rb_path = _rollback_state_path()
    rollback_ref = f"rb-{uuid.uuid4().hex[:12]}"
    rb_path.parent.mkdir(parents=True, exist_ok=True)
    rb_path.write_text(
        json.dumps(
            {
                "ts": int(time.time()),
                "reason": "guarded_apply",
                "rollback_ref": rollback_ref,
                "config_before": before,
                "applied_count": len(applied.get("applied", [])),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    audit = record_governance_decision(
        action="guarded_apply",
        scope=apply_scope,
        operator="autonomous-cycle",
        evidence_refs=[f"rejected_count={len(rejected)}", f"applied_count={len(applied.get('applied', []))}"],
        rollback_ref=rollback_ref,
        payload={"domain": domain, "session_id": session_id},
        slo_state=str(guardrail.get("slo_state", "normal")),
        freeze_reason=str(guardrail.get("freeze_reason", "")),
        policy_id=str(guardrail.get("policy_id", "")),
        policy_scope=str(guardrail.get("policy_scope", "")),
        policy_version=str(guardrail.get("policy_version", "")),
        policy_hash=str(guardrail.get("policy_hash", "")),
        trace_id=trace_id or "",
        cycle_id=cycle_id or "",
    )
    applied["rollback_ref"] = rollback_ref
    applied["audit_record_id"] = audit["decision_id"]
    applied["slo_state"] = guardrail.get("slo_state", "normal")
    applied["freeze_reason"] = str(guardrail.get("freeze_reason", ""))
    applied["policy_id"] = str(guardrail.get("policy_id", ""))
    applied["policy_scope"] = str(guardrail.get("policy_scope", ""))
    applied["policy_version"] = str(guardrail.get("policy_version", ""))
    applied["freeze_until_ts"] = int(guardrail.get("freeze_until_ts", 0) or 0)
    emit_ops_event("tuning_guarded_apply", {"applied_count": len(applied.get("applied", [])), "rejected_count": len(rejected)})
    return applied


def export_governance_audit_report(*, limit: int = 500) -> dict[str, Any]:
    """Export read-only governance audit summary for compliance."""
    path = _governance_audit_path()
    rows: list[dict[str, Any]] = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(Exception):
                    rows.append(json.loads(line))
    rows = rows[-max(1, int(limit)) :]
    summary = {
        "total": len(rows),
        "actions": {},
    }
    for r in rows:
        action = str(r.get("action", "unknown") or "unknown")
        summary["actions"][action] = int(summary["actions"].get(action, 0) or 0) + 1
    out_dir = _reports_dir_path()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    out = out_dir / f"governance-audit-{ts}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "path": str(out), "summary": summary}


def summarize_clawteam_deeploop_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate clawteam deep-loop ops rows (``emit_ops_event`` JSONL shape) for dashboards/tests."""
    from collections import Counter

    gap_deltas: list[float] = []
    handoffs: list[float] = []
    decisions: list[str] = []
    for row in events:
        et = str(row.get("event_type", "") or "")
        p = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if et == "clawteam_iteration_completed":
            gap_deltas.append(abs(float(p.get("gap_delta", 0.0) or 0.0)))
            if p.get("handoff_success_rate") is not None:
                handoffs.append(float(p.get("handoff_success_rate", 0.0) or 0.0))
        elif et == "clawteam_deeploop_decision":
            decisions.append(str(p.get("decision", "") or ""))
    n = len(gap_deltas)
    avg_abs_gap = round(sum(gap_deltas) / n, 6) if n else 0.0
    dc = dict(Counter(d for d in decisions if d))
    return {
        "schema_version": "clawteam-deeploop-events-summary-v1",
        "iteration_count": n,
        "avg_abs_gap_delta": avg_abs_gap,
        "handoff_success_series": [round(h, 6) for h in handoffs],
        "decision_counts": dc,
    }
