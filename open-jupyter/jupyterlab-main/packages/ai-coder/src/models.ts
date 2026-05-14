// Copyright (c) Jupyter Studio AI.
// Distributed under the terms of the Modified BSD License.
//
// TS mirror of jupyter_studio_ai/jupyter_studio_ai/models.py.
// Keep field names in sync.

export type WsInbound =
  | UserMessageIn
  | ToolResponseIn
  | PermissionDecisionIn
  | CancelIn
  | NotebookStateIn
  | PingIn;

export type WsOutbound =
  | AgentEventOut
  | ToolRequestOut
  | PermissionRequestOut
  | ReadyOut
  | ErrorOut
  | PongOut;

export interface CellRef {
  index: number;
  source: string;
  cell_type?: string;
}

export interface UserMessageIn {
  kind: 'user_message';
  text: string;
  cell_refs?: CellRef[];
  file_refs?: string[];
  notebook_path?: string | null;
  model?: string | null;
  plan_mode?: boolean;
}

export interface ToolResponseIn {
  kind: 'tool_response';
  request_id: string;
  result?: unknown;
  is_error?: boolean;
  error_message?: string;
}

export interface PermissionDecisionIn {
  kind: 'permission_decision';
  request_id: string;
  decision: 'grant' | 'deny' | 'grant_session';
}

export interface CancelIn {
  kind: 'cancel';
}

export interface NotebookStateIn {
  kind: 'notebook_state';
  notebook_path?: string | null;
  cells: NotebookCellSnapshot[];
  active_cell_index?: number | null;
}

export interface PingIn {
  kind: 'ping';
}

export interface NotebookCellSnapshot {
  index: number;
  cell_type: 'code' | 'markdown' | 'raw';
  source_preview: string;
  execution_count: number | null;
  has_output: boolean;
}

export type AgentEventType =
  | 'thinking'
  | 'content_delta'
  | 'tool_use'
  | 'tool_result'
  | 'usage'
  | 'response'
  | 'error';

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
}

export interface AgentEventOut {
  kind: 'agent_event';
  event_type: AgentEventType;
  content?: string;
  tool_name?: string;
  tool_call_id?: string;
  tool_input?: unknown;
  tool_result?: string;
  tool_stream?: string;
  is_error?: boolean;
  tool_done?: boolean;
  hud_only?: boolean;
  error?: string;
  usage?: TokenUsage;
  message_id?: string;
  done?: boolean;
}

export interface ToolRequestOut {
  kind: 'tool_request';
  request_id: string;
  method: NotebookRpcMethod;
  params: Record<string, unknown>;
  timeout?: number;
}

export type NotebookRpcMethod =
  | 'listCells'
  | 'readCell'
  | 'readCellOutput'
  | 'editCell'
  | 'insertCell'
  | 'deleteCell'
  | 'runCell'
  | 'setCellMetadata';

export interface PermissionRequestOut {
  kind: 'permission_request';
  request_id: string;
  tool_name: string;
  description: string;
  path?: string | null;
  input?: unknown;
}

export interface ReadyOut {
  kind: 'ready';
  session_id: string;
}

export interface ErrorOut {
  kind: 'error';
  message: string;
}

export interface PongOut {
  kind: 'pong';
}

// REST request/response models -------------------------------------------------

export interface InlineCompleteRequest {
  prefix: string;
  suffix?: string;
  language?: string;
  max_tokens?: number;
  notebook_path?: string | null;
}

export interface InlineCompleteResponse {
  text: string;
}

export interface InlineEditRequest {
  instruction: string;
  selection?: string;
  cell_source?: string;
  language?: string;
  notebook_path?: string | null;
  cell_index?: number | null;
  extra_context?: string;
}

export interface InlineEditResponse {
  text: string;
}

/**
 * One provider slot from ``Settings.providers`` in ``.clawcode.json``.
 *
 * Mirrors ``jupyter_studio_ai/bridge.py::AgentBridge.list_providers``.
 */
export interface ProviderInfo {
  provider_key: string;
  disabled: boolean;
  has_api_key: boolean;
  base_url: string | null;
  models: string[];
}

/**
 * Snapshot of the currently bound coder agent (mirrors
 * ``AgentBridge.current_coder``).
 */
export interface CoderInfo {
  model: string | null;
  provider_key: string | null;
  max_tokens: number | null;
  reasoning_effort: string | null;
  temperature: number | null;
  provider_class: string;
  model_in_use: string | null;
}

/**
 * Response from ``GET /jupyter-studio-ai/models``.
 */
export interface ModelsResponse {
  providers: ProviderInfo[];
  current: CoderInfo;
}

/**
 * Request body for ``POST /jupyter-studio-ai/coder``.
 */
export interface SetCoderRequest {
  model: string;
  provider_key?: string | null;
  persist?: boolean;
}
