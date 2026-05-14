"""Right-side plan todo panel with Build action."""

from __future__ import annotations

from textual.containers import HorizontalScroll, Vertical, VerticalScroll
from textual.widgets import Button, Static

from ....llm.plan_store import PlanTaskItem


class PlanPanel(Vertical):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pulse_frame: int = 0
        self._state: dict | None = None
        self._pulse_timer = None  # running only while is_building=True
        # Hidden until ChatScreen._refresh_plan_panel sets display from plan state
        # (avoids Build/Stop/Retry flashing during TUI startup before async init).
        self.display = False

    def on_mount(self) -> None:
        # Timer is started on-demand in set_plan() when a build begins.
        pass

    def _on_pulse(self) -> None:
        if not self._state or not bool(self._state.get("is_building")):
            self._stop_pulse()
            return
        self._pulse_frame = (self._pulse_frame + 1) % 7
        self._render_from_state()

    def _start_pulse(self) -> None:
        """Start the animation timer if not already running."""
        if self._pulse_timer is not None:
            return
        self._pulse_timer = self.set_interval(0.35, self._on_pulse)

    def _stop_pulse(self) -> None:
        """Stop the animation timer and release the resource."""
        if self._pulse_timer is None:
            return
        try:
            self._pulse_timer.stop()
        except Exception:
            pass
        self._pulse_timer = None

    def compose(self):
        yield Static("", id="plan_panel_title")
        yield Static("", id="plan_panel_meta")
        with VerticalScroll(id="plan_panel_body_scroll"):
            yield Static("", id="plan_panel_body")
        yield Static("", id="plan_panel_footer")
        with HorizontalScroll(id="plan_panel_actions", can_focus=True):
            yield Button("Build", id="plan_build_button", variant="success")
            yield Button("Stop", id="plan_stop_button")
            yield Button("Retry", id="plan_retry_button")
            yield Button("Resume", id="plan_resume_button", variant="primary")

    def set_plan(
        self,
        *,
        title: str,
        todo_count: int,
        tasks: list[PlanTaskItem],
        is_building: bool,
        current_task_index: int,
        can_build: bool,
        is_completed: bool,
        can_stop: bool,
        can_retry_current: bool,
        can_resume: bool,
        status_text: str,
        running_task_title: str = "",
    ) -> None:
        self._state = {
            "title": title,
            "todo_count": todo_count,
            "tasks": tasks,
            "is_building": is_building,
            "current_task_index": current_task_index,
            "can_build": can_build,
            "is_completed": is_completed,
            "can_stop": can_stop,
            "can_retry_current": can_retry_current,
            "can_resume": can_resume,
            "status_text": status_text,
            "running_task_title": running_task_title,
        }
        # Start / stop the pulse animation timer on demand.
        if is_building:
            self._start_pulse()
        else:
            self._stop_pulse()
        self._render_from_state()

    def _render_from_state(self) -> None:
        if not self._state:
            return
        title = str(self._state["title"])
        todo_count = int(self._state["todo_count"])
        tasks = list(self._state["tasks"])
        is_building = bool(self._state["is_building"])
        current_task_index = int(self._state["current_task_index"])
        can_build = bool(self._state["can_build"])
        is_completed = bool(self._state["is_completed"])
        can_stop = bool(self._state["can_stop"])
        can_retry_current = bool(self._state["can_retry_current"])
        can_resume = bool(self._state["can_resume"])
        status_text = str(self._state["status_text"] or "")
        running_task_title = str(self._state.get("running_task_title") or "")
        title_widget = self.query_one("#plan_panel_title", Static)
        meta_widget = self.query_one("#plan_panel_meta", Static)
        body_widget = self.query_one("#plan_panel_body", Static)
        footer_widget = self.query_one("#plan_panel_footer", Static)
        button = self.query_one("#plan_build_button", Button)
        stop_button = self.query_one("#plan_stop_button", Button)
        retry_button = self.query_one("#plan_retry_button", Button)
        resume_button = self.query_one("#plan_resume_button", Button)

        title_widget.update(f"Plan: {title}")
        if is_completed:
            meta_widget.update("[Build Completed]")
        else:
            meta_widget.update(f"{todo_count} To-dos" if todo_count > 0 else "")

        lines: list[str] = []
        if not tasks:
            lines.append("No tasks yet. Run /plan, then send your request.")
        spinner = ("◐", "◓", "◑", "◒")
        for i, task in enumerate(tasks):
            icon = "○"
            if task.status == "in_progress":
                icon = spinner[self._pulse_frame % len(spinner)] if is_building else "◐"
            elif task.status == "completed":
                icon = "✓"
            elif task.status == "failed":
                icon = "✗"
            prefix = ">" if is_building and i == current_task_index else " "
            lines.append(f"{prefix} {icon} {i + 1}. {task.title}")
        body_widget.update("\n".join(lines))

        button.disabled = not can_build
        stop_button.disabled = not can_stop
        retry_button.disabled = not can_retry_current
        resume_button.disabled = not can_resume
        if is_building:
            dots = "." * (self._pulse_frame + 1)
            # Narrow buttons: keep a short label; full progress stays in the footer.
            button.label = "Busy"
            n_tasks = len(tasks)
            k = current_task_index + 1 if 0 <= current_task_index < n_tasks else 0
            progress = ""
            if n_tasks and k > 0:
                title_bit = running_task_title[:48] + ("…" if len(running_task_title) > 48 else "")
                if title_bit:
                    progress = f"Task {k}/{n_tasks} · {title_bit}  "
                else:
                    progress = f"Task {k}/{n_tasks}  "
            footer_widget.update(
                f"{progress}{status_text or 'Executing tasks sequentially'}{dots}"
            )
        elif is_completed:
            button.label = "Build"
            footer_widget.update(status_text or "Build completed.")
        else:
            button.label = "Build"
            footer_widget.update(status_text or "Ready to build.")


__all__ = ["PlanPanel"]

