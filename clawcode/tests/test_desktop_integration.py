"""Optional integration tests: real display and optional deps (skipped in headless CI)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_desktop_screenshot_real_display_optional(tmp_path: Path) -> None:
    pytest.importorskip("mss")
    pytest.importorskip("pyautogui")
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        pytest.skip("no DISPLAY/WAYLAND on Linux — GUI capture unavailable")

    from clawcode.config.settings import get_settings, load_settings
    from clawcode.llm.tools.desktop.desktop_utils import desktop_screenshot

    asyncio.run(load_settings(working_directory=str(tmp_path), debug=False))
    s = get_settings()
    s.desktop.enabled = True

    raw = desktop_screenshot()
    data = json.loads(raw)
    if not data.get("ok"):
        pytest.skip(
            "screenshot unavailable in this environment: "
            f"{data.get('error', data.get('message', raw))}"
        )
    path = data.get("screenshot_path")
    assert isinstance(path, str) and path.strip()
    assert Path(path).is_file()
