"""Unit tests for Code Awareness mapping, monitor, and session file-event state."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clawcode.config.settings import Settings
from clawcode.llm.base import ProviderResponse
from clawcode.tui.code_awareness.classifier import classify_architecture_map
from clawcode.tui.code_awareness.bfs_outline import build_bfs_outline
from clawcode.tui.code_awareness.mapping_store import (
    _MAX_EVENTS,
    load_architecture_map,
    map_file_path,
    save_architecture_map,
)
from clawcode.tui.code_awareness.monitor import ArchitectureAwarenessMonitor
from clawcode.tui.code_awareness.render import render_awareness
from clawcode.tui.code_awareness.scanner import classify_dir, classify_path, collect_all_paths
from clawcode.tui.code_awareness.state import (
    ArchLayer,
    ArchitectureMap,
    CodeAwarenessState,
    DirNode,
    FileChangeEvent,
    ProjectTree,
)
from clawcode.tui.code_awareness.widget import CodeAwarenessPanel


def _make_panel_without_textual_mount() -> CodeAwarenessPanel:
    """Build panel instance without running ScrollableContainer __init__."""
    panel = object.__new__(CodeAwarenessPanel)
    panel._state = CodeAwarenessState()
    panel._content = MagicMock()
    panel._accent = "#a8bbd6"
    panel._muted = "#7f8796"
    panel._highlight = "#a6e3a1"
    panel._read_highlight = "#7eb8da"
    return panel


def test_stage1_bfs_outline_covers_top_level_and_bounds_deeper_levels(tmp_path: Path) -> None:
    (tmp_path / "internal" / "domain").mkdir(parents=True)
    (tmp_path / "internal" / "app").mkdir(parents=True)
    (tmp_path / "internal" / "infra").mkdir(parents=True)
    (tmp_path / "gateway").mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)
    for i in range(10):
        (tmp_path / "internal" / "domain" / f"x{i}").mkdir(parents=True)

    outline = build_bfs_outline(
        str(tmp_path),
        max_depth=3,
        max_total_paths=20,
        max_children_per_dir=3,
    )
    top = outline["top_level_dirs"]
    assert "internal" in top
    assert "gateway" in top
    assert "docs" in top
    levels = outline["levels"]
    assert any(level["parent"] == "internal" for level in levels)
    domain_level = next(level for level in levels if level["parent"] == "internal/domain")
    assert len(domain_level["paths"]) == 3
    assert outline["stats"]["truncated"] is True


@pytest.mark.asyncio
async def test_classifier_falls_back_when_create_provider_fails() -> None:
    settings = Settings()

    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        side_effect=RuntimeError("no provider"),
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["docs", "internal"],
        )

    assert result.source == "fallback_rules"
    assert result.model_info.get("available") is False
    assert result.dir_to_layer["docs"] == classify_dir("docs").value
    assert result.dir_to_layer["internal"] == classify_dir("internal").value


@pytest.mark.asyncio
async def test_classifier_falls_back_on_invalid_llm_json() -> None:
    settings = Settings()

    class _BadProvider:
        def __init__(self) -> None:
            self.model = "mock"

        async def send_messages(self, messages, tools=None):
            return ProviderResponse(content="NOT JSON")

    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=_BadProvider(),
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["configs"],
        )

    assert result.source == "fallback_rules"
    assert result.dir_to_layer["configs"] == classify_dir("configs").value


@pytest.mark.asyncio
async def test_classifier_llm_success_strict_json() -> None:
    settings = Settings()

    class _GoodProvider:
        async def send_messages(self, messages, tools=None):
            payload = json.dumps({"dir_to_layer": {"src": "Core / Logic", "api": "API / Interface"}})
            return ProviderResponse(content=payload)

    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=_GoodProvider(),
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["src", "api"],
        )

    assert result.source == "llm"
    assert result.model_info.get("available") is True
    assert result.dir_to_layer["src"] == "Core / Logic"
    assert result.dir_to_layer["api"] == "API / Interface"


@pytest.mark.asyncio
async def test_classifier_accepts_project_specific_dynamic_layers() -> None:
    settings = Settings()

    class _DynamicProvider:
        async def send_messages(self, messages, tools=None):
            payload = json.dumps(
                {
                    "architecture_layers": [
                        {
                            "name": "Application",
                            "description": "入口与编排",
                            "directories": ["gateway", "cli"],
                        }
                    ],
                    "layer_descriptions": {"Application": "入口与编排"},
                    "dir_to_layer": {"gateway": "Application", "cli": "Application"},
                }
            )
            return ProviderResponse(content=payload)

    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=_DynamicProvider(),
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["gateway", "cli"],
        )

    assert result.source == "llm"
    assert result.dir_to_layer["gateway"] == "Application"
    assert "Application" in result.layers
    assert result.layer_descriptions.get("Application") == "入口与编排"
    assert "Application" in result.layer_order


@pytest.mark.asyncio
async def test_classifier_accepts_json_inside_markdown_codeblock() -> None:
    settings = Settings()

    class _WrappedProvider:
        async def send_messages(self, messages, tools=None):
            return ProviderResponse(
                content=(
                    "结果如下：\n```json\n"
                    '{"dir_to_layer":{"src":"Core / Logic"}}\n'
                    "```"
                )
            )

    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=_WrappedProvider(),
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["src"],
        )

    assert result.source == "llm"
    assert result.dir_to_layer["src"] == "Core / Logic"


@pytest.mark.asyncio
async def test_classifier_retries_once_after_parse_failure() -> None:
    settings = Settings()

    class _RetryProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def send_messages(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return ProviderResponse(content="not-json")
            return ProviderResponse(content='{"dir_to_layer":{"src":"Core / Logic"}}')

    provider = _RetryProvider()
    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=provider,
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["src"],
        )

    # Two-stage mode may introduce additional calls (stage-1 + stage-2).
    assert provider.calls >= 2
    assert result.source == "llm"
    assert result.dir_to_layer["src"] == "Core / Logic"


@pytest.mark.asyncio
async def test_classifier_two_stage_prompt_flow_works() -> None:
    settings = Settings()

    class _TwoStageProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def send_messages(self, messages, tools=None):
            self.calls += 1
            user_prompt = str(messages[-1]["content"])
            if "Do not output directory-to-layer mapping in this step." in user_prompt:
                return ProviderResponse(
                    content=json.dumps(
                        {
                            "architecture_layers": [
                                {"name": "Application", "description": "入口与编排"},
                                {"name": "Core Agent", "description": "推理与主循环"},
                            ],
                            "layer_order": ["Application", "Core Agent"],
                        }
                    )
                )
            return ProviderResponse(
                content=json.dumps(
                    {
                        "dir_to_layer": {
                            "gateway": "Application",
                            "agent": "Core Agent",
                        }
                    }
                )
            )

    provider = _TwoStageProvider()
    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=provider,
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["gateway", "agent"],
        )

    assert result.source == "llm"
    assert result.model_info.get("two_stage") is True
    assert result.dir_to_layer["gateway"] == "Application"
    assert result.dir_to_layer["agent"] == "Core Agent"
    assert result.layer_order[:2] == ["Application", "Core Agent"]
    assert result.layer_descriptions.get("Application") == "入口与编排"


@pytest.mark.asyncio
async def test_classifier_stage1_prompt_contains_readme_and_bfs_outline() -> None:
    settings = Settings()

    class _InspectProvider:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        async def send_messages(self, messages, tools=None):
            user_prompt = str(messages[-1]["content"])
            self.prompts.append(user_prompt)
            if "Do not output directory-to-layer mapping in this step." in user_prompt:
                return ProviderResponse(
                    content=json.dumps(
                        {
                            "architecture_layers": [
                                {"name": "Application", "description": "入口"}
                            ],
                            "layer_order": ["Application"],
                        }
                    )
                )
            return ProviderResponse(
                content=json.dumps(
                    {"dir_to_layer": {"gateway": "Application", "internal": "Application"}}
                )
            )

    provider = _InspectProvider()
    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=provider,
    ), patch(
        "clawcode.tui.code_awareness.classifier.build_bfs_outline",
        return_value={
            "top_level_dirs": ["gateway", "internal"],
            "levels": [{"depth": 1, "parent": "internal", "paths": ["internal/domain"]}],
            "stats": {"truncated": False},
        },
    ), patch(
        "clawcode.tui.code_awareness.classifier.read_readme_snippet",
        return_value="Project for telemetry pipeline.",
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["gateway", "internal"],
        )

    assert result.source == "llm"
    stats = result.model_info.get("stage1_outline_stats")
    assert isinstance(stats, dict)
    assert stats.get("truncated") is False
    stage1_prompt = next(
        p for p in provider.prompts if "Do not output directory-to-layer mapping in this step." in p
    )
    assert "Project context (README snippet):" in stage1_prompt
    assert "Project for telemetry pipeline." in stage1_prompt
    assert '"top_level_dirs": ["gateway", "internal"]' in stage1_prompt


@pytest.mark.asyncio
async def test_classifier_fallback_keeps_error_details_in_model_info() -> None:
    settings = Settings()

    class _BadProvider:
        async def send_messages(self, messages, tools=None):
            return ProviderResponse(content="")

    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=_BadProvider(),
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=["foo"],
        )

    assert result.source == "fallback_rules"
    assert isinstance(result.model_info.get("error"), str)
    assert result.model_info.get("error")


@pytest.mark.asyncio
async def test_classifier_uses_partial_fallback_for_truncated_batch() -> None:
    settings = Settings()

    class _BatchProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def send_messages(self, messages, tools=None):
            self.calls += 1
            # First batch fails both attempts -> fallback for that batch.
            if self.calls <= 2:
                return ProviderResponse(content='{"dir_to_layer":{"src":"Core / Logic"}')
            # Second batch succeeds.
            return ProviderResponse(content='{"dir_to_layer":{"x120":"API / Interface"}}')

    provider = _BatchProvider()
    dirs = ["src", "api"] + [f"x{i}" for i in range(130)]  # trigger >= 2 batches
    with patch(
        "clawcode.tui.code_awareness.classifier.create_provider",
        return_value=provider,
    ):
        result = await classify_architecture_map(
            working_directory="/tmp/proj",
            settings=settings,
            directories=dirs,
        )

    assert result.source in {"llm", "fallback_rules"}
    assert isinstance(result.model_info, dict)
    # Truncated responses should not crash; mapping is still produced.
    assert "x120" in result.dir_to_layer


@pytest.mark.asyncio
async def test_monitor_refresh_mapping_again_when_directory_structure_changes(
    tmp_path: Path,
) -> None:
    settings = Settings()
    refresh = AsyncMock()

    snap_calls: list[tuple[set[str], dict[str, int]]] = [
        (set(), {}),
        ({"newdir"}, {}),
    ]

    def _next_snap() -> tuple[set[str], dict[str, int]]:
        if snap_calls:
            return snap_calls.pop(0)
        return ({"newdir"}, {})

    on_map = MagicMock()
    on_ev = MagicMock()

    mon = ArchitectureAwarenessMonitor(
        working_directory=str(tmp_path),
        settings=settings,
        on_mapping=on_map,
        on_file_event=on_ev,
    )
    mon._refresh_mapping = refresh
    mon._snapshot_fs = _next_snap
    mon._current_interval = lambda: 0.01

    mon.start()
    try:
        await asyncio.sleep(0.16)
    finally:
        await mon.stop()

    assert refresh.await_count >= 2
    first = refresh.await_args_list[0]
    assert first.kwargs.get("force") is True


@pytest.mark.asyncio
async def test_monitor_refresh_passes_scanned_tree_to_on_mapping(tmp_path: Path) -> None:
    """Regression: panel must receive a fresh ProjectTree when the map refreshes."""
    (tmp_path / "internal" / "tools" / "CLI").mkdir(parents=True)
    settings = Settings()
    on_map = MagicMock()
    on_ev = MagicMock()
    mon = ArchitectureAwarenessMonitor(
        working_directory=str(tmp_path),
        settings=settings,
        on_mapping=on_map,
        on_file_event=on_ev,
    )
    with patch(
        "clawcode.tui.code_awareness.monitor.classify_architecture_map",
        new_callable=AsyncMock,
    ) as clf:

        async def _fake_classify(*, directories: list[str], **_: object) -> ArchitectureMap:
            dtl = {d: "Core / Logic" for d in directories}
            return ArchitectureMap(
                project_root=str(tmp_path),
                source="fallback_rules",
                model_info={"available": False},
                dir_to_layer=dtl,
                layers={"Core / Logic": list(directories)},
            )

        clf.side_effect = _fake_classify
        await mon._refresh_mapping(force=True)

    assert on_map.call_count == 1
    mapping, tree = on_map.call_args[0]
    assert isinstance(mapping, ArchitectureMap)
    assert isinstance(tree, ProjectTree)
    assert "internal/tools/CLI" in collect_all_paths(tree)


def test_render_shows_mapped_empty_branch_when_sibling_path_modified() -> None:
    """Empty new dirs under a mapped path stay visible even if edits are elsewhere."""
    cli = DirNode(
        name="CLI",
        rel_path="internal/tools/CLI",
        is_dir=True,
        children=[],
        layer=ArchLayer.CORE,
    )
    tools = DirNode(
        name="tools",
        rel_path="internal/tools",
        is_dir=True,
        children=[cli],
        layer=ArchLayer.CORE,
    )
    internal = DirNode(
        name="internal",
        rel_path="internal",
        is_dir=True,
        children=[tools],
        layer=ArchLayer.CORE,
    )
    state = CodeAwarenessState(
        tree=ProjectTree(root_name="p", root_path="/p", nodes=[internal]),
        modified_files={"internal/foo.txt"},
    )
    state.architecture_map = ArchitectureMap(
        project_root="/p",
        source="llm",
        dir_to_layer={
            "internal": "App",
            "internal/tools": "App",
            "internal/tools/CLI": "App",
        },
        layers={"App": ["internal/tools/CLI"]},
        layer_order=["App"],
    )
    text = render_awareness(state)
    assert "CLI" in text.plain


@pytest.mark.asyncio
async def test_monitor_retries_classification_while_stuck_in_fallback(
    tmp_path: Path,
) -> None:
    settings = Settings()
    on_map = MagicMock()
    on_ev = MagicMock()
    mon = ArchitectureAwarenessMonitor(
        working_directory=str(tmp_path),
        settings=settings,
        on_mapping=on_map,
        on_file_event=on_ev,
    )

    calls = 0

    async def _fake_refresh(*, force: bool = False) -> None:
        nonlocal calls
        calls += 1
        mon._current_map = ArchitectureMap(
            project_root=str(tmp_path),
            source="fallback_rules",
            model_info={"available": True},
            dir_to_layer={},
            layers={},
        )

    mon._refresh_mapping = _fake_refresh  # type: ignore[assignment]
    mon._snapshot_fs = lambda: (set(), {})  # type: ignore[assignment]
    mon._current_interval = lambda: 0.01  # type: ignore[assignment]

    mon.start()
    try:
        await asyncio.sleep(0.06)
    finally:
        await mon.stop()

    assert calls >= 2


def test_mapping_store_roundtrip_caps_file_events(tmp_path: Path) -> None:
    events = [
        FileChangeEvent(float(i), f"p{i}", "d", "Other", "modified") for i in range(_MAX_EVENTS + 50)
    ]
    mapping = ArchitectureMap(
        project_root=str(tmp_path),
        dir_to_layer={"a": "Other"},
        layers={"Other": ["a"]},
        file_events=events,
    )
    save_architecture_map(str(tmp_path), mapping)
    loaded = load_architecture_map(str(tmp_path))
    assert loaded is not None
    assert len(loaded.file_events) == _MAX_EVENTS
    raw = json.loads(map_file_path(str(tmp_path)).read_text(encoding="utf-8"))
    assert len(raw["file_events"]) == _MAX_EVENTS


@pytest.mark.asyncio
async def test_monitor_handle_event_keeps_at_most_200_file_events(tmp_path: Path) -> None:
    settings = Settings()
    on_map = MagicMock()
    on_ev = MagicMock()

    mon = ArchitectureAwarenessMonitor(
        working_directory=str(tmp_path),
        settings=settings,
        on_mapping=on_map,
        on_file_event=on_ev,
    )
    mon._current_map = ArchitectureMap(project_root=str(tmp_path))
    mon._current_map.file_events = [
        FileChangeEvent(0.0, f"old{i}.txt", "", "Other") for i in range(199)
    ]
    mon._dir_snapshot = set()

    with patch("clawcode.tui.code_awareness.monitor.save_architecture_map"):
        f = tmp_path / "touch.txt"
        f.write_text("x", encoding="utf-8")
        await mon._handle_event(str(f))

    assert len(mon._current_map.file_events) == 200


def test_widget_file_events_session_archive_and_restore() -> None:
    panel = _make_panel_without_textual_mount()
    ev_a = FileChangeEvent(1.0, "src/a.go", "src", "Core / Logic")
    CodeAwarenessPanel.add_file_event(panel, ev_a)
    assert len(panel._state.file_events) == 1

    old_sid = "sess-old"
    panel._state.session_file_events[old_sid] = list(panel._state.file_events)
    CodeAwarenessPanel.clear_session(panel)
    assert panel._state.file_events == []

    new_sid = "sess-new"
    CodeAwarenessPanel.set_file_events(panel, panel._state.session_file_events.get(new_sid, []))
    assert panel._state.file_events == []

    CodeAwarenessPanel.set_file_events(panel, panel._state.session_file_events.get(old_sid, []))
    assert len(panel._state.file_events) == 1
    assert panel._state.file_events[0].path == "src/a.go"


def test_widget_add_file_event_truncates_to_120() -> None:
    panel = _make_panel_without_textual_mount()
    for i in range(130):
        CodeAwarenessPanel.add_file_event(
            panel,
            FileChangeEvent(float(i), f"f{i}.txt", "d", "Other"),
        )
    assert len(panel._state.file_events) == 120
    assert panel._state.file_events[-1].path == "f129.txt"


def test_fallback_classify_path_typical_main_dirs_are_core() -> None:
    assert classify_path("agent") == classify_dir("core")
    assert classify_path("gateway") == classify_dir("core")
    assert classify_path("project_cli") == classify_dir("core")


def test_fallback_classify_path_unknown_top_level_defaults_to_core() -> None:
    assert classify_path("foo_bar") == classify_dir("core")


def test_fallback_classify_path_unknown_nested_keeps_other() -> None:
    assert classify_path("vendor/unknown") == classify_dir("other")


def test_fallback_classify_path_existing_known_layers_unchanged() -> None:
    assert classify_path("tests") == classify_dir("tests")
    assert classify_path("docs") == classify_dir("docs")
    assert classify_path("assets") == classify_dir("assets")


def test_render_uses_mapped_descendant_layer_for_top_level_group() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="proj",
            root_path="/tmp/proj",
            nodes=[
                DirNode(
                    name="foo",
                    rel_path="foo",
                    is_dir=True,
                    children=[
                        DirNode(
                            name="api",
                            rel_path="foo/api",
                            is_dir=True,
                            layer=ArchLayer.OTHER,
                        )
                    ],
                    layer=ArchLayer.OTHER,
                )
            ],
        )
    )
    state.architecture_map = ArchitectureMap(
        project_root="/tmp/proj",
        source="llm",
        dir_to_layer={"foo/api": "API / Interface"},
        layers={"API / Interface": ["foo/api"]},
    )
    text = render_awareness(state)
    plain = text.plain
    assert "◆ API / Interface" in plain
    assert "◆ Other" not in plain


def test_render_dynamic_layer_header_with_description() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="proj",
            root_path="/tmp/proj",
            nodes=[
                DirNode(
                    name="gateway",
                    rel_path="gateway",
                    is_dir=True,
                    layer=ArchLayer.OTHER,
                )
            ],
        )
    )
    state.architecture_map = ArchitectureMap(
        project_root="/tmp/proj",
        source="llm",
        dir_to_layer={"gateway": "Application"},
        layers={"Application": ["gateway"]},
        layer_descriptions={"Application": "入口与编排"},
        layer_order=["Application"],
    )
    text = render_awareness(state)
    plain = text.plain
    assert "◆ Application (入口与编排)" in plain


def test_render_shows_modification_and_read_sequence_labels() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="proj",
            root_path="/tmp/proj",
            nodes=[
                DirNode(
                    name="internal",
                    rel_path="internal",
                    is_dir=True,
                    files=["a.py", "b.py"],
                    layer=ArchLayer.CORE,
                )
            ],
        ),
        modified_files={"internal/a.py"},
        read_files={"internal/a.py", "internal/b.py"},
        modification_events=["internal/a.py"],
        read_events=["internal/b.py", "internal/a.py"],
    )
    text = render_awareness(state)
    plain = text.plain
    assert "internal/" in plain
    assert "#1" in plain
    assert "R2" in plain
    assert "R1" in plain


def test_widget_updates_latest_sequence_for_repeated_marks() -> None:
    panel = _make_panel_without_textual_mount()
    CodeAwarenessPanel.mark_file_modified(panel, "src/a.py")
    CodeAwarenessPanel.mark_file_modified(panel, "src/b.py")
    CodeAwarenessPanel.mark_file_modified(panel, "src/a.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/a.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/c.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/a.py")

    assert panel._state.modification_events[-1] == "src/a.py"
    assert panel._state.read_events[-1] == "src/a.py"
    assert "src/a.py" in panel._state.modified_files
    assert "src/a.py" in panel._state.read_files

    state = panel._state
    state.tree = ProjectTree(
        root_name="proj",
        root_path="/tmp/proj",
        nodes=[
            DirNode(
                name="src",
                rel_path="src",
                is_dir=True,
                files=["a.py", "b.py", "c.py"],
                layer=ArchLayer.CORE,
            )
        ],
    )
    text = render_awareness(state)
    plain = text.plain
    assert "#3" in plain
    assert "R3" in plain


def test_render_keeps_read_highlight_when_read_events_empty() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="proj",
            root_path="/tmp/proj",
            nodes=[
                DirNode(
                    name="src",
                    rel_path="src",
                    is_dir=True,
                    files=["a.py"],
                    layer=ArchLayer.CORE,
                )
            ],
        ),
        read_files={"src/a.py"},
        read_events=[],
    )
    text = render_awareness(state)
    plain = text.plain
    assert "◇ a.py" in plain
    assert "R0" not in plain


def test_render_tree_connectors_use_visible_children_only() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="proj",
            root_path="/tmp/proj",
            nodes=[
                DirNode(
                    name="src",
                    rel_path="src",
                    is_dir=True,
                    children=[
                        DirNode(name="hidden", rel_path="src/hidden", is_dir=True, files=["x.py"]),
                        DirNode(name="shown", rel_path="src/shown", is_dir=True, files=["y.py"]),
                    ],
                    files=["root.py"],
                    layer=ArchLayer.CORE,
                )
            ],
        ),
        modified_files={"src/shown/y.py"},
    )
    text = render_awareness(state)
    plain = text.plain
    assert "└─ shown/" in plain
    assert "hidden/" not in plain
    assert "root.py" not in plain


def test_widget_restore_session_file_marks_keeps_read_files_and_events() -> None:
    panel = _make_panel_without_textual_mount()
    CodeAwarenessPanel.restore_session_file_marks(
        panel,
        modified_files={"src/a.py"},
        read_files={"src/a.py", "src/b.py"},
        modification_events=["src/a.py"],
        read_events=["src/b.py", "src/a.py"],
    )
    assert panel._state.modified_files == {"src/a.py"}
    assert panel._state.read_files == {"src/a.py", "src/b.py"}
    assert panel._state.modification_events == ["src/a.py"]
    assert panel._state.read_events == ["src/b.py", "src/a.py"]


def test_render_observability_audit_line_marks_and_stage1_stats() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="p",
            root_path="/p",
            nodes=[DirNode(name="x", rel_path="x", is_dir=True, layer=ArchLayer.CORE)],
        ),
        modified_files={"x/f.py"},
        modification_events=["x/f.py", "x/g.py"],
        read_files={"x/g.py"},
        read_events=["x/g.py"],
    )
    state.architecture_map = ArchitectureMap(
        project_root="/p",
        source="llm",
        dir_to_layer={"x": "Core / Logic"},
        layers={"Core / Logic": ["x"]},
        model_info={
            "stage1_outline_stats": {"truncated": True, "sampled_paths": 42},
        },
    )
    text = render_awareness(state)
    plain = text.plain
    assert "■ 1/2" in plain
    assert "◇ 1/1" in plain
    assert "S1 n=42,trunc" in plain


def test_widget_archive_current_turn_then_reset_marks() -> None:
    panel = _make_panel_without_textual_mount()
    panel._state.active_session_id = "s1"
    CodeAwarenessPanel.mark_file_modified(panel, "src/a.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/a.py")
    CodeAwarenessPanel.archive_current_turn(panel, query="how works", session_id="s1")

    history = CodeAwarenessPanel.get_session_history(panel, "s1")
    assert len(history) == 1
    assert history[0].query == "how works"
    assert history[0].modification_events == ["src/a.py"]
    assert history[0].read_events == ["src/a.py"]

    CodeAwarenessPanel.reset_current_marks(panel)
    assert panel._state.modified_files == set()
    assert panel._state.read_files == set()
    assert panel._state.modification_events == []
    assert panel._state.read_events == []


def test_widget_history_isolated_per_session() -> None:
    panel = _make_panel_without_textual_mount()
    CodeAwarenessPanel.mark_file_modified(panel, "src/a.py")
    CodeAwarenessPanel.archive_current_turn(panel, query="q1", session_id="s1")
    CodeAwarenessPanel.reset_current_marks(panel)

    CodeAwarenessPanel.mark_file_read(panel, "src/b.py")
    CodeAwarenessPanel.archive_current_turn(panel, query="q2", session_id="s2")

    h1 = CodeAwarenessPanel.get_session_history(panel, "s1")
    h2 = CodeAwarenessPanel.get_session_history(panel, "s2")
    assert len(h1) == 1
    assert len(h2) == 1
    assert h1[0].query == "q1"
    assert h2[0].query == "q2"


def test_render_shows_history_block_for_active_session() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="p",
            root_path="/p",
            nodes=[DirNode(name="src", rel_path="src", is_dir=True, layer=ArchLayer.CORE)],
        ),
        active_session_id="s1",
    )
    panel = _make_panel_without_textual_mount()
    panel._state = state
    CodeAwarenessPanel.mark_file_modified(panel, "src/a.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/b.py")
    CodeAwarenessPanel.archive_current_turn(panel, query="analyze internals", session_id="s1")
    CodeAwarenessPanel.reset_current_marks(panel)

    text = render_awareness(panel._state)
    plain = text.plain
    assert "◆ History" in plain
    assert "Q1: analyze internals" in plain
    assert "W: a.py" in plain
    assert "R: b.py" in plain


def test_widget_toggle_history_expanded() -> None:
    panel = _make_panel_without_textual_mount()
    assert panel._state.history_expanded is False
    assert CodeAwarenessPanel.toggle_history_expanded(panel) is True
    assert panel._state.history_expanded is True
    assert CodeAwarenessPanel.toggle_history_expanded(panel) is False
    assert panel._state.history_expanded is False


def test_render_history_full_mode_shows_complete_sequences() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="p",
            root_path="/p",
            nodes=[DirNode(name="src", rel_path="src", is_dir=True, layer=ArchLayer.CORE)],
        ),
        active_session_id="s1",
        history_expanded=True,
    )
    panel = _make_panel_without_textual_mount()
    panel._state = state
    CodeAwarenessPanel.mark_file_modified(panel, "src/a.py")
    CodeAwarenessPanel.mark_file_modified(panel, "src/b.py")
    CodeAwarenessPanel.mark_file_modified(panel, "src/c.py")
    CodeAwarenessPanel.mark_file_modified(panel, "src/d.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/r1.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/r2.py")
    CodeAwarenessPanel.archive_current_turn(panel, query="trace", session_id="s1")
    CodeAwarenessPanel.reset_current_marks(panel)

    text = render_awareness(panel._state)
    plain = text.plain
    assert "◆ History [full]" in plain
    assert "W: a.py -> b.py -> c.py -> d.py" in plain
    assert "R: r1.py -> r2.py" in plain


def test_widget_history_expand_state_persists_per_session() -> None:
    panel = _make_panel_without_textual_mount()

    CodeAwarenessPanel.set_active_session(panel, "s1")
    assert panel._state.history_expanded is False
    assert CodeAwarenessPanel.toggle_history_expanded(panel) is True

    CodeAwarenessPanel.set_active_session(panel, "s2")
    assert panel._state.history_expanded is False


def test_history_hotkey_hint_shows_once_for_new_session() -> None:
    panel = _make_panel_without_textual_mount()
    panel._state.tree = ProjectTree(
        root_name="p",
        root_path="/p",
        nodes=[DirNode(name="src", rel_path="src", is_dir=True, layer=ArchLayer.CORE)],
    )
    from clawcode.tui.code_awareness.state import HistoryRecord

    panel._state.session_history_records["s1"] = [
        HistoryRecord(turn_id=1, query="q", created_at=0.0, modification_events=["src/a.py"])
    ]

    CodeAwarenessPanel.set_active_session(panel, "s1")
    first_render = panel._content.update.call_args[0][0].plain
    assert "Ops: [Y] history(summary)" in first_render
    assert "◆ History [summary]" in first_render

    # Next refresh in same session keeps ops visible (discoverable, non-once hint).
    text_second = render_awareness(panel._state).plain
    assert "Ops: [Y] history(summary)" in text_second


def test_render_shows_history_ops_even_without_archived_turns() -> None:
    state = CodeAwarenessState(
        tree=ProjectTree(
            root_name="p",
            root_path="/p",
            nodes=[DirNode(name="src", rel_path="src", is_dir=True, layer=ArchLayer.CORE)],
        ),
        active_session_id="s1",
    )
    text = render_awareness(state).plain
    assert "Ops: [Y] history(summary)" in text
    assert "◆ History [summary]" in text
    assert "(no archived turns)" in text


def test_widget_debounce_merges_multiple_mark_refreshes() -> None:
    panel = _make_panel_without_textual_mount()
    panel._refresh_scheduled = False
    panel._refresh_debounce_s = 0.1
    panel._force_debounce_for_tests = True
    refresh_calls = {"count": 0}
    scheduled_callbacks: list = []

    def _fake_refresh() -> None:
        refresh_calls["count"] += 1

    def _fake_timer(_delay: float, cb):
        scheduled_callbacks.append(cb)

    panel._refresh_content = _fake_refresh
    panel.set_timer = _fake_timer

    CodeAwarenessPanel.mark_file_modified(panel, "src/a.py")
    CodeAwarenessPanel.mark_file_read(panel, "src/b.py")

    assert refresh_calls["count"] == 0
    assert len(scheduled_callbacks) == 1

    scheduled_callbacks[0]()
    assert refresh_calls["count"] == 1
