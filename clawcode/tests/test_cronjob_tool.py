from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def ctx(tmp_path: Path):
    from clawcode.llm.tools.base import ToolContext

    return ToolContext(
        session_id="sess_cronjob",
        message_id="msg_1",
        working_directory=str(tmp_path),
        permission_service=None,
        plan_mode=False,
    )


@pytest.mark.asyncio
async def test_cronjob_schedule_poll_shell_success(ctx, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall
    from clawcode.llm.tools.cronjob import create_cronjob_tool

    tool = create_cronjob_tool(permissions=None)
    sched = await tool.run(
        ToolCall(
            id="tc_cron_sched_1",
            name="cronjob",
            input={
                "action": "schedule",
                "kind": "shell",
                "code": "echo cronhello_execute",
                "interval_s": 0.15,
                "timeout_s": 3,
                "max_runs": 1,
            },
        ),
        ctx,
    )
    assert sched.is_error is False
    data = json.loads(sched.content)
    assert data["success"] is True
    job_id = data["job_id"]

    # Wait for the first run to finish.
    pdata = {}
    for _ in range(20):
        poll = await tool.run(
            ToolCall(
                id=f"tc_cron_poll_1_{_}",
                name="cronjob",
                input={"action": "poll", "job_id": job_id},
            ),
            ctx,
        )
        assert poll.is_error is False
        pdata = json.loads(poll.content)
        assert pdata["success"] is True
        runs = pdata.get("runs") or []
        if runs and (runs[-1].get("done") is True):
            latest = runs[-1]
            break
        await asyncio.sleep(0.1)
    else:
        latest = {}

    runs = pdata.get("runs") or []
    assert len(runs) >= 1
    assert latest.get("done") is True

    result = latest.get("result") or {}
    assert result.get("success") is True
    assert "cronhello_execute" in (result.get("stdout") or "")


@pytest.mark.asyncio
async def test_cronjob_stop_prevents_more_runs(ctx, tmp_path: Path) -> None:
    from clawcode.llm.tools.base import ToolCall
    from clawcode.llm.tools.cronjob import create_cronjob_tool

    tool = create_cronjob_tool(permissions=None)
    sched = await tool.run(
        ToolCall(
            id="tc_cron_sched_2",
            name="cronjob",
            input={
                "action": "schedule",
                "kind": "shell",
                "code": "echo stoptest_cronjob",
                "interval_s": 0.3,
                "timeout_s": 3,
                "max_runs": 5,
            },
        ),
        ctx,
    )
    assert sched.is_error is False
    job_id = json.loads(sched.content)["job_id"]

    # Wait until at least one run completes.
    for _ in range(20):
        poll = await tool.run(
            ToolCall(
                id=f"tc_cron_poll_wait_{_}",
                name="cronjob",
                input={"action": "poll", "job_id": job_id},
            ),
            ctx,
        )
        pdata = json.loads(poll.content)
        runs = pdata.get("runs") or []
        if runs and runs[-1].get("done") is True:
            break
        await asyncio.sleep(0.1)

    stop = await tool.run(
        ToolCall(id="tc_cron_stop_1", name="cronjob", input={"action": "stop", "job_id": job_id}),
        ctx,
    )
    assert stop.is_error is False
    sp = json.loads(stop.content)
    assert sp["success"] is True

    poll_after = await tool.run(
        ToolCall(id="tc_cron_poll_after_1", name="cronjob", input={"action": "poll", "job_id": job_id}),
        ctx,
    )
    pdata_after = json.loads(poll_after.content)
    count_at_stop = len(pdata_after.get("runs") or [])

    await asyncio.sleep(0.45)

    poll_later = await tool.run(
        ToolCall(id="tc_cron_poll_later_1", name="cronjob", input={"action": "poll", "job_id": job_id}),
        ctx,
    )
    pdata_later = json.loads(poll_later.content)
    count_later = len(pdata_later.get("runs") or [])

    assert count_later == count_at_stop

