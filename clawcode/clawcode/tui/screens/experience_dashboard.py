"""Experience Dashboard TUI Screen.

Visualizes team-level and personal experience metrics (ECAP/TECAP),
alerts, window comparisons, and adaptive policy suggestions.

Style: blue primary, yellow accent — matching the ClawCode welcome banner.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from rich import box
from rich.align import Align
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.console import Group
from textual.screen import Screen
from textual.widgets import Static, Button, Header, Footer
from textual.containers import VerticalScroll, Vertical, Horizontal

if TYPE_CHECKING:
    from ...config.settings import Settings

_C_BLUE = "#5c9cf5"
_C_BLUE_LIGHT = "#7eb8ff"
_C_YELLOW = "#f9e2af"
_C_MUTED = "#92a0b4"
_C_PRIMARY = "#d8dee9"
_C_RED = "#f38ba8"
_C_GREEN = "#a6e3a1"


def _fmt(v, pct: bool = False) -> str:
    if v is None:
        return "-"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return str(v)
    if pct:
        return f"{fv * 100:.1f}%"
    return f"{fv:.3f}"


def _bar(value, width: int = 12, max_val: float = 1.0) -> str:
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return "░" * width
    filled = int(fv / max_val * width) if max_val > 0 else 0
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _status_color(status: str) -> str:
    return {"ok": _C_GREEN, "warning": _C_YELLOW, "critical": _C_RED, "normal": _C_BLUE_LIGHT}.get(status, _C_MUTED)


def _metric_status(value, thresholds):
    if not thresholds:
        return "normal"
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return "normal"
    if "critical_lt" in thresholds and fv < thresholds["critical_lt"]:
        return "critical"
    if "critical_gt" in thresholds and fv > thresholds["critical_gt"]:
        return "critical"
    if "warning_lt" in thresholds and fv < thresholds["warning_lt"]:
        return "warning"
    if "warning_gt" in thresholds and fv > thresholds["warning_gt"]:
        return "warning"
    return "ok"


class ExperienceDashboardScreen(Screen):

    BINDINGS = [
        ("q", "close_dashboard", "Close"),
        ("escape", "close_dashboard", "Close"),
        ("r", "refresh_dashboard", "Refresh"),
    ]

    def __init__(self, settings: Any, domain: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._settings = settings
        self._domain = domain
        self._data: dict | None = None

    def compose(self):
        yield Header()
        with VerticalScroll(id="dashboard_screen"):
            yield Static("Loading...", id="dashboard_content")
            with Horizontal(id="dashboard_actions"):
                yield Button("Refresh [R]", variant="primary", id="btn_refresh")
                yield Button("Close [Q]", variant="default", id="btn_close")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh_dashboard()

    def action_close_dashboard(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        key = event.key
        if key in ("q", "escape"):
            event.prevent_default()
            event.stop()
            self.app.pop_screen()
            return
        if key == "r":
            event.prevent_default()
            event.stop()
            self.action_refresh_dashboard()
            return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = getattr(event.button, "id", "")
        if btn_id == "btn_close":
            self.app.pop_screen()
        elif btn_id == "btn_refresh":
            self.action_refresh_dashboard()

    def action_refresh_dashboard(self) -> None:
        self.run_worker(self._load_data(), exclusive=True)

    async def _load_data(self) -> None:
        try:
            content = self.query_one("#dashboard_content", Static)
            content.update(self._loading_renderable())
        except Exception:
            pass
        try:
            from ...learning.service import LearningService

            svc = LearningService(self._settings)
            snap = await asyncio.to_thread(
                svc.experience_dashboard_query,
                include_alerts=True,
                domain=self._domain,
            )
            self._data = snap
            self._render_dashboard()
        except Exception as exc:
            try:
                content = self.query_one("#dashboard_content", Static)
                content.update(self._error_renderable(exc))
            except Exception:
                pass

    def _render_dashboard(self) -> None:
        if not self._data:
            return
        try:
            content = self.query_one("#dashboard_content", Static)
            content.update(self._build_dashboard())
        except Exception as exc:
            try:
                content = self.query_one("#dashboard_content", Static)
                content.update(self._error_renderable(exc))
            except Exception:
                pass

    def _loading_renderable(self):
        t = Text()
        t.append("\n\n")
        t.append("  Loading Experience Dashboard...", style=f"bold {_C_BLUE_LIGHT}")
        t.append("\n\n  Please wait...", style=_C_MUTED)
        return Panel(t, title=Text(" Experience Dashboard ", style=f"bold {_C_YELLOW}"), border_style=_C_BLUE, box=box.ROUNDED, padding=(1, 1))

    def _error_renderable(self, exc):
        t = Text()
        t.append("\n  Error\n\n", style=f"bold {_C_RED}")
        t.append(f"  {escape(str(exc))}", style=_C_MUTED)
        t.append("\n\n  Press [R] retry, [Q] close.", style=_C_MUTED)
        return Panel(t, title=Text(" Experience Dashboard ", style=f"bold {_C_YELLOW}"), border_style=_C_RED, box=box.ROUNDED, padding=(1, 1))

    def _build_dashboard(self):
        dash = (self._data or {}).get("experience_dashboard") or {}
        alerts_data = (self._data or {}).get("experience_alerts") or {}
        policy = (self._data or {}).get("experience_policy_advice") or {}
        health = (self._data or {}).get("experience_health", "unknown")

        sections = []
        sections.append(self._header_section(health, dash))
        sections.append(self._metrics_section(dash))
        sections.append(self._scope_section(dash))
        sections.append(self._window_section(dash))
        sections.append(self._alerts_section(alerts_data))
        sections.append(self._policy_section(policy))
        sections.append(self._ab_section(dash))
        sections.append(self._footer_section())

        return Panel(
            Group(*sections),
            title=Text(" Experience Dashboard ", style=f"bold {_C_YELLOW}"),
            border_style=_C_BLUE,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _header_section(self, health, dash):
        hc = _status_color(health)
        t = Text()
        t.append("Health: ", style=_C_MUTED)
        t.append(health.upper(), style=f"bold {hc}")
        domain = dash.get("domain", "")
        if domain:
            t.append(f"  Domain: {domain}", style=_C_MUTED)
        t.append("\n")
        return t

    def _metrics_section(self, dash):
        metrics = dash.get("metrics") or {}
        thresholds = {}
        cl = getattr(self._settings, "closed_loop", None)
        if cl:
            thresholds = getattr(cl, "experience_alert_thresholds", {})

        rows_def = [
            ("ecap_effectiveness_avg", "Effectiveness", True),
            ("ecap_confidence_avg", "Confidence", True),
            ("ecap_ci_width_avg", "CI Width", True),
            ("ecap_sample_sufficiency_rate", "Sample Suff.", True),
            ("ecap_gap_convergence", "Gap Conv.", True),
            ("routing_experience_contribution", "Routing", True),
            ("instinct_delta_net", "Instinct Δ", False),
            ("experience_gate_block_rate", "Gate Block", True),
            ("tuning_experience_gate_pass_rate", "Gate Pass", True),
            ("closed_loop_gain_consistency", "CL Gain", True),
        ]

        table = Table(
            title=Text("Core Metrics", style=f"bold {_C_BLUE_LIGHT}"),
            show_lines=False,
            expand=True,
            box=box.SIMPLE,
            border_style=f"{_C_BLUE} dim",
            padding=0,
        )
        table.add_column("Metric", style=_C_PRIMARY, ratio=3)
        table.add_column("Value", justify="right", ratio=2)
        table.add_column("Bar", ratio=3)
        table.add_column("Status", ratio=2)

        for key, label, is_pct in rows_def:
            val = metrics.get(key)
            if val is None:
                table.add_row(Text(label, style=_C_MUTED), "-", "", "")
                continue
            status = _metric_status(val, thresholds.get(key))
            sc = _status_color(status)
            try:
                fv = float(val)
            except (TypeError, ValueError):
                table.add_row(Text(label, style=_C_MUTED), str(val), "", "")
                continue
            bv = fv if "block" not in key and "width" not in key else 1.0 - fv
            table.add_row(label, _fmt(fv, pct=is_pct), Text(_bar(bv, 12), style=sc), Text(status, style=f"bold {sc}"))
        return table

    def _scope_section(self, dash):
        scope = dash.get("scope_metrics") or {}
        team = scope.get("team") or {}

        table = Table(
            title=Text("Team (TECAP)", style=f"bold {_C_BLUE_LIGHT}"),
            show_lines=False,
            expand=True,
            box=box.SIMPLE,
            border_style=f"{_C_BLUE} dim",
            padding=0,
        )
        table.add_column("Layer", style=_C_PRIMARY, ratio=3)
        table.add_column("Value", justify="right", ratio=2)

        table.add_row(Text("TECAP Count", style=_C_YELLOW), str(team.get("tecap_count", 0)))
        table.add_row(Text("Avg Score", style=_C_YELLOW), _fmt(team.get("avg_score", 0.0), pct=True))
        for name in ("model", "agent", "skill", "team"):
            sd = scope.get(name)
            if not isinstance(sd, dict):
                continue
            v = sd.get("routing_experience_contribution")
            if v is not None:
                table.add_row(f"  {name.title()}", _fmt(v, pct=True))
        return table

    def _window_section(self, dash):
        wm = dash.get("window_metrics") or {}
        if not wm:
            return Text("")
        try:
            windows = sorted(wm.keys(), key=lambda x: int(x))
        except (ValueError, TypeError):
            windows = list(wm.keys())

        table = Table(
            title=Text("Windows", style=f"bold {_C_BLUE_LIGHT}"),
            show_lines=False,
            expand=True,
            box=box.SIMPLE,
            border_style=f"{_C_BLUE} dim",
            padding=0,
        )
        table.add_column("Metric", style=_C_PRIMARY, ratio=3)
        for w in windows:
            table.add_column(Text(f"{w}d", style=f"bold {_C_YELLOW}"), justify="right", ratio=2)

        for key, label in [
            ("ecap_effectiveness_avg", "Effect."),
            ("ecap_confidence_avg", "Confid."),
            ("ecap_sample_sufficiency_rate", "Suff."),
            ("routing_experience_contribution", "Routing"),
        ]:
            row = [label]
            for w in windows:
                wd = wm.get(w)
                if not isinstance(wd, dict):
                    row.append("-")
                    continue
                v = wd.get(key)
                row.append(_fmt(v, pct=True) if v is not None else "-")
            table.add_row(*row)
        return table

    def _alerts_section(self, alerts_data):
        level = alerts_data.get("level", "ok")
        alerts_list = alerts_data.get("alerts") or []
        lc = _status_color(level)

        t = Text()
        t.append("Alerts: ", style=_C_MUTED)
        t.append(level.upper(), style=f"bold {lc}")

        if not alerts_list:
            t.append("  ✓ healthy", style=_C_GREEN)
        else:
            for a in alerts_list[:3]:
                if not isinstance(a, dict):
                    continue
                ac = _status_color(a.get("level", "warning"))
                t.append(f"\n  ● {a.get('metric', '?')} = {_fmt(a.get('value'), pct=True)} ({a.get('reason', '')})", style=ac)

        return t

    def _policy_section(self, policy):
        guard = policy.get("guard_mode", "normal")
        suggestions = policy.get("suggestions") or []

        t = Text()
        t.append("Policy: ", style=_C_MUTED)
        t.append(guard, style=f"bold {_C_YELLOW}")

        if suggestions:
            for s in suggestions[:3]:
                if not isinstance(s, dict):
                    continue
                t.append(f"\n  → {s.get('target', '?')} {s.get('op', '?')} {s.get('delta') or s.get('value', '')} — {s.get('reason', '')}", style=_C_BLUE_LIGHT)
        else:
            t.append("  No suggestions", style=_C_MUTED)

        return t

    def _ab_section(self, dash):
        ab = dash.get("ab_comparison") or {}
        if not ab.get("enabled"):
            return Text("")

        t = Text()
        sig = ab.get("is_significant", False)
        t.append("A/B: ", style=_C_MUTED)
        t.append(f"{ab.get('experiment_id', '?')} ", style=f"bold {_C_YELLOW}")
        t.append(f"Δ={_fmt(ab.get('delta', 0.0))} ", style=_C_BLUE_LIGHT)
        t.append(f"Conf={_fmt(ab.get('confidence', 0.0), pct=True)} ", style=_C_BLUE_LIGHT)
        t.append("✓ Significant" if sig else "Not Significant", style=f"bold {_C_GREEN if sig else _C_YELLOW}")
        return t

    def _footer_section(self):
        t = Text()
        t.append("─" * 40, style=f"{_C_BLUE} dim")
        t.append("\n[Q] Close    [R] Refresh    [↑↓] Scroll", style=_C_MUTED)
        return Align.center(t)
