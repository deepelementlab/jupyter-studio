"""Claw mode agent — dedicated Claw execution branch on the clawcode stack.

This module provides :class:`ClawAgent`, a subclass of :class:`~clawcode.llm.agent.Agent`
with an explicit :meth:`~ClawAgent.run_claw_turn` (alias :meth:`~ClawAgent.run_claw_conversation`) entrypoint used when the TUI enables
``/claw`` routing. The loop is the same async ReAct implementation as the default coder
agent; tooling and providers remain fully localized to clawcode.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .agent import Agent, AgentEvent
from .claw_support.iteration_budget import IterationBudget


class ClawAgent(Agent):
    """Coder :class:`Agent` with a dedicated Claw-mode entrypoint.

    The typical agent ``run_conversation`` pattern maps conceptually to this class plus
    :meth:`run_claw_turn` — multi-turn tool use until the assistant finishes without
    further tool calls. :attr:`claw_iteration_budget` mirrors
    ``IterationBudget`` for future subagent / refund use.
    """

    def __init__(
        self,
        *args: Any,
        claw_iteration_budget: IterationBudget | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.claw_iteration_budget: IterationBudget = (
            claw_iteration_budget
            if claw_iteration_budget is not None
            else IterationBudget(self._max_iterations)
        )

    async def run_claw_turn(
        self,
        session_id: str,
        content: str,
        attachments: list[Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Execute one user message through the ReAct loop in Claw mode.

        Does not apply ``plan_mode`` tool gating (mutually exclusive with ``/plan`` at the TUI).

        Resets :attr:`claw_iteration_budget` each turn (same idea as resetting
        ``iteration_budget`` at the start of a conversation turn), then passes it to
        :meth:`~clawcode.llm.agent.Agent.run` so each LLM round consumes one unit.
        """
        self.claw_iteration_budget = IterationBudget(self._max_iterations)
        async for ev in self.run(
            session_id,
            content,
            attachments=attachments,
            plan_mode=False,
            iteration_budget=self.claw_iteration_budget,
        ):
            yield ev


run_claw_conversation = ClawAgent.run_claw_turn
"""Alias naming parity with ``run_conversation``; same as :meth:`ClawAgent.run_claw_turn`."""


__all__ = ["ClawAgent", "IterationBudget", "run_claw_conversation"]
