"""Wire-format models for WS messages and REST payloads.

Kept intentionally minimal and explicit so the front-end TS types in
`packages/ai-coder/src/models.ts` can mirror this 1:1.

Inbound (client -> server) WebSocket message kinds:

- ``user_message``:   { kind, text, attachments?, cell_refs?, file_refs? }
- ``tool_response``:  { kind, request_id, result, is_error? }
- ``permission_decision``: { kind, request_id, decision: 'grant'|'deny'|'grant_session' }
- ``cancel``:         { kind }
- ``notebook_state``: { kind, cells: [...] }  (optional snapshot for context)

Outbound (server -> client) WebSocket message kinds:

- ``agent_event``:        { kind, event_type, ... }  serialized clawcode AgentEvent
- ``tool_request``:       { kind, request_id, method, params }  reverse RPC call
- ``permission_request``: { kind, request_id, tool_name, description, path, input }
- ``ready``:              { kind, session_id }
- ``error``:              { kind, message }
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class UserMessageIn(BaseModel):
    kind: Literal["user_message"] = "user_message"
    text: str = ""
    cell_refs: list[dict[str, Any]] = Field(default_factory=list)
    file_refs: list[str] = Field(default_factory=list)
    notebook_path: Optional[str] = None
    model: Optional[str] = None
    plan_mode: bool = False


class ToolResponseIn(BaseModel):
    kind: Literal["tool_response"] = "tool_response"
    request_id: str
    result: Any = None
    is_error: bool = False
    error_message: Optional[str] = None


class PermissionDecisionIn(BaseModel):
    kind: Literal["permission_decision"] = "permission_decision"
    request_id: str
    decision: Literal["grant", "deny", "grant_session"]


class CancelIn(BaseModel):
    kind: Literal["cancel"] = "cancel"


class NotebookStateIn(BaseModel):
    kind: Literal["notebook_state"] = "notebook_state"
    notebook_path: Optional[str] = None
    cells: list[dict[str, Any]] = Field(default_factory=list)
    active_cell_index: Optional[int] = None


class AgentEventOut(BaseModel):
    kind: Literal["agent_event"] = "agent_event"
    event_type: str
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_input: Any = None
    tool_result: Optional[str] = None
    tool_stream: Optional[str] = None
    is_error: bool = False
    tool_done: bool = False
    error: Optional[str] = None
    usage: Optional[dict[str, Any]] = None
    message_id: Optional[str] = None
    done: bool = False


class ToolRequestOut(BaseModel):
    kind: Literal["tool_request"] = "tool_request"
    request_id: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    timeout: float = 60.0


class PermissionRequestOut(BaseModel):
    kind: Literal["permission_request"] = "permission_request"
    request_id: str
    tool_name: str
    description: str
    path: Optional[str] = None
    input: Any = None


class ReadyOut(BaseModel):
    kind: Literal["ready"] = "ready"
    session_id: str


class ErrorOut(BaseModel):
    kind: Literal["error"] = "error"
    message: str


class InlineCompleteRequest(BaseModel):
    prefix: str
    suffix: str = ""
    language: str = "python"
    max_tokens: int = 80
    notebook_path: Optional[str] = None


class InlineEditRequest(BaseModel):
    instruction: str
    selection: str = ""
    cell_source: str = ""
    language: str = "python"
    notebook_path: Optional[str] = None
    cell_index: Optional[int] = None
    extra_context: str = ""


class SetCoderRequest(BaseModel):
    """Payload for ``POST /jupyter-studio-ai/coder``: switch the active model.

    ``provider_key`` is the name of a slot under ``Settings.providers`` (e.g.
    ``openai_glm``, ``anthropic_shengsuanyun``); omitting it lets clawcode
    auto-infer from the model name.

    When ``persist`` is true the new selection is also written back to the
    user's ``.clawcode.json`` so it survives a restart.
    """

    model: str
    provider_key: Optional[str] = None
    persist: bool = False
