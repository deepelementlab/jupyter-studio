from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..claw_learning.ops_observability import emit_ops_event

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ALLOWED_SUBDIRS = {"references", "templates", "scripts", "assets"}


@dataclass(frozen=True)
class ClawSkillsPaths:
    root: Path


def get_claw_skills_paths() -> ClawSkillsPaths:
    settings = get_settings()
    data_dir = settings.ensure_data_directory()
    root = data_dir / "claw_skills"
    root.mkdir(parents=True, exist_ok=True)
    return ClawSkillsPaths(root=root)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.tmp.", suffix="")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    m = re.search(r"\n---\s*\n", content[3:])
    if not m:
        return {}, content
    raw = content[3 : m.start() + 3]
    body = content[m.end() + 3 :]
    # lightweight parse (fallback-safe)
    fm: dict[str, Any] = {}
    try:
        import yaml

        y = yaml.safe_load(raw)
        if isinstance(y, dict):
            fm = y
    except Exception:
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip().strip("'").strip('"')
    return fm, body


def validate_skill_name(name: str) -> str | None:
    if not name:
        return "Skill name is required."
    if len(name) > MAX_NAME_LENGTH:
        return f"Skill name exceeds {MAX_NAME_LENGTH} characters."
    if not VALID_NAME_RE.match(name):
        return "Invalid skill name. Use lowercase letters, numbers, dots, underscores, hyphens."
    return None


def validate_skill_content(content: str) -> str | None:
    if not (content or "").strip():
        return "Content cannot be empty."
    if not content.startswith("---"):
        return "SKILL.md must start with YAML frontmatter."
    m = re.search(r"\n---\s*\n", content[3:])
    if not m:
        return "SKILL.md frontmatter must be closed with '---'."
    fm, body = _parse_frontmatter(content)
    if not isinstance(fm, dict):
        return "Frontmatter must be key-value mapping."
    if "name" not in fm:
        return "Frontmatter must include 'name'."
    if "description" not in fm:
        return "Frontmatter must include 'description'."
    if len(str(fm.get("description", ""))) > MAX_DESCRIPTION_LENGTH:
        return f"Description exceeds {MAX_DESCRIPTION_LENGTH} characters."
    if not body.strip():
        return "SKILL.md body cannot be empty."
    return None


def validate_file_path(file_path: str) -> str | None:
    if not file_path:
        return "file_path is required."
    p = Path(file_path)
    if ".." in p.parts:
        return "Path traversal is not allowed."
    if not p.parts or p.parts[0] not in ALLOWED_SUBDIRS:
        return f"file_path must be under one of: {', '.join(sorted(ALLOWED_SUBDIRS))}"
    if len(p.parts) < 2:
        return "Provide file path including filename."
    return None


class SkillStore:
    def _append_changelog(self, skill_dir: Path, *, action: str, why: str) -> None:
        if not self._audit_enabled:
            return
        log_file = skill_dir / "CHANGELOG.md"
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        reason = why.strip() if why.strip() else "unspecified"
        line = f"- {ts} | action={action} | why={reason}\n"
        old = ""
        if log_file.exists():
            try:
                old = log_file.read_text(encoding="utf-8")
            except OSError:
                old = ""
        _atomic_write_text(log_file, old + line)
        emit_ops_event(
            "skill_audit_write",
            {
                "skill": skill_dir.name,
                "action": action,
                "why": reason[:160],
                "domain": "general",
                "source": "skill_store",
                "tool_name": "skill_manage",
            },
        )

    def __init__(self) -> None:
        self._paths = get_claw_skills_paths()
        try:
            self._audit_enabled = bool(get_settings().closed_loop.skill_audit_enabled)
        except Exception:
            self._audit_enabled = True

    def _find_skill_dir(self, name: str) -> Path | None:
        if not self._paths.root.exists():
            return None
        for s in self._paths.root.rglob("SKILL.md"):
            if s.parent.name == name:
                return s.parent
        return None

    def list_skills(self) -> dict[str, Any]:
        out: list[dict[str, Any]] = []
        for s in sorted(self._paths.root.rglob("SKILL.md")):
            try:
                txt = s.read_text(encoding="utf-8")
            except OSError:
                continue
            fm, _ = _parse_frontmatter(txt)
            out.append(
                {
                    "name": s.parent.name,
                    "path": str(s.parent.relative_to(self._paths.root)).replace("\\", "/"),
                    "description": str(fm.get("description", "")),
                    "version": str(fm.get("version", "")),
                }
            )
        return {"success": True, "skills": out, "count": len(out)}

    def view_skill(self, name: str, file_path: str | None = None) -> dict[str, Any]:
        d = self._find_skill_dir(name)
        if not d:
            return {"success": False, "error": f"Skill '{name}' not found."}
        target = d / file_path if file_path else d / "SKILL.md"
        if not target.exists():
            return {"success": False, "error": f"File not found: {file_path or 'SKILL.md'}"}
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as e:
            return {"success": False, "error": f"Read failed: {e}"}
        return {
            "success": True,
            "name": name,
            "path": str(target),
            "file_path": file_path or "SKILL.md",
            "content": content,
        }

    def create_skill(self, name: str, content: str, category: str | None = None, *, why: str = "") -> dict[str, Any]:
        err = validate_skill_name(name)
        if err:
            return {"success": False, "error": err}
        err = validate_skill_content(content)
        if err:
            return {"success": False, "error": err}
        if self._find_skill_dir(name):
            return {"success": False, "error": f"Skill '{name}' already exists."}
        d = self._paths.root / category / name if category else self._paths.root / name
        d.mkdir(parents=True, exist_ok=True)
        skill_md = d / "SKILL.md"
        _atomic_write_text(skill_md, content)
        self._append_changelog(d, action="create", why=why)
        return {
            "success": True,
            "message": f"Skill '{name}' created.",
            "path": str(d.relative_to(self._paths.root)).replace("\\", "/"),
            "skill_md": str(skill_md),
        }

    def edit_skill(self, name: str, content: str, *, why: str = "") -> dict[str, Any]:
        err = validate_skill_content(content)
        if err:
            return {"success": False, "error": err}
        d = self._find_skill_dir(name)
        if not d:
            return {"success": False, "error": f"Skill '{name}' not found."}
        _atomic_write_text(d / "SKILL.md", content)
        self._append_changelog(d, action="edit", why=why)
        return {"success": True, "message": f"Skill '{name}' updated.", "path": str(d)}

    def patch_skill(
        self,
        name: str,
        old_string: str,
        new_string: str,
        file_path: str | None = None,
        replace_all: bool = False,
        why: str = "",
    ) -> dict[str, Any]:
        if not old_string:
            return {"success": False, "error": "old_string is required."}
        if new_string is None:
            return {"success": False, "error": "new_string is required."}
        d = self._find_skill_dir(name)
        if not d:
            return {"success": False, "error": f"Skill '{name}' not found."}
        target = d / "SKILL.md"
        if file_path:
            err = validate_file_path(file_path)
            if err:
                return {"success": False, "error": err}
            target = d / file_path
        if not target.exists():
            return {"success": False, "error": f"File not found: {target.relative_to(d)}"}
        content = target.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return {
                "success": False,
                "error": "old_string not found in file.",
                "file_preview": content[:500] + ("..." if len(content) > 500 else ""),
            }
        if count > 1 and not replace_all:
            lines = content.splitlines()
            hit = content.find(old_string)
            context = ""
            if hit >= 0:
                line_idx = content[:hit].count("\n")
                lo = max(0, line_idx - 2)
                hi = min(len(lines), line_idx + 3)
                context = "\n".join(lines[lo:hi])
            return {
                "success": False,
                "error": f"old_string matched {count} times. Provide unique context or set replace_all=true.",
                "match_count": count,
                "conflict_context": context,
            }
        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        if not file_path:
            err = validate_skill_content(new_content)
            if err:
                return {"success": False, "error": f"Patch would break SKILL.md: {err}"}
        _atomic_write_text(target, new_content)
        self._append_changelog(d, action="patch", why=why)
        replaced = count if replace_all else 1
        return {
            "success": True,
            "message": f"Patched {file_path or 'SKILL.md'} in skill '{name}' ({replaced} replacement{'s' if replaced > 1 else ''}).",
        }

    def delete_skill(self, name: str, *, why: str = "") -> dict[str, Any]:
        d = self._find_skill_dir(name)
        if not d:
            return {"success": False, "error": f"Skill '{name}' not found."}
        self._append_changelog(d, action="delete", why=why)
        shutil.rmtree(d, ignore_errors=True)
        if d.parent != self._paths.root and d.parent.exists() and not any(d.parent.iterdir()):
            d.parent.rmdir()
        return {"success": True, "message": f"Skill '{name}' deleted."}

    def write_file(self, name: str, file_path: str, file_content: str, *, why: str = "") -> dict[str, Any]:
        err = validate_file_path(file_path)
        if err:
            return {"success": False, "error": err}
        d = self._find_skill_dir(name)
        if not d:
            return {"success": False, "error": f"Skill '{name}' not found."}
        target = d / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(target, file_content)
        self._append_changelog(d, action=f"write_file:{file_path}", why=why)
        return {"success": True, "message": f"File '{file_path}' written to skill '{name}'.", "path": str(target)}

    def remove_file(self, name: str, file_path: str, *, why: str = "") -> dict[str, Any]:
        err = validate_file_path(file_path)
        if err:
            return {"success": False, "error": err}
        d = self._find_skill_dir(name)
        if not d:
            return {"success": False, "error": f"Skill '{name}' not found."}
        target = d / file_path
        if not target.exists():
            available: list[str] = []
            for sub in ALLOWED_SUBDIRS:
                sd = d / sub
                if sd.exists():
                    for f in sd.rglob("*"):
                        if f.is_file():
                            available.append(str(f.relative_to(d)).replace("\\", "/"))
            return {"success": False, "error": f"File '{file_path}' not found.", "available_files": available or None}
        target.unlink()
        if target.parent != d and target.parent.exists() and not any(target.parent.iterdir()):
            target.parent.rmdir()
        self._append_changelog(d, action=f"remove_file:{file_path}", why=why)
        return {"success": True, "message": f"File '{file_path}' removed from skill '{name}'."}

    @staticmethod
    def dump_json(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

