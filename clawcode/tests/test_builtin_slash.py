"""Tests for built-in slash registry, handlers, and GitHub PR helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from clawcode.config.constants import MCPType
from clawcode.config.settings import MCPServer, Provider, Settings
from clawcode.message.service import Message, MessageRole, TextContent
from clawcode.plugin.types import HookEvent, HookMatcherGroup, LoadedPlugin, PluginManifest
from clawcode.integrations import github_pr
from clawcode.llm.plan_store import PlanStore, PlanTaskItem
from clawcode.learning.team_experience_params import parse_team_experience_create_args
from clawcode.session.service import Session
from clawcode.tui.architect_params import parse_architect_args
from clawcode.tui import builtin_slash_handlers
from clawcode.tui.builtin_slash import (
    BUILTIN_SLASH_COMMANDS,
    BUILTIN_SLASH_NAMES,
    SLASH_AUTOCOMPLETE_EXTRA,
    BuiltinSlashContext,
    BuiltinSlashOutcome,
    filter_commands,
    longest_common_prefix,
    parse_slash_line,
    slash_autocomplete_hidden_union,
    slash_suggest_query,
)
from clawcode.tui.screens.chat import (
    _parse_clawteam_namespace_slash,
    _parse_plugin_namespace_slash,
)
from clawcode.tui.builtin_slash_handlers import handle_builtin_slash


def test_builtin_names_cover_registry() -> None:
    assert "init" in BUILTIN_SLASH_NAMES
    assert "pr-comments" in BUILTIN_SLASH_NAMES
    assert "security-review" in BUILTIN_SLASH_NAMES
    assert "claude" in BUILTIN_SLASH_NAMES
    assert "claude-cli" in BUILTIN_SLASH_NAMES
    assert "opencode-cli" in BUILTIN_SLASH_NAMES
    assert "codex-cli" in BUILTIN_SLASH_NAMES
    assert len(BUILTIN_SLASH_NAMES) == 92
    assert "todos" in BUILTIN_SLASH_NAMES
    assert "vim" in BUILTIN_SLASH_NAMES
    assert "debug" in BUILTIN_SLASH_NAMES
    assert "stats" in BUILTIN_SLASH_NAMES
    assert "theme" in BUILTIN_SLASH_NAMES
    assert "tdd" in BUILTIN_SLASH_NAMES
    assert "architect" in BUILTIN_SLASH_NAMES
    assert "clawteam" in BUILTIN_SLASH_NAMES
    assert "multi-plan" in BUILTIN_SLASH_NAMES
    assert "multi-execute" in BUILTIN_SLASH_NAMES
    assert "multi-backend" in BUILTIN_SLASH_NAMES
    assert "multi-frontend" in BUILTIN_SLASH_NAMES
    assert "learn-orchestrate" in BUILTIN_SLASH_NAMES
    assert "experience-dashboard" in BUILTIN_SLASH_NAMES
    assert "closed-loop-contract" in BUILTIN_SLASH_NAMES
    assert "multi-workflow" in BUILTIN_SLASH_NAMES
    assert "orchestrate" in BUILTIN_SLASH_NAMES
    assert "checkpoint" in BUILTIN_SLASH_NAMES
    assert "code-review" in BUILTIN_SLASH_NAMES
    assert "learn" in BUILTIN_SLASH_NAMES
    assert "instinct-status" in BUILTIN_SLASH_NAMES
    assert "instinct-import" in BUILTIN_SLASH_NAMES
    assert "instinct-export" in BUILTIN_SLASH_NAMES
    assert "evolve" in BUILTIN_SLASH_NAMES
    assert "experience-create" in BUILTIN_SLASH_NAMES
    assert "experience-status" in BUILTIN_SLASH_NAMES
    assert "experience-export" in BUILTIN_SLASH_NAMES
    assert "experience-import" in BUILTIN_SLASH_NAMES
    assert "experience-apply" in BUILTIN_SLASH_NAMES
    assert "experience-feedback" in BUILTIN_SLASH_NAMES
    assert "team-experience-create" in BUILTIN_SLASH_NAMES
    assert "team-experience-status" in BUILTIN_SLASH_NAMES
    assert "team-experience-export" in BUILTIN_SLASH_NAMES
    assert "team-experience-import" in BUILTIN_SLASH_NAMES
    assert "team-experience-apply" in BUILTIN_SLASH_NAMES
    assert "team-experience-feedback" in BUILTIN_SLASH_NAMES
    assert "tecap-create" in BUILTIN_SLASH_NAMES
    assert "tecap-status" in BUILTIN_SLASH_NAMES
    assert "tecap-export" in BUILTIN_SLASH_NAMES
    assert "tecap-import" in BUILTIN_SLASH_NAMES
    assert "tecap-apply" in BUILTIN_SLASH_NAMES
    assert "tecap-feedback" in BUILTIN_SLASH_NAMES
    reg_names = {n for n, _ in BUILTIN_SLASH_COMMANDS}
    assert reg_names == set(BUILTIN_SLASH_NAMES)
    assert "plugin" not in BUILTIN_SLASH_NAMES
    assert "plan" not in BUILTIN_SLASH_NAMES
    extra = dict(SLASH_AUTOCOMPLETE_EXTRA)
    assert "plan mode" in extra.get("plan", "").lower()


def test_parse_slash_line() -> None:
    assert parse_slash_line("/init") == ("init", "")
    assert parse_slash_line("/pr-comments 12") == ("pr-comments", "12")
    assert parse_slash_line("/install-github-app") == ("install-github-app", "")
    assert parse_slash_line("hello") == (None, "hello")


def test_slash_suggest_query() -> None:
    assert slash_suggest_query("/") == ""
    assert slash_suggest_query("/pr") == "pr"
    assert slash_suggest_query("/pr-comments") is None
    assert slash_suggest_query("/plugin") is None
    assert slash_suggest_query("/plan") is None
    assert slash_suggest_query("/pr-comments 1") is None
    assert slash_suggest_query("not slash") is None


def test_filter_commands_with_plugin_skill_extra() -> None:
    rows = filter_commands("api", extra=[("api-design", "Skill (p): REST patterns")])
    names = [n for n, _ in rows]
    assert "api-design" in names


def test_slash_suggest_query_hides_plugin_skill_exact_name() -> None:
    hidden = slash_autocomplete_hidden_union([("api-design", "desc")])
    assert slash_suggest_query("/api-design", autocomplete_hidden=hidden) is None
    assert slash_suggest_query("/api-des", autocomplete_hidden=hidden) == "api-des"


def test_filter_commands() -> None:
    rows = filter_commands("pr")
    names = [n for n, _ in rows]
    assert "pr-comments" in names
    pl_rows = [n for n, _ in filter_commands("pl")]
    assert "plugin" in pl_rows
    plug = dict(SLASH_AUTOCOMPLETE_EXTRA)
    assert plug["plugin"] == "Manage clawcode plugins"
    rev = [n for n, _ in filter_commands("rev")]
    assert "review" in rev
    sec = [n for n, _ in filter_commands("security")]
    assert "security-review" in sec
    pln = [n for n, _ in filter_commands("pla")]
    assert "plan" in pln
    mem = [n for n, _ in filter_commands("mem")]
    assert "memory" in mem
    cod = [n for n, _ in filter_commands("code")]
    assert "code-review" in cod
    ins = [n for n, _ in filter_commands("instinct")]
    assert "instinct-status" in ins


def test_longest_common_prefix() -> None:
    assert longest_common_prefix(["pr-comments", "review"]) == ""
    assert longest_common_prefix(["init", "insights"]) == "in"


def test_parse_remote_url_https() -> None:
    r = github_pr.parse_remote_url("https://github.com/foo/bar.git")
    assert r is not None
    assert r.owner == "foo"
    assert r.repo == "bar"


def test_parse_remote_url_ssh() -> None:
    r = github_pr.parse_remote_url("git@github.com:acme/widget.git")
    assert r is not None
    assert r.owner == "acme"
    assert r.repo == "widget"


def test_parse_pr_ref_url() -> None:
    ref = github_pr.parse_pr_ref("https://github.com/o/r/pull/99/extra")
    assert ref is not None
    assert ref.number == 99
    assert ref.owner == "o"
    assert ref.repo == "r"


def test_parse_pr_number_from_tail() -> None:
    assert github_pr.parse_pr_number_from_tail("42") == 42
    assert github_pr.parse_pr_number_from_tail("") is None


@pytest.mark.asyncio
async def test_pr_comments_no_auth_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "clawcode.integrations.github_pr.github_authorization_header",
        lambda: None,
    )

    settings = Settings()
    out = await handle_builtin_slash(
        "pr-comments",
        "https://github.com/a/b/pull/1",
        settings=settings,
        session_service=None,
    )
    assert isinstance(out, BuiltinSlashOutcome)
    assert out.kind == "assistant_message"
    assert out.assistant_text is not None
    assert "GITHUB_TOKEN" in out.assistant_text or "gh" in out.assistant_text.lower()


def test_format_pr_comments_markdown() -> None:
    data = {
        "pull": {
            "number": 7,
            "title": "Fix bug",
            "state": "open",
            "html_url": "https://github.com/o/r/pull/7",
            "body": "Desc",
        },
        "issue_comments": [{"user": {"login": "alice"}, "body": "LGTM"}],
        "review_comments": [{"user": {"login": "bob"}, "path": "a.py", "body": "nit"}],
        "reviews": [{"user": {"login": "bob"}, "state": "APPROVED", "body": ""}],
    }
    md = github_pr.format_pr_comments_markdown(data)
    assert "PR #7" in md
    assert "Fix bug" in md
    assert "alice" in md
    assert "a.py" in md
    assert "APPROVED" in md


def test_resolve_pr_ref_with_number_and_mock_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        github_pr,
        "resolve_repo_from_git",
        lambda _cwd: github_pr.RepoRef(owner="org", repo="proj"),
    )
    ref = github_pr.resolve_pr_ref("99", str(tmp_path))
    assert ref is not None
    assert ref.number == 99
    assert ref.owner == "org"
    assert ref.repo == "proj"


@pytest.mark.asyncio
async def test_handle_claude_slash_path_a() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "claude",
        "",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(plan_blocks_claw=False),
    )
    assert out.kind == "assistant_message"
    assert out.ui_action == "enable_claw_mode"
    text = out.assistant_text or ""
    assert "path A" in text
    assert "CLAW_SUPPORT_MAP.md" in text
    assert "Anthropic credential resolved:" in text
    assert "Claw agent mode is now ON" in text


@pytest.mark.asyncio
async def test_handle_claude_slash_blocked_when_plan_pending() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "claude",
        "",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(plan_blocks_claw=True),
    )
    assert out.kind == "assistant_message"
    assert out.ui_action is None
    assert "/plan off" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_init_creates_clawcode_md(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("init", "", settings=settings, session_service=None)
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    assert "CLAWCODE.md" in out.agent_user_text
    assert (tmp_path / "CLAWCODE.md").is_file()
    assert "Overview" in (tmp_path / "CLAWCODE.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_handle_init_existing_clawcode_md(tmp_path: Path) -> None:
    claw = tmp_path / "CLAWCODE.md"
    claw.write_text("# existing\n", encoding="utf-8")
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("init", "", settings=settings, session_service=None)
    assert out.kind == "agent_prompt"
    assert "already exists" in (out.agent_user_text or "")


@pytest.mark.asyncio
async def test_handle_insights_no_session_service() -> None:
    settings = Settings()
    out = await handle_builtin_slash("insights", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "not available" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_learning_builtins_mvp(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    s1 = await handle_builtin_slash("learn", "", settings=settings, session_service=None)
    assert s1.kind == "assistant_message"
    assert s1.assistant_text is not None
    s2 = await handle_builtin_slash("instinct-status", "", settings=settings, session_service=None)
    assert s2.kind == "assistant_message"
    assert s2.assistant_text is not None
    s3 = await handle_builtin_slash(
        "instinct-export",
        f"--output {tmp_path / 'x.md'}",
        settings=settings,
        session_service=None,
    )
    assert s3.kind == "assistant_message"
    assert s3.assistant_text is not None
    s4 = await handle_builtin_slash("evolve", "", settings=settings, session_service=None)
    assert s4.kind == "assistant_message"
    assert s4.assistant_text is not None


@pytest.mark.asyncio
async def test_handle_closed_loop_contract_builtin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def closed_loop_contract_report(self):
            return {
                "schema_version": "closed-loop-contract-v1",
                "total_keys": 4,
                "consumed_count": 3,
                "unconsumed_count": 1,
                "consumed_keys": ["a", "b", "c"],
                "unconsumed_keys": ["x"],
                "risk_level": "medium",
                "recommended_action": "review keys",
            }

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)
    out = await handle_builtin_slash("closed-loop-contract", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "Closed Loop Config Contract" in text
    assert "schema_version: closed-loop-contract-v1" in text
    assert "consumed_count: 3" in text
    assert "unconsumed_count: 1" in text


@pytest.mark.asyncio
async def test_handle_experience_dashboard_builtin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def experience_dashboard_query(self, *, include_alerts: bool = True, domain: str | None = None):
            return {
                "schema_version": "experience-dashboard-query-v1",
                "experience_dashboard": {
                    "schema_version": "experience-dashboard-v1",
                    "generated_at": "t0",
                    "metrics": {"ecap_effectiveness_avg": 0.7},
                    "window_metrics": {"7": {"ecap_effectiveness_avg": 0.6}},
                },
                "experience_alerts": {
                    "schema_version": "experience-alerts-v1",
                    "level": "warning",
                    "alerts": [{"metric": "x", "level": "warning", "value": 0.1, "reason": "r"}],
                },
                "experience_health": "warning",
                "experience_policy_advice": {
                    "guard_mode": "restrictive",
                    "suggestions": [{"target": "tuning_auto_apply_enabled", "op": "set", "value": False}],
                },
            }

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)
    out = await handle_builtin_slash("experience-dashboard", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "ECAP-first Experience Dashboard" in text
    assert "ecap_effectiveness_avg" in text
    assert "experience_health: warning" in text
    assert "Adaptive policy advice" in text


@pytest.mark.asyncio
async def test_handle_experience_dashboard_builtin_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def experience_dashboard_query(self, *, include_alerts: bool = True, domain: str | None = None):
            return {
                "schema_version": "experience-dashboard-query-v1",
                "experience_dashboard": {"schema_version": "experience-dashboard-v1"},
                "experience_alerts": {"level": "ok"},
                "experience_health": "ok",
            }

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)
    out = await handle_builtin_slash("experience-dashboard", "--json", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert text.strip().startswith("{")
    assert '"schema_version": "experience-dashboard-query-v1"' in text


@pytest.mark.asyncio
async def test_handle_closed_loop_contract_builtin_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def closed_loop_contract_report(self):
            return {
                "schema_version": "closed-loop-contract-v1",
                "total_keys": 4,
                "consumed_count": 3,
                "unconsumed_count": 1,
                "consumed_keys": ["a", "b", "c"],
                "unconsumed_keys": ["x"],
                "risk_level": "medium",
                "recommended_action": "review keys",
            }

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)
    out = await handle_builtin_slash("closed-loop-contract", "--json", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert text.strip().startswith("{")
    assert '"schema_version": "closed-loop-contract-v1"' in text
    assert '"unconsumed_count": 1' in text


@pytest.mark.asyncio
async def test_handle_learn_orchestrate_builtin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def run_autonomous_cycle(self, **_kwargs):
            return {
                "mode": "apply",
                "schema_version": "autonomous-cycle-v2",
                "observe": "Observer processed 3 new event(s).",
                "evolve": "Evolved 2 clusters.",
                "import_payload": {
                    "rows": [],
                    "summary": {
                        "created": 1,
                        "updated": 2,
                        "skipped_same_content": 0,
                        "conflicts": 0,
                        "read_errors": 0,
                    },
                },
                "predicted_import_candidates": 0,
                "domain": "general",
                "domain_confidence": 0.35,
                "ops_report": {"event_count": 0, "counts": {}},
                "tuning_report": {"recommendations": []},
                "layered_report": {"markdown_report": "", "json_report": {}},
                "long_term_metrics": {"windows": {"7": {"score": 0.8}, "30": {"score": 0.7}}},
                "canary_evaluation": {"decision": "promote"},
                "applied_tuning": None,
                "exported_report": None,
            }

        def closed_loop_contract_report(self):
            return {"consumed_count": 8, "unconsumed_count": 0}

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)

    out = await handle_builtin_slash(
        "learn-orchestrate",
        "",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "Learning Orchestration" in text
    assert "schema_version: autonomous-cycle-v2" in text
    assert "created: 1" in text
    assert "updated: 2" in text


@pytest.mark.asyncio
async def test_handle_learn_orchestrate_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def run_autonomous_cycle(self, **_kwargs):
            return {
                "mode": "dry-run (no file write)",
                "schema_version": "autonomous-cycle-v2",
                "observe": "Observer processed 1 new event(s).",
                "evolve": "Evolved 1 cluster.",
                "import_payload": {"summary": {"created": 9}},
                "predicted_import_candidates": 1,
                "domain": "general",
                "domain_confidence": 0.35,
                "ops_report": {"event_count": 1, "counts": {}},
                "tuning_report": {"recommendations": []},
                "layered_report": {"markdown_report": "", "json_report": {}},
                "long_term_metrics": {"windows": {"7": {"score": 0.8}, "30": {"score": 0.7}}},
                "canary_evaluation": {"decision": "hold"},
                "applied_tuning": None,
                "exported_report": None,
            }

        def closed_loop_contract_report(self):
            return {"consumed_count": 8, "unconsumed_count": 0}

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)

    out = await handle_builtin_slash(
        "learn-orchestrate",
        "--dry-run --report",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "dry-run" in text
    assert "executed_import: no" in text


@pytest.mark.asyncio
async def test_handle_learn_orchestrate_report_only_and_tuning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.closed_loop.tuning_auto_apply_enabled = True

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def run_autonomous_cycle(self, **_kwargs):
            return {
                "mode": "dry-run (no file write)",
                "schema_version": "autonomous-cycle-v2",
                "observe": "skipped (report-only)",
                "evolve": "skipped (report-only)",
                "import_payload": {"summary": {"created": 0, "updated": 0, "skipped_same_content": 0, "conflicts": 0, "read_errors": 0}},
                "predicted_import_candidates": 0,
                "domain": "backend",
                "domain_confidence": 1.0,
                "ops_report": {"event_count": 3, "counts": {"x": 1}},
                "tuning_report": {
                    "recommendations": [{"param": "closed_loop.flush_max_writes", "suggested_delta": 1, "layer": "global"}]
                },
                "layered_report": {"markdown_report": "## Layered Tuning Comparison\n", "json_report": {}},
                "long_term_metrics": {"windows": {"7": {"score": 0.8}, "30": {"score": 0.7}}},
                "canary_evaluation": {"decision": "promote"},
                "applied_tuning": {"applied": [{"param": "closed_loop.flush_max_writes"}]},
                "exported_report": {"success": True, "md_path": str(tmp_path / "r.md"), "json_path": str(tmp_path / "r.json")},
            }

        def closed_loop_contract_report(self):
            return {"consumed_count": 8, "unconsumed_count": 1}

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)

    out = await handle_builtin_slash(
        "learn-orchestrate",
        "--report-only --apply-tuning --export-report --window 12 --domain backend",
        settings=settings,
        session_service=None,
    )
    text = out.assistant_text or ""
    assert "window_hours: 12" in text
    assert "domain: backend" in text
    assert "stage_status:" in text
    assert "executed_import: no" in text
    assert "contract_unconsumed_keys: 1" in text
    assert "tuning_applied:" in text
    assert "exported_report_md:" in text
    assert "exported_report_json:" in text


@pytest.mark.asyncio
async def test_handle_learn_orchestrate_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)

    class _FakeSvc:
        def __init__(self, _settings: Settings) -> None:
            self.settings = _settings

        def run_autonomous_cycle(self, **_kwargs):
            return {
                "schema_version": "autonomous-cycle-v2",
                "mode": "dry-run (no file write)",
                "errors": [{"stage": "report", "error": "x"}],
                "governance_summary": {"policy_id": "slo-default-v2"},
            }

        def closed_loop_contract_report(self):
            return {"consumed_count": 8, "unconsumed_count": 1}

    monkeypatch.setattr(builtin_slash_handlers, "LearningService", _FakeSvc)
    out = await handle_builtin_slash(
        "learn-orchestrate",
        "--json --dry-run",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    payload = json.loads(out.assistant_text or "{}")
    assert payload["schema_version"] == "autonomous-cycle-v2"
    assert payload["contract_report"]["consumed_count"] == 8
    assert payload["error_taxonomy"]["report"] == 1


@pytest.mark.asyncio
async def test_handle_learning_builtins_advanced_args(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    src = tmp_path / "incoming.md"
    src.write_text(
        "---\n"
        "id: t1\ntrigger: \"when testing\"\nconfidence: 0.8\ndomain: testing\nsource: inherited\n---\n\n## Action\nA\n",
        encoding="utf-8",
    )
    i1 = await handle_builtin_slash(
        "instinct-import",
        f"{src} --merge-strategy higher --from-skill-creator acme/repo --force",
        settings=settings,
        session_service=None,
    )
    assert i1.kind == "assistant_message"
    st = await handle_builtin_slash(
        "instinct-status",
        "--json --high-confidence",
        settings=settings,
        session_service=None,
    )
    assert st.kind == "assistant_message"
    assert (st.assistant_text or "").strip().startswith("{")
    ex = await handle_builtin_slash(
        "instinct-export",
        f"--format json --output {tmp_path / 'x.json'}",
        settings=settings,
        session_service=None,
    )
    assert ex.kind == "assistant_message"
    ev = await handle_builtin_slash(
        "evolve",
        "--threshold 2 --type skill --dry-run",
        settings=settings,
        session_service=None,
    )
    assert ev.kind == "assistant_message"


@pytest.mark.asyncio
async def test_handle_experience_builtins(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    c = await handle_builtin_slash(
        "experience-create",
        "--problem-type debug --dry-run",
        settings=settings,
        session_service=None,
    )
    assert c.kind == "assistant_message"
    s = await handle_builtin_slash(
        "experience-status",
        "--json",
        settings=settings,
        session_service=None,
    )
    assert s.kind == "assistant_message"
    assert (s.assistant_text or "").strip().startswith("{")
    f = await handle_builtin_slash(
        "experience-feedback",
        "missing --result success --score 0.5",
        settings=settings,
        session_service=None,
    )
    assert f.kind == "assistant_message"


class _FakeSessionService:
    def __init__(self, rows: list[Session]) -> None:
        self._rows = rows

    async def list(
        self,
        limit: int = 50,
        _offset: int = 0,
        _parent_session_id: str | None = None,
    ):
        return list(self._rows[:limit])

    async def create(self, title: str, parent_session_id: str | None = None) -> Session:
        return Session(
            id="sess_forked_test",
            title=title,
            parent_session_id=parent_session_id,
        )

    async def get(self, session_id: str) -> Session | None:
        for r in self._rows:
            if r.id == session_id:
                return r
        return None


class _ForkExportMessageService:
    def __init__(self, rows: list[Message]) -> None:
        self._rows = rows
        self.created: list[tuple[str, MessageRole, str, list | None, str | None]] = []

    async def list_by_session(self, session_id: str, limit: int = 100) -> list[Message]:
        return list(self._rows[:limit])

    async def create(
        self,
        session_id: str,
        role: MessageRole,
        content: str = "",
        parts: list | None = None,
        model: str | None = None,
    ) -> Message:
        self.created.append((session_id, role, content, parts, model))
        return Message(id="m_new", session_id=session_id, role=role, parts=parts or [])

    async def reconcile_session_row_from_active_messages(
        self, session_id: str, session_service: object
    ) -> None:
        return None

    async def soft_delete_messages_after(
        self,
        session_id: str,
        anchor_message_id: str,
        *,
        inclusive: bool = False,
    ) -> int:
        return len(self._rows)

    async def soft_delete_messages_except_ids(
        self, session_id: str, keep_ids: frozenset[str]
    ) -> int:
        return len([m for m in self._rows if m.id not in keep_ids])


@pytest.mark.asyncio
async def test_handle_insights_renders_table(tmp_path: Path) -> None:
    now = int(time.time())
    sess = Session(
        id="s1",
        title="Hello session",
        message_count=3,
        prompt_tokens=100,
        completion_tokens=50,
        cost=0.01,
        created_at=now,
        updated_at=now,
    )
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "insights",
        "",
        settings=settings,
        session_service=_FakeSessionService([sess]),
    )
    assert out.kind == "assistant_message"
    assert "clawcode session insights" in (out.assistant_text or "").lower()
    assert "Hello session" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_pr_comments_usage_empty_tail(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("pr-comments", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "Usage" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_review_usage_empty_tail(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("review", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "Usage" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_pr_comments_success_mock_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_fetch(_pr: github_pr.PrRef) -> dict:
        return {
            "pull": {
                "number": 3,
                "title": "Feature",
                "state": "open",
                "html_url": "https://github.com/o/r/pull/3",
            },
            "issue_comments": [{"user": {"login": "u1"}, "body": "ok"}],
            "review_comments": [],
            "reviews": [],
        }

    monkeypatch.setattr(builtin_slash_handlers, "fetch_pr_comments", _fake_fetch)
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "pr-comments",
        "https://github.com/o/r/pull/3",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    assert "Feature" in (out.assistant_text or "")
    assert "u1" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_review_success_mock_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_ctx(_pr: github_pr.PrRef) -> dict:
        return {
            "pull": {"title": "My PR", "html_url": "https://x"},
            "files_meta": [{"filename": "src/x.py", "status": "modified"}],
            "patch_excerpt": "```\n+line\n```",
        }

    monkeypatch.setattr(builtin_slash_handlers, "fetch_pr_review_context", _fake_ctx)
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "review",
        "https://github.com/a/b/pull/2",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    assert "My PR" in out.agent_user_text
    assert "pull request review" in out.agent_user_text.lower()
    assert "src/x.py" in out.agent_user_text


@pytest.mark.asyncio
async def test_handle_security_review_includes_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtin_slash_handlers, "run_git_diff", lambda _cwd: "+added line\n")
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "security-review",
        "",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    assert "added line" in out.agent_user_text
    assert "security review" in out.agent_user_text.lower()


@pytest.mark.asyncio
async def test_handle_tdd_builds_strict_agent_prompt() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "tdd",
        "implement email validator",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    prompt = out.agent_user_text
    assert "SCAFFOLD -> RED -> GREEN -> REFACTOR -> COVERAGE GATE" in prompt
    assert "Test-first always" in prompt
    assert "RED before GREEN" in prompt
    assert ">= 80%" in prompt
    assert "implement email validator" in prompt


@pytest.mark.asyncio
async def test_handle_multi_plan_builds_agent_prompt() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "multi-plan",
        "design tenant-aware throttling",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    prompt = out.agent_user_text
    assert "multi-model collaborative planning" in prompt
    assert "PLAN-ONLY" in prompt
    assert "Research phase" in prompt
    assert "Analysis phase" in prompt
    assert "Cross-validation phase" in prompt
    assert "## Implementation Steps" in prompt
    assert "## Risks and Mitigation" in prompt
    assert "approve or request plan adjustments" in prompt


@pytest.mark.asyncio
async def test_handle_multi_plan_explain_routing_uses_config_pool(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    out = await handle_builtin_slash(
        "multi-plan",
        "plan api redesign --explain-routing",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    text = out.agent_user_text
    assert "Routing decision (config-driven)" in text
    assert "deepseek-chat" in text or "glm-5" in text
    assert isinstance(out.routing_meta, dict)
    assert out.routing_meta.get("discovered_pool")


@pytest.mark.asyncio
async def test_handle_multi_plan_usage_when_empty() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "multi-plan",
        "",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    assert "Usage" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_multi_plan_show_with_current_session_artifact(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id="sess_mp_show",
        user_request="build feature",
        plan_text="# Implementation Plan: X\n\n- step",
        tasks=[PlanTaskItem(id="task-1", title="step")],
        subdir="multi-plan",
        base_name="feature-x",
    )
    out = await handle_builtin_slash(
        "multi-plan",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sess_mp_show"),
    )
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "latest multi-plan" in text
    assert bundle.markdown_path in text
    assert "Implementation Plan" in text


@pytest.mark.asyncio
async def test_handle_multi_plan_show_without_artifact(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "multi-plan",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sess_empty"),
    )
    assert out.kind == "assistant_message"
    assert "No `/multi-plan` artifact found" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_multi_plan_list_outputs_versions(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    store = PlanStore(str(tmp_path))
    _ = store.save_bundle_versioned(
        session_id="sess_a",
        user_request="r1",
        plan_text="# Plan A",
        tasks=[PlanTaskItem(id="task-1", title="a")],
        subdir="multi-plan",
        base_name="alpha",
    )
    _ = store.save_bundle_versioned(
        session_id="sess_b",
        user_request="r2",
        plan_text="# Plan B",
        tasks=[PlanTaskItem(id="task-1", title="b")],
        subdir="multi-plan",
        base_name="beta",
    )
    out = await handle_builtin_slash(
        "multi-plan",
        "list",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "multi-plan artifacts" in text
    assert "alpha" in text or "beta" in text
    assert "| Created | Session | Strategy | Models | Markdown | JSON |" in text


@pytest.mark.asyncio
async def test_handle_multi_execute_builds_agent_prompt_from_text(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    out = await handle_builtin_slash(
        "multi-execute",
        "implement payment retry --strategy balanced --explain-routing",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    text = out.agent_user_text
    assert "multi-model collaborative execution" in text
    assert "Routing decision (config-driven)" in text
    assert isinstance(out.routing_meta, dict)
    assert out.routing_meta.get("execution_meta")


@pytest.mark.asyncio
async def test_handle_multi_execute_show_and_list(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id="sess_me_show",
        user_request="ship feature",
        plan_text="# Multi-Execute Result: A\n\n- done",
        tasks=[PlanTaskItem(id="task-1", title="do")],
        subdir="multi-execute",
        base_name="feature-a",
    )
    bundle.routing_meta = {
        "strategy": "balanced",
        "selected_by_stage": {
            "backend_analysis": {"model_id": "deepseek-chat", "provider_key": "openai_deepseek"}
        },
        "execution_meta": {"audit": "on", "input_mode": "direct-text"},
    }
    store.save_plan_bundle(bundle)

    out_show = await handle_builtin_slash(
        "multi-execute",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sess_me_show"),
    )
    assert out_show.kind == "assistant_message"
    show_text = out_show.assistant_text or ""
    assert "latest multi-execute" in show_text
    assert "Routing summary" in show_text
    assert "deepseek-chat" in show_text

    out_list = await handle_builtin_slash(
        "multi-execute",
        "list",
        settings=settings,
        session_service=None,
    )
    assert out_list.kind == "assistant_message"
    list_text = out_list.assistant_text or ""
    assert "multi-execute artifacts" in list_text
    assert "| Created | Session | Strategy | Models | Audit | Markdown | JSON |" in list_text


@pytest.mark.asyncio
async def test_handle_multi_backend_builds_agent_prompt_from_text(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "openai_deepseek": Provider(disabled=False, models=["deepseek-chat"]),
        "openai_glm": Provider(disabled=False, models=["glm-5"]),
    }
    out = await handle_builtin_slash(
        "multi-backend",
        "idempotent payment retry --strategy balanced --explain-routing",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    text = out.agent_user_text
    assert "Backend Orchestrator" in text
    assert "Phase 4 Execute" in text
    assert "Subagents are **read-only advisors**" in text
    assert isinstance(out.routing_meta, dict)
    assert out.routing_meta.get("workflow") == "backend"
    assert out.routing_meta.get("backend_meta", {}).get("audit") == "on"
    assert "Routing decision (config-driven, backend workflow)" in text


@pytest.mark.asyncio
async def test_handle_multi_backend_show_and_list(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id="sess_mb_show",
        user_request="retry api",
        plan_text="# Multi-Backend Result: B\n\n- ok",
        tasks=[PlanTaskItem(id="task-mb-1", title="x")],
        subdir="multi-backend",
        base_name="retry-b",
    )
    bundle.routing_meta = {
        "workflow": "backend",
        "strategy": "balanced",
        "selected_by_stage": {
            "backend_authority": {"model_id": "deepseek-chat", "provider_key": "openai_deepseek"}
        },
        "backend_meta": {"audit": "on"},
    }
    store.save_plan_bundle(bundle)

    out_show = await handle_builtin_slash(
        "multi-backend",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sess_mb_show"),
    )
    assert out_show.kind == "assistant_message"
    show_text = out_show.assistant_text or ""
    assert "latest multi-backend" in show_text
    assert "Routing summary" in show_text
    assert "deepseek-chat" in show_text

    out_list = await handle_builtin_slash(
        "multi-backend",
        "list",
        settings=settings,
        session_service=None,
    )
    assert out_list.kind == "assistant_message"
    list_text = out_list.assistant_text or ""
    assert "multi-backend artifacts" in list_text
    assert "| Workflow |" in list_text
    assert "| Audit |" in list_text


@pytest.mark.asyncio
async def test_handle_multi_frontend_builds_agent_prompt_from_text(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "gemini_google": Provider(disabled=False, models=["gemini-2.0-flash"]),
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
    }
    out = await handle_builtin_slash(
        "multi-frontend",
        "dashboard layout --strategy balanced --explain-routing",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    text = out.agent_user_text
    assert "Frontend Orchestrator" in text
    assert "Phase 4 Execute" in text
    assert "Subagents are **read-only advisors**" in text
    assert isinstance(out.routing_meta, dict)
    assert out.routing_meta.get("workflow") == "frontend"
    assert out.routing_meta.get("frontend_meta", {}).get("audit") == "on"
    assert "Routing decision (config-driven, frontend workflow)" in text


@pytest.mark.asyncio
async def test_handle_multi_frontend_show_and_list(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id="sess_mf_show",
        user_request="nav bar",
        plan_text="# Multi-Frontend Result: B\n\n- ok",
        tasks=[PlanTaskItem(id="task-mf-1", title="x")],
        subdir="multi-frontend",
        base_name="nav-b",
    )
    bundle.routing_meta = {
        "workflow": "frontend",
        "strategy": "balanced",
        "selected_by_stage": {
            "frontend_authority": {"model_id": "gemini-2.0-flash", "provider_key": "gemini_google"}
        },
        "frontend_meta": {"audit": "on"},
    }
    store.save_plan_bundle(bundle)

    out_show = await handle_builtin_slash(
        "multi-frontend",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sess_mf_show"),
    )
    assert out_show.kind == "assistant_message"
    show_text = out_show.assistant_text or ""
    assert "latest multi-frontend" in show_text
    assert "Routing summary" in show_text
    assert "gemini-2.0-flash" in show_text

    out_list = await handle_builtin_slash(
        "multi-frontend",
        "list",
        settings=settings,
        session_service=None,
    )
    assert out_list.kind == "assistant_message"
    list_text = out_list.assistant_text or ""
    assert "multi-frontend artifacts" in list_text
    assert "| Workflow |" in list_text
    assert "| Audit |" in list_text


@pytest.mark.asyncio
async def test_handle_multi_workflow_builds_agent_prompt_from_text(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.providers = {
        "anthropic_proxy": Provider(disabled=False, models=["claude-opus-4"]),
        "gemini_google": Provider(disabled=False, models=["gemini-2.0-flash"]),
    }
    out = await handle_builtin_slash(
        "multi-workflow",
        "checkout API and UI --strategy balanced --explain-routing",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    text = out.agent_user_text
    assert "Orchestrator" in text
    assert "Phase 1 Research" in text
    assert "Goal clarity" in text
    assert "do not enter ideation" in text.lower()
    assert "backend_analysis" in text
    assert "frontend_analysis" in text
    assert isinstance(out.routing_meta, dict)
    assert out.routing_meta.get("workflow") == "fullstack"
    assert out.routing_meta.get("fullstack_meta", {}).get("audit") == "on"
    assert "Routing decision (config-driven, full-stack workflow)" in text


@pytest.mark.asyncio
async def test_handle_multi_workflow_show_and_list(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id="sess_mw_show",
        user_request="feature x",
        plan_text="# Multi-Workflow Result: B\n\n- ok",
        tasks=[PlanTaskItem(id="task-mw-1", title="x")],
        subdir="multi-workflow",
        base_name="feat-b",
    )
    bundle.routing_meta = {
        "workflow": "fullstack",
        "strategy": "balanced",
        "selected_by_stage": {
            "backend_analysis": {"model_id": "claude-opus-4", "provider_key": "anthropic_proxy"}
        },
        "fullstack_meta": {"audit": "on"},
    }
    store.save_plan_bundle(bundle)

    out_show = await handle_builtin_slash(
        "multi-workflow",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sess_mw_show"),
    )
    assert out_show.kind == "assistant_message"
    show_text = out_show.assistant_text or ""
    assert "latest multi-workflow" in show_text
    assert "Routing summary" in show_text
    assert "claude-opus-4" in show_text

    out_list = await handle_builtin_slash(
        "multi-workflow",
        "list",
        settings=settings,
        session_service=None,
    )
    assert out_list.kind == "assistant_message"
    list_text = out_list.assistant_text or ""
    assert "multi-workflow artifacts" in list_text
    assert "| Workflow |" in list_text
    assert "| Audit |" in list_text


@pytest.mark.asyncio
async def test_handle_orchestrate_builds_agent_prompt_feature_and_custom(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "orchestrate",
        'feature "Add user authentication"',
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    text = out.agent_user_text
    assert "HANDOFF" in text
    assert "ORCHESTRATION REPORT" in text
    assert isinstance(out.routing_meta, dict)
    assert out.routing_meta.get("workflow") == "orchestrate"
    assert out.routing_meta.get("orchestrate_type") == "feature"
    assert out.routing_meta.get("orchestrate_chain") == [
        "planner",
        "tdd-guide",
        "code-reviewer",
        "security-reviewer",
    ]

    out_c = await handle_builtin_slash(
        "orchestrate",
        'custom architect,code-reviewer "Tighten module boundaries"',
        settings=settings,
        session_service=None,
    )
    assert out_c.kind == "agent_prompt"
    assert out_c.routing_meta.get("orchestrate_chain") == ["architect", "code-reviewer"]
    assert "Tighten module boundaries" in (out_c.agent_user_text or "")


@pytest.mark.asyncio
async def test_handle_orchestrate_show_and_list(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle_versioned(
        session_id="sess_orch_show",
        user_request="feature x",
        plan_text="# Orchestrate Result\n\n- ok",
        tasks=[PlanTaskItem(id="task-orch-1", title="x")],
        subdir="orchestrate",
        base_name="orch-a",
    )
    bundle.routing_meta = {
        "workflow": "orchestrate",
        "orchestrate_type": "feature",
        "orchestrate_chain": ["planner", "tdd-guide"],
    }
    store.save_plan_bundle(bundle)

    out_show = await handle_builtin_slash(
        "orchestrate",
        "show",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sess_orch_show"),
    )
    assert out_show.kind == "assistant_message"
    show_text = out_show.assistant_text or ""
    assert "latest orchestrate" in show_text
    assert "Orchestrate Result" in show_text

    out_list = await handle_builtin_slash(
        "orchestrate",
        "list",
        settings=settings,
        session_service=None,
    )
    assert out_list.kind == "assistant_message"
    list_text = out_list.assistant_text or ""
    assert "orchestrate artifacts" in list_text
    assert "| Type |" in list_text
    assert "| Chain |" in list_text


@pytest.mark.asyncio
async def test_handle_multi_execute_from_plan_missing_file() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "multi-execute",
        "--from-plan ./not_exists.plan.md",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    assert "file not found" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_architect_builds_structured_agent_prompt() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "architect",
        "redesign cache strategy --mode refactor --adr --checklist --json --scope core/cache --constraints latency<50ms",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    prompt = out.agent_user_text
    assert "Current State Analysis" in prompt
    assert "Requirements Gathering" in prompt
    assert "Design Proposal" in prompt
    assert "Pros" in prompt and "Cons" in prompt and "Alternatives" in prompt
    assert "ADR section required" in prompt
    assert "System design checklist required" in prompt
    assert "Output JSON with keys" in prompt
    assert "core/cache" in prompt
    assert "latency<50ms" in prompt


def test_parse_architect_args_valid_and_invalid() -> None:
    args, err = parse_architect_args(
        "design payment service --mode design --scope payments --constraints p99<120ms --adr --checklist --json"
    )
    assert err == ""
    assert args is not None
    assert args.request == "design payment service"
    assert args.mode == "design"
    assert args.scope == "payments"
    assert args.constraints == "p99<120ms"
    assert args.include_adr is True
    assert args.include_checklist is True
    assert args.as_json is True

    bad_args, bad_err = parse_architect_args("--mode unknown do something")
    assert bad_args is None
    assert "--mode" in bad_err

    empty_args, empty_err = parse_architect_args("--adr")
    assert empty_args is None
    assert "Usage:" in empty_err


def test_parse_team_experience_create_args_valid() -> None:
    args, err = parse_team_experience_create_args(
        "improve multi-agent triage --problem-type incident --team clawteam --participants a,b,c "
        "--workflow incident-response --constraints p99<150ms --dry-run"
    )
    assert err == ""
    assert args is not None
    assert args.objective == "improve multi-agent triage"
    assert args.problem_type == "incident"
    assert args.team == "clawteam"
    assert args.participants == "a,b,c"
    assert args.workflow == "incident-response"
    assert args.constraints == "p99<150ms"
    assert args.dry_run is True


@pytest.mark.asyncio
async def test_handle_code_review_builds_gate_prompt() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "code-review",
        "focus on api and auth files",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    prompt = out.agent_user_text
    assert "git diff --name-only HEAD" in prompt
    assert "CRITICAL" in prompt and "HIGH" in prompt
    assert "block_commit=true" in prompt
    assert "focus on api and auth files" in prompt


@pytest.mark.asyncio
async def test_handle_team_experience_apply_and_alias(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    c = await handle_builtin_slash(
        "team-experience-create",
        "capture team debugging playbook --team clawteam --participants p1,p2 --workflow debug-chain",
        settings=settings,
        session_service=None,
    )
    assert c.kind == "assistant_message"
    text = c.assistant_text or ""
    assert "Created TECAP" in text
    parts = text.split("`")
    tecap_id = parts[1] if len(parts) > 1 else ""
    assert tecap_id.startswith("tecap-")

    a = await handle_builtin_slash(
        "tecap-apply",
        f"{tecap_id} --mode concise --strategy conservative --explain",
        settings=settings,
        session_service=None,
    )
    assert a.kind == "agent_prompt"
    assert a.agent_user_text is not None
    assert "TECAP" in a.agent_user_text
    assert "Strategy: conservative" in a.agent_user_text


def test_parse_plugin_namespace_slash() -> None:
    assert _parse_plugin_namespace_slash("/plugin:tdd add retries") == ("tdd", "add retries")
    assert _parse_plugin_namespace_slash("/plugin:tdd") == ("tdd", "")
    assert _parse_plugin_namespace_slash("/plugin:") is None
    assert _parse_plugin_namespace_slash("/plugin:bad:name test") is None
    assert _parse_plugin_namespace_slash("/tdd hello") is None


def test_parse_clawteam_namespace_slash() -> None:
    assert _parse_clawteam_namespace_slash("/clawteam:qa verify login") == (
        "qa",
        "verify login",
    )
    assert _parse_clawteam_namespace_slash("/clawteam:clawteam-sre") == (
        "clawteam-sre",
        "",
    )
    assert _parse_clawteam_namespace_slash("/clawteam:") is None
    assert _parse_clawteam_namespace_slash("/clawteam:bad:name req") is None
    assert _parse_clawteam_namespace_slash("/architect:x req") is None


@pytest.mark.asyncio
async def test_handle_clawteam_builds_orchestration_prompt() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "clawteam",
        "design and deliver an order management module",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    prompt = out.agent_user_text
    assert "AUTO-ORCHESTRATION" in prompt
    assert "Agent`/`Task" in prompt
    assert "clawteam-system-architect" in prompt
    assert "TECAP context (retrieved)" in prompt
    assert "Role ECAP context (retrieved)" in prompt


@pytest.mark.asyncio
async def test_handle_clawteam_single_role_alias_agent() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "clawteam",
        "--agent qa validate checkout edge cases",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    assert "SINGLE-ROLE" in out.agent_user_text
    assert "clawteam-qa" in out.agent_user_text


@pytest.mark.asyncio
async def test_handle_clawteam_unknown_agent_returns_error() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "clawteam",
        "--agent unknown-role do something",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    assert out.assistant_text is not None
    assert "Unknown `/clawteam` agent" in out.assistant_text


@pytest.mark.asyncio
async def test_handle_clawteam_deep_loop_builds_iterative_prompt() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "clawteam",
        "--deep_loop improve checkout stability and product readiness",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    prompt = out.agent_user_text
    assert "Deep loop mode: ENABLED" in prompt
    assert "检查" in prompt
    assert "深化设计" in prompt
    assert "扩展实现" in prompt
    assert "最终收敛" in prompt
    assert "delta_score" in prompt
    assert "converged" in prompt
    assert "Iteration cap:" in prompt
    assert "iteration_goal" in prompt
    assert "role_handoff_result" in prompt
    assert "gap_delta" in prompt
    assert "DEEP_LOOP_EVAL_JSON:" in prompt


@pytest.mark.asyncio
async def test_handle_clawteam_deep_loop_supports_max_iters() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "clawteam",
        "--deep_loop --max_iters 7 harden payment failover",
        settings=settings,
        session_service=None,
    )
    assert out.kind == "agent_prompt"
    assert out.agent_user_text
    assert "Deep loop mode: ENABLED" in out.agent_user_text
    assert "Iteration cap: 7" in out.agent_user_text


@pytest.mark.asyncio
async def test_handle_statusline_assistant_message() -> None:
    settings = Settings()
    out = await handle_builtin_slash("statusline", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "HUD" in (out.assistant_text or "")
    assert "clawcode" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_unknown_builtin_head() -> None:
    settings = Settings()
    out = await handle_builtin_slash("notregistered", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "Unknown" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_todos_empty_context() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "todos",
        "",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(todos=[]),
    )
    assert out.kind == "assistant_message"
    assert "No todo" in (out.assistant_text or "") or "HUD" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_todos_with_items() -> None:
    settings = Settings()
    ctx = BuiltinSlashContext(todos=[("Do thing", "pending"), ("Done", "completed")])
    out = await handle_builtin_slash(
        "todos", "", settings=settings, session_service=None, context=ctx
    )
    assert out.kind == "assistant_message"
    assert "Do thing" in (out.assistant_text or "")
    assert "pending" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_upgrade_stub() -> None:
    settings = Settings()
    out = await handle_builtin_slash("upgrade", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "clawcode" in (out.assistant_text or "").lower()
    assert "provider" in (out.assistant_text or "").lower() or "API" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_usage_reports_context() -> None:
    settings = Settings()
    ctx = BuiltinSlashContext(
        context_percent=12,
        context_window_size=128_000,
        session_prompt_tokens=1000,
        session_completion_tokens=500,
        turn_input_tokens=10,
        turn_output_tokens=20,
        model_label="test-model",
    )
    out = await handle_builtin_slash(
        "usage", "", settings=settings, session_service=None, context=ctx
    )
    assert out.kind == "assistant_message"
    assert "12" in (out.assistant_text or "")
    assert "test-model" in (out.assistant_text or "")
    assert "128,000" in (out.assistant_text or "") or "128000" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_vim_requests_ui_toggle() -> None:
    settings = Settings()
    out = await handle_builtin_slash("vim", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert out.ui_action == "toggle_vim"


@pytest.mark.asyncio
async def test_handle_debug_message() -> None:
    settings = Settings()
    out = await handle_builtin_slash("debug", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "clawcode" in (out.assistant_text or "").lower()
    assert "Ctrl+L" in (out.assistant_text or "") or "ctrl+l" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_stats_combines_usage_and_sessions(tmp_path: Path) -> None:
    now = int(time.time())
    sess = Session(
        id="s1",
        title="Act",
        message_count=2,
        prompt_tokens=10,
        completion_tokens=5,
        cost=0.0,
        created_at=now,
        updated_at=now,
    )
    settings = Settings()
    settings.working_directory = str(tmp_path)
    ctx = BuiltinSlashContext(model_label="m", context_percent=5, context_window_size=100_000)
    out = await handle_builtin_slash(
        "stats",
        "",
        settings=settings,
        session_service=_FakeSessionService([sess]),
        context=ctx,
    )
    assert out.kind == "assistant_message"
    assert "clawcode stats" in (out.assistant_text or "").lower()
    assert "Act" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_status_markdown() -> None:
    settings = Settings()
    ctx = BuiltinSlashContext(
        app_version="0.1.0",
        working_dir_display="/tmp/p",
        session_id="abc123456789",
        session_title="Hi",
        model_label="m",
        provider_label="openai",
        lsp_on=True,
        mouse_on=False,
        display_mode="opencode",
        is_agent_processing=False,
    )
    out = await handle_builtin_slash(
        "status", "", settings=settings, session_service=None, context=ctx
    )
    assert out.kind == "assistant_message"
    assert "0.1.0" in (out.assistant_text or "")
    assert "openai" in (out.assistant_text or "")
    assert "clawcode status" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_stickers_stub() -> None:
    settings = Settings()
    out = await handle_builtin_slash("stickers", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "sticker" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_tasks_idle_no_plan() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "tasks",
        "",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(is_agent_processing=False, plan_background_tasks=[]),
    )
    assert out.kind == "assistant_message"
    assert "idle" in (out.assistant_text or "").lower() or "Agent" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_tasks_with_plan_lines() -> None:
    settings = Settings()
    ctx = BuiltinSlashContext(
        plan_background_tasks=["**pending** Fix bug"],
        is_agent_processing=True,
    )
    out = await handle_builtin_slash(
        "tasks", "", settings=settings, session_service=None, context=ctx
    )
    assert out.kind == "assistant_message"
    assert "Fix bug" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_terminal_setup_backslash_enter() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "terminal-setup", "", settings=settings, session_service=None
    )
    assert out.kind == "assistant_message"
    assert "Enter" in (out.assistant_text or "")
    assert "Shift" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_mcp_lists_configured_servers() -> None:
    settings = Settings()
    settings.mcp_servers = {
        "demo": MCPServer(command="npx", args=["-y", "@demo/mcp"], type=MCPType.STDIO),
        "remote": MCPServer(type=MCPType.SSE, url="https://example.invalid/mcp"),
    }
    out = await handle_builtin_slash("mcp", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "demo" in text and "npx" in text
    assert "remote" in text and "example.invalid" in text
    assert "headers" in text.lower() or "secrets" in text.lower()


@pytest.mark.asyncio
async def test_handle_model_opens_dialog_action() -> None:
    settings = Settings()
    out = await handle_builtin_slash("model", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert out.ui_action == "open_model_dialog"


@pytest.mark.asyncio
async def test_handle_output_style_valid_mode_sets_apply() -> None:
    settings = Settings()
    out = await handle_builtin_slash("output-style", "zen", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert out.apply_display_mode == "zen"
    assert "zen" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_output_style_empty_opens_picker() -> None:
    settings = Settings()
    out = await handle_builtin_slash("output-style", "", settings=settings, session_service=None)
    assert out.ui_action == "open_display_mode"


@pytest.mark.asyncio
async def test_handle_permissions_clear_no_session() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "permissions",
        "clear",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id=""),
    )
    assert out.kind == "assistant_message"
    assert "no active session" in (out.assistant_text or "").lower()
    assert not out.clear_session_tool_permissions


@pytest.mark.asyncio
async def test_handle_permissions_clear_with_session() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "permissions",
        "clear",
        settings=settings,
        session_service=None,
        context=BuiltinSlashContext(session_id="sid-1"),
    )
    assert out.clear_session_tool_permissions


@pytest.mark.asyncio
async def test_handle_memory_lists_context_paths(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.context_paths = ["docs/*.md", "README.md"]
    out = await handle_builtin_slash("memory", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "docs/*.md" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_theme_opens_selector_action() -> None:
    settings = Settings()
    out = await handle_builtin_slash("theme", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert out.ui_action == "show_theme_selector"


@pytest.mark.asyncio
async def test_handle_resume_opens_switch_session_action() -> None:
    settings = Settings()
    out = await handle_builtin_slash("resume", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert out.ui_action == "switch_session"


@pytest.mark.asyncio
async def test_handle_rename_opens_dialog_when_session_id() -> None:
    settings = Settings()
    ctx = BuiltinSlashContext(session_id="x", session_title="Hi")
    out = await handle_builtin_slash(
        "rename", "", settings=settings, session_service=None, context=ctx
    )
    assert out.kind == "assistant_message"
    assert out.ui_action == "show_rename_dialog"


@pytest.mark.asyncio
async def test_handle_rewind_help_default() -> None:
    settings = Settings()
    out = await handle_builtin_slash("rewind", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    text = (out.assistant_text or "").lower()
    assert "rewind" in text and "chat" in text and "git" in text


@pytest.mark.asyncio
async def test_handle_skills_without_plugin_manager() -> None:
    settings = Settings()
    out = await handle_builtin_slash("skills", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    assert "not available" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_exit_ui_action() -> None:
    settings = Settings()
    out = await handle_builtin_slash("exit", "", settings=settings, session_service=None)
    assert out.ui_action == "exit_app"


@pytest.mark.asyncio
async def test_handle_help_ui_action() -> None:
    settings = Settings()
    out = await handle_builtin_slash("help", "", settings=settings, session_service=None)
    assert out.ui_action == "show_help_screen"


@pytest.mark.asyncio
async def test_handle_fast_stub() -> None:
    settings = Settings()
    out = await handle_builtin_slash("fast", "", settings=settings, session_service=None)
    assert "clawcode" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_context_ascii_bar(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    ctx = BuiltinSlashContext(
        context_percent=50,
        context_window_size=200_000,
        session_prompt_tokens=100,
        session_completion_tokens=20,
        turn_input_tokens=5,
        turn_output_tokens=3,
        model_label="m1",
    )
    out = await handle_builtin_slash(
        "context", "", settings=settings, session_service=None, context=ctx
    )
    assert out.kind == "assistant_message"
    text = out.assistant_text or ""
    assert "█" in text and "░" in text
    assert "context" in text.lower()


@pytest.mark.asyncio
async def test_handle_copy_last_assistant_to_clipboard(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    rows = [
        Message(
            id="m1",
            session_id="sid-test",
            role=MessageRole.USER,
            parts=[TextContent(content="hi")],
        ),
        Message(
            id="m2",
            session_id="sid-test",
            role=MessageRole.ASSISTANT,
            parts=[TextContent(content="last reply body")],
        ),
    ]
    msg_svc = _ForkExportMessageService(rows)
    ctx = BuiltinSlashContext(session_id="sid-test", session_title="S")
    out = await handle_builtin_slash(
        "copy",
        "",
        settings=settings,
        session_service=None,
        message_service=msg_svc,
        context=ctx,
    )
    assert out.clipboard_text and "last reply body" in out.clipboard_text
    assert out.assistant_text and "clipboard" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_cost_shows_session_totals(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    now = int(time.time())
    sess = Session(
        id="sid-cost",
        title="Paid",
        message_count=4,
        prompt_tokens=900,
        completion_tokens=100,
        cost=0.042,
        created_at=now - 125,
        updated_at=now,
    )
    fake_ss = _FakeSessionService([sess])
    ctx = BuiltinSlashContext(session_id="sid-cost", session_title="Paid")
    out = await handle_builtin_slash(
        "cost", "", settings=settings, session_service=fake_ss, context=ctx
    )
    text = out.assistant_text or ""
    assert "0.042" in text or "0.042000" in text
    assert "Paid" in text
    assert "900" in text


@pytest.mark.asyncio
async def test_handle_desktop_honest_no_client_handoff(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("desktop", "", settings=settings, session_service=None)
    text = (out.assistant_text or "").lower()
    assert "terminal" in text or "tui" in text
    assert "desktop" in text
    assert "no official" in text or "not" in text


@pytest.mark.asyncio
async def test_handle_diff_not_git_repo(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("diff", "", settings=settings, session_service=None)
    assert out.kind == "assistant_message"
    text = (out.assistant_text or "").lower()
    assert "git" in text
    assert "work tree" in text or "not" in text


@pytest.mark.asyncio
async def test_handle_diff_help_mentions_per_turn(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("diff", "help", settings=settings, session_service=None)
    text = (out.assistant_text or "").lower()
    assert "per-turn" in text or "per turn" in text or "turn-by-turn" in text


@pytest.mark.asyncio
async def test_handle_doctor_lists_clawcode(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("doctor", "", settings=settings, session_service=None)
    text = out.assistant_text or ""
    assert "clawcode" in text.lower()
    assert "Doctor" in text or "doctor" in text
    assert "desktop" in text.lower()


@pytest.mark.asyncio
async def test_handle_doctor_includes_desktop_tools_line(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash("doctor", "", settings=settings, session_service=None)
    text = out.assistant_text or ""
    assert "**Desktop tools:**" in text or "Desktop tools:" in text


@pytest.mark.asyncio
async def test_handle_doctor_desktop_respects_claw_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    from unittest.mock import MagicMock

    from clawcode.llm.tools.desktop import desktop_utils as du

    settings = Settings()
    settings.working_directory = str(tmp_path)
    settings.desktop.enabled = True
    settings.desktop.tools_require_claw_mode = True
    monkeypatch.setattr(du, "get_settings", lambda: settings)

    sys.modules["mss"] = MagicMock()
    sys.modules["pyautogui"] = MagicMock()
    try:
        out_not = await handle_builtin_slash(
            "doctor",
            "",
            settings=settings,
            session_service=None,
            context=BuiltinSlashContext(claw_mode_enabled=False),
        )
        t_not = out_not.assistant_text or ""
        assert "Desktop tools:" in t_not or "**Desktop tools:**" in t_not
        assert "not ok" in t_not.lower()
        assert "claw" in t_not.lower()

        out_ok = await handle_builtin_slash(
            "doctor",
            "",
            settings=settings,
            session_service=None,
            context=BuiltinSlashContext(claw_mode_enabled=True),
        )
        t_ok = out_ok.assistant_text or ""
        assert "Desktop tools:" in t_ok or "**Desktop tools:**" in t_ok
        assert "**ok**" in t_ok
    finally:
        del sys.modules["mss"]
        del sys.modules["pyautogui"]
    settings.desktop.tools_require_claw_mode = False


@pytest.mark.asyncio
async def test_handle_hooks_with_plugin(tmp_path: Path) -> None:
    class _PM:
        @property
        def plugins(self) -> list[LoadedPlugin]:
            return [
                LoadedPlugin(
                    name="demo",
                    root=tmp_path,
                    manifest=PluginManifest(name="demo"),
                    enabled=True,
                    hooks={HookEvent.PreToolUse: [HookMatcherGroup(matcher="Bash")]},
                )
            ]

    settings = Settings()
    out = await handle_builtin_slash(
        "hooks", "", settings=settings, session_service=None, plugin_manager=_PM()
    )
    assert "demo" in (out.assistant_text or "")
    assert "PreToolUse" in (out.assistant_text or "")


@pytest.mark.asyncio
async def test_handle_fork_copies_messages(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    rows = [
        Message(
            id="m1",
            session_id="sid-test",
            role=MessageRole.USER,
            parts=[TextContent(content="forkme")],
        )
    ]
    msg_svc = _ForkExportMessageService(rows)
    fake_ss = _FakeSessionService([])
    ctx = BuiltinSlashContext(session_id="sid-test", session_title="Parent")
    out = await handle_builtin_slash(
        "fork",
        "",
        settings=settings,
        session_service=fake_ss,
        message_service=msg_svc,
        context=ctx,
    )
    assert out.switch_to_session_id == "sess_forked_test"
    assert len(msg_svc.created) >= 1


@pytest.mark.asyncio
async def test_handle_export_sets_clipboard_payload(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    rows = [
        Message(
            id="m1",
            session_id="sid-test",
            role=MessageRole.USER,
            parts=[TextContent(content="exportme")],
        )
    ]
    msg_svc = _ForkExportMessageService(rows)
    ctx = BuiltinSlashContext(session_id="sid-test", session_title="S")
    out = await handle_builtin_slash(
        "export",
        "",
        settings=settings,
        session_service=None,
        message_service=msg_svc,
        context=ctx,
    )
    assert out.clipboard_text and "exportme" in out.clipboard_text


@pytest.mark.asyncio
async def test_handle_add_dir_appends_context_paths(tmp_path: Path) -> None:
    sub = tmp_path / "extra"
    sub.mkdir()
    (tmp_path / ".clawcode.json").write_text("{}", encoding="utf-8")
    settings = Settings()
    settings.working_directory = str(tmp_path)
    out = await handle_builtin_slash(
        "add-dir",
        str(sub),
        settings=settings,
        session_service=None,
    )
    assert out.kind == "assistant_message"
    data = json.loads((tmp_path / ".clawcode.json").read_text(encoding="utf-8"))
    norm = str(sub.resolve()).replace("\\", "/")
    assert norm in data.get("context_paths", [])


@pytest.mark.asyncio
async def test_handle_agents_lists_default_slots() -> None:
    settings = Settings()
    out = await handle_builtin_slash("agents", "", settings=settings, session_service=None)
    text = (out.assistant_text or "").lower()
    assert "agent" in text
    assert "coder" in text or "summarizer" in text


@pytest.mark.asyncio
async def test_handle_chrome_stub_no_extension() -> None:
    settings = Settings()
    out = await handle_builtin_slash("chrome", "", settings=settings, session_service=None)
    assert "chrome" in (out.assistant_text or "").lower()
    assert "claw" in (out.assistant_text or "").lower()


@pytest.mark.asyncio
async def test_handle_config_opens_external_action() -> None:
    settings = Settings()
    out = await handle_builtin_slash("config", "", settings=settings, session_service=None)
    assert out.ui_action == "open_clawcode_config_external"


@pytest.mark.asyncio
async def test_handle_clear_requests_reload(tmp_path: Path) -> None:
    settings = Settings()
    settings.working_directory = str(tmp_path)
    rows = [
        Message(
            id="z1",
            session_id="sid-test",
            role=MessageRole.USER,
            parts=[TextContent(content="x")],
        )
    ]
    msg_svc = _ForkExportMessageService(rows)
    fake_ss = _FakeSessionService(
        [
            Session(
                id="sid-test",
                title="T",
                message_count=1,
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
        ]
    )
    ctx = BuiltinSlashContext(session_id="sid-test", session_title="T")
    out = await handle_builtin_slash(
        "clear",
        "",
        settings=settings,
        session_service=fake_ss,
        message_service=msg_svc,
        context=ctx,
    )
    assert out.ui_action == "reload_session_history"


@pytest.mark.asyncio
async def test_handle_release_notes_has_version_heading() -> None:
    settings = Settings()
    out = await handle_builtin_slash(
        "release-notes", "", settings=settings, session_service=None
    )
    assert out.kind == "assistant_message"
    assert out.assistant_text is not None
    assert "Release notes" in out.assistant_text or "Version" in out.assistant_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    sorted(BUILTIN_SLASH_NAMES),
    ids=sorted(BUILTIN_SLASH_NAMES),
)
async def test_each_builtin_command_reaches_handler(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: every registered built-in name must be handled without raising."""
    settings = Settings()
    settings.working_directory = str(tmp_path)

    async def _noop_fetch(_pr: github_pr.PrRef) -> dict:
        return {
            "pull": {"number": 1, "title": "T", "state": "open", "html_url": "u"},
            "issue_comments": [],
            "review_comments": [],
            "reviews": [],
        }

    async def _noop_ctx(_pr: github_pr.PrRef) -> dict:
        return {
            "pull": {"title": "T", "html_url": "u"},
            "files_meta": [],
            "patch_excerpt": "",
        }

    monkeypatch.setattr(builtin_slash_handlers, "fetch_pr_comments", _noop_fetch)
    monkeypatch.setattr(builtin_slash_handlers, "fetch_pr_review_context", _noop_ctx)
    monkeypatch.setattr(builtin_slash_handlers, "run_git_diff", lambda _cwd: "(diff)")

    tail = ""
    if name in ("pr-comments", "review"):
        tail = "https://github.com/x/y/pull/1"
    cost_sess = Session(
        id="sid-test",
        title="ParamCost",
        message_count=1,
        prompt_tokens=1,
        completion_tokens=1,
        cost=0.0,
        created_at=int(time.time()) - 30,
        updated_at=int(time.time()),
    )
    fake_ss = _FakeSessionService([cost_sess] if name in ("cost", "clear", "compact") else [])
    ctx = (
        BuiltinSlashContext(session_id="sid-test", session_title="Test")
        if name in ("rename", "fork", "export", "copy", "cost", "clear", "compact")
        else BuiltinSlashContext()
    )
    sample_rows = [
        Message(
            id="m1",
            session_id="sid-test",
            role=MessageRole.USER,
            parts=[TextContent(content="hi")],
        ),
        Message(
            id="m2",
            session_id="sid-test",
            role=MessageRole.ASSISTANT,
            parts=[TextContent(content="a1")],
        ),
        Message(
            id="m3",
            session_id="sid-test",
            role=MessageRole.USER,
            parts=[TextContent(content="u2")],
        ),
        Message(
            id="m4",
            session_id="sid-test",
            role=MessageRole.ASSISTANT,
            parts=[TextContent(content="a2")],
        ),
        Message(
            id="m5",
            session_id="sid-test",
            role=MessageRole.USER,
            parts=[TextContent(content="u3")],
        ),
    ]
    msg_svc = (
        _ForkExportMessageService(sample_rows)
        if name in ("fork", "export", "copy", "clear", "compact")
        else None
    )

    if name == "compact":

        class _FakeSum:
            summary_message = Message(
                id="sum_fake",
                session_id="sid-test",
                role=MessageRole.SYSTEM,
                parts=[TextContent(content="[SUMMARY] t")],
            )

        async def _fake_force(*_a: object, **_k: object) -> object:
            return _FakeSum()

        monkeypatch.setattr(
            "clawcode.history.summarizer.SummarizerService.force_summarize",
            _fake_force,
        )

    out = await handle_builtin_slash(
        name,
        tail,
        settings=settings,
        session_service=fake_ss,
        context=ctx,
        message_service=msg_svc,
    )
    assert isinstance(out, BuiltinSlashOutcome)
    if out.kind == "assistant_message":
        if out.ui_action in (
            "toggle_vim",
            "show_theme_selector",
            "show_rename_dialog",
            "switch_session",
            "reload_session_history",
            "confirm_git_restore",
            "open_model_dialog",
            "open_display_mode",
            "exit_app",
            "show_help_screen",
            "open_clawcode_config_external",
        ):
            assert out.ui_action in (
                "toggle_vim",
                "show_theme_selector",
                "show_rename_dialog",
                "switch_session",
                "reload_session_history",
                "confirm_git_restore",
                "open_model_dialog",
                "open_display_mode",
                "exit_app",
                "show_help_screen",
                "open_clawcode_config_external",
            )
        else:
            assert (
                (out.assistant_text and out.assistant_text.strip())
                or (getattr(out, "clipboard_text", None) or "").strip()
                or (getattr(out, "switch_to_session_id", None) or "").strip()
            )
    else:
        assert out.agent_user_text is not None and out.agent_user_text.strip()
