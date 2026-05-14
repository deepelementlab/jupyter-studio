from __future__ import annotations

import json
from pathlib import Path

from clawcode.llm.plan_policy import filter_read_only_tools, is_tool_allowed_in_plan_mode
from clawcode.llm.plan_store import (
    PlanBundle,
    PlanExecutionState,
    PlanStore,
    PlanTaskItem,
)


def test_plan_policy_blocks_write_like_bash() -> None:
    ok, reason = is_tool_allowed_in_plan_mode("bash", {"command": "echo hi > out.txt"})
    assert ok is False
    assert reason


def test_plan_policy_allows_readonly_tools() -> None:
    ok, reason = is_tool_allowed_in_plan_mode("grep", {"pattern": "foo"})
    assert ok is True
    assert reason is None

    kept = filter_read_only_tools(["view", "write", "grep", "Agent"])
    assert kept == ["view", "grep"]


def test_plan_store_save_and_load(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    artifact = store.save("sess_12345678", "need plan", "# Plan\n\n- item")
    assert Path(artifact.file_path).exists()
    assert ".claw" in artifact.file_path.replace("\\", "/")
    loaded = store.load_markdown(artifact.file_path)
    assert "# Plan" in loaded


def test_plan_store_load_fallback_from_claude(tmp_path: Path) -> None:
    legacy = tmp_path / ".claude" / "plans"
    legacy.mkdir(parents=True)
    f = legacy / "legacy.md"
    f.write_text("# Legacy Plan", encoding="utf-8")

    store = PlanStore(str(tmp_path))
    loaded = store.load_markdown(str(tmp_path / ".missing" / "legacy.md"))
    assert "Legacy Plan" in loaded


def test_plan_store_save_and_load_bundle(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    bundle = store.save_bundle(
        session_id="sess_1",
        user_request="do x",
        plan_text="# Plan\n- one",
        tasks=[PlanTaskItem(id="task-1", title="one")],
    )
    loaded = store.load_plan_bundle(bundle.markdown_path)
    assert loaded is not None
    assert loaded.tasks
    assert loaded.tasks[0].title == "one"


def test_plan_store_save_bundle_versioned_iterates_name(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    first = store.save_bundle_versioned(
        session_id="sess_2",
        user_request="build api auth",
        plan_text="# Plan\n- first",
        tasks=[PlanTaskItem(id="task-1", title="first")],
        subdir="multi-plan",
        base_name="api-auth",
    )
    second = store.save_bundle_versioned(
        session_id="sess_2",
        user_request="build api auth",
        plan_text="# Plan\n- second",
        tasks=[PlanTaskItem(id="task-1", title="second")],
        subdir="multi-plan",
        base_name="api-auth",
    )
    p1 = Path(first.markdown_path)
    p2 = Path(second.markdown_path)
    assert p1.exists()
    assert p2.exists()
    assert p1.parent.name == "multi-plan"
    assert p2.parent.name == "multi-plan"
    assert p1.name == "api-auth.md"
    assert p2.name == "api-auth-v2.md"


def test_find_latest_bundle_for_session_in_subdir(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    a = store.save_bundle_versioned(
        session_id="sess_mp",
        user_request="r1",
        plan_text="# A",
        tasks=[PlanTaskItem(id="task-1", title="a")],
        subdir="multi-plan",
        base_name="feature-x",
    )
    _ = store.save_bundle_versioned(
        session_id="sess_other",
        user_request="r2",
        plan_text="# B",
        tasks=[PlanTaskItem(id="task-1", title="b")],
        subdir="multi-plan",
        base_name="feature-y",
    )
    b = store.save_bundle_versioned(
        session_id="sess_mp",
        user_request="r3",
        plan_text="# C",
        tasks=[PlanTaskItem(id="task-1", title="c")],
        subdir="multi-plan",
        base_name="feature-x",
    )
    found = store.find_latest_bundle_for_session_in_subdir("sess_mp", "multi-plan")
    assert found is not None
    assert Path(found.markdown_path).name == Path(b.markdown_path).name
    assert Path(found.markdown_path).name != Path(a.markdown_path).name


def test_list_bundles_in_subdir_desc(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    one = store.save_bundle_versioned(
        session_id="sess_1",
        user_request="r1",
        plan_text="# one",
        tasks=[PlanTaskItem(id="task-1", title="one")],
        subdir="multi-plan",
        base_name="f1",
    )
    two = store.save_bundle_versioned(
        session_id="sess_2",
        user_request="r2",
        plan_text="# two",
        tasks=[PlanTaskItem(id="task-1", title="two")],
        subdir="multi-plan",
        base_name="f2",
    )
    rows = store.list_bundles_in_subdir("multi-plan", limit=10)
    assert len(rows) >= 2
    names = [Path(x.markdown_path).name for x in rows]
    assert Path(two.markdown_path).name in names
    assert Path(one.markdown_path).name in names


def _write_plan_json(plans_dir: Path, name: str, payload: dict) -> None:
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_find_latest_bundle_for_session_picks_highest_created_at(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    sid = "sess_aaaaaaaaaaaaaaaa"
    plans_dir = store._plans_dir
    base = {
        "session_id": sid,
        "user_request": "u",
        "plan_text": "# P",
        "markdown_path": str(tmp_path / "a.md"),
        "json_path": "",
        "tasks": [{"id": "1", "title": "t", "status": "pending", "details": "", "result_summary": ""}],
        "execution": {},
    }
    _write_plan_json(plans_dir, "plan-old.json", {**base, "created_at": 100})
    _write_plan_json(plans_dir, "plan-new.json", {**base, "created_at": 200})
    found = store.find_latest_bundle_for_session(sid)
    assert found is not None
    assert found.created_at == 200


def test_find_latest_bundle_for_session_ignores_meta_only_json(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    sid = "sess_bbbbbbbbbbbbbbbb"
    plans_dir = store._plans_dir
    _write_plan_json(
        plans_dir,
        "plan-meta.json",
        {
            "session_id": sid,
            "user_request": "u",
            "created_at": 300,
            "markdown_file": "x.md",
        },
    )
    assert store.find_latest_bundle_for_session(sid) is None


def test_normalize_stale_build_after_restart_clears_building_and_in_progress(tmp_path: Path) -> None:
    store = PlanStore(str(tmp_path))
    bundle = PlanBundle(
        session_id="sess_c",
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path=str(tmp_path / "p.md"),
        json_path=str(store._plans_dir / "plan-c.json"),
        tasks=[
            PlanTaskItem(id="1", title="a", status="completed"),
            PlanTaskItem(id="2", title="b", status="in_progress"),
        ],
        execution=PlanExecutionState(
            is_building=True,
            current_task_index=1,
            started_at=10,
        ),
    )
    assert store.normalize_stale_build_after_restart(bundle) is True
    assert bundle.execution.is_building is False
    assert bundle.execution.current_task_index == -1
    assert bundle.tasks[1].status == "pending"


def test_normalize_stale_build_after_restart_noop_when_idle() -> None:
    bundle = PlanBundle(
        session_id="sess_d",
        user_request="u",
        plan_text="# P",
        created_at=1,
        markdown_path="m.md",
        json_path="j.json",
        tasks=[PlanTaskItem(id="1", title="a", status="completed")],
        execution=PlanExecutionState(is_building=False, current_task_index=-1),
    )
    assert PlanStore.normalize_stale_build_after_restart(bundle) is False

