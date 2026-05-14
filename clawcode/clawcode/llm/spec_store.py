"""Spec artifact persistence for /spec workflow.

Stores three documents per spec session:
  spec.md      — detailed specification
  tasks.md     — ordered task breakdown with dependencies
  checklist.md — acceptance verification items

All files live under ``.claw/specs/spec-{session_prefix}-{ts}/``.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..storage_paths import iter_read_candidates, resolve_write_path


@dataclass
class SpecTask:
    id: str
    title: str
    description: str = ""
    priority: str = "medium"
    depends_on: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    files_to_modify: list[str] = field(default_factory=list)
    status: str = "pending"
    checklist_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecTask":
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            priority=str(data.get("priority") or "medium"),
            depends_on=list(data.get("depends_on") or []),
            acceptance_criteria=list(data.get("acceptance_criteria") or []),
            files_to_modify=list(data.get("files_to_modify") or []),
            status=str(data.get("status") or "pending"),
            checklist_refs=list(data.get("checklist_refs") or []),
        )


@dataclass
class CheckItem:
    id: str
    description: str
    task_ref: str = ""
    verified: bool = False
    auto_verify_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckItem":
        return cls(
            id=str(data.get("id") or ""),
            description=str(data.get("description") or ""),
            task_ref=str(data.get("task_ref") or ""),
            verified=bool(data.get("verified") or False),
            auto_verify_command=str(data.get("auto_verify_command") or ""),
        )


@dataclass
class SpecExecutionState:
    current_task_index: int = 0
    started_at: int = 0
    finished_at: int = 0
    last_progress_at: int = 0
    verified_count: int = 0
    failed_count: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecExecutionState":
        return cls(
            current_task_index=int(data.get("current_task_index") or 0),
            started_at=int(data.get("started_at") or 0),
            finished_at=int(data.get("finished_at") or 0),
            last_progress_at=int(data.get("last_progress_at") or 0),
            verified_count=int(data.get("verified_count") or 0),
            failed_count=int(data.get("failed_count") or 0),
            last_error=str(data.get("last_error") or ""),
        )


@dataclass
class SpecBundle:
    session_id: str
    user_request: str
    spec_markdown: str = ""
    tasks_markdown: str = ""
    checklist_markdown: str = ""
    created_at: int = 0
    approved_at: int = 0
    spec_dir: str = ""
    tasks: list[SpecTask] = field(default_factory=list)
    checklist: list[CheckItem] = field(default_factory=list)
    execution: SpecExecutionState = field(default_factory=SpecExecutionState)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_request": self.user_request,
            "spec_markdown": self.spec_markdown,
            "tasks_markdown": self.tasks_markdown,
            "checklist_markdown": self.checklist_markdown,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
            "spec_dir": self.spec_dir,
            "tasks": [t.to_dict() for t in self.tasks],
            "checklist": [c.to_dict() for c in self.checklist],
            "execution": self.execution.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecBundle":
        tasks = [SpecTask.from_dict(t) for t in (data.get("tasks") or []) if isinstance(t, dict)]
        checklist = [CheckItem.from_dict(c) for c in (data.get("checklist") or []) if isinstance(c, dict)]
        exe = SpecExecutionState.from_dict(data.get("execution") or {})
        return cls(
            session_id=str(data.get("session_id") or ""),
            user_request=str(data.get("user_request") or ""),
            spec_markdown=str(data.get("spec_markdown") or ""),
            tasks_markdown=str(data.get("tasks_markdown") or ""),
            checklist_markdown=str(data.get("checklist_markdown") or ""),
            created_at=int(data.get("created_at") or 0),
            approved_at=int(data.get("approved_at") or 0),
            spec_dir=str(data.get("spec_dir") or ""),
            tasks=tasks,
            checklist=checklist,
            execution=exe,
        )


class SpecStore:
    """Manage spec artifacts on disk."""

    def __init__(self, working_directory: str | None = None):
        self._cwd = working_directory or "."

    def _spec_base_dir(self) -> Path:
        p = resolve_write_path(self._cwd, ".claw/specs")
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _session_dir(self, session_id: str, ts: int | None = None) -> Path:
        base = self._spec_base_dir()
        prefix = session_id[:8] if len(session_id) >= 8 else session_id
        stamp = ts or int(time.time())
        d = base / f"spec-{prefix}-{stamp}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_bundle(self, bundle: SpecBundle) -> SpecBundle:
        if not bundle.spec_dir:
            bundle.spec_dir = str(self._session_dir(bundle.session_id, bundle.created_at or None))
        spec_dir = Path(bundle.spec_dir)
        spec_dir.mkdir(parents=True, exist_ok=True)

        (spec_dir / "spec.md").write_text(bundle.spec_markdown, encoding="utf-8")
        (spec_dir / "tasks.md").write_text(bundle.tasks_markdown, encoding="utf-8")
        (spec_dir / "checklist.md").write_text(bundle.checklist_markdown, encoding="utf-8")
        (spec_dir / "meta.json").write_text(json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return bundle

    def load_bundle(self, spec_dir: str) -> SpecBundle | None:
        meta_path = Path(spec_dir) / "meta.json"
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return SpecBundle.from_dict(data)
        except Exception:
            return None

    def find_latest_bundle_for_session(self, session_id: str) -> SpecBundle | None:
        base = self._spec_base_dir()
        if not base.exists():
            return None
        prefix = session_id[:8] if len(session_id) >= 8 else session_id
        candidates = sorted(base.glob(f"spec-{prefix}-*"), reverse=True)
        for d in candidates:
            if not d.is_dir():
                continue
            bundle = self.load_bundle(str(d))
            if bundle and bundle.session_id == session_id:
                return bundle
        return None

    def update_task_status(self, bundle: SpecBundle, task_id: str, status: str) -> None:
        for t in bundle.tasks:
            if t.id == task_id:
                t.status = status
                break
        self.save_bundle(bundle)

    def update_checklist_item(self, bundle: SpecBundle, check_id: str, verified: bool) -> None:
        for c in bundle.checklist:
            if c.id == check_id:
                c.verified = verified
                break
        self.save_bundle(bundle)
