// Copyright (c) Jupyter Studio AI.
// Distributed under the terms of the Modified BSD License.

import { Token } from '@lumino/coreutils';
import { ISignal } from '@lumino/signaling';
import { NotebookPanel } from '@jupyterlab/notebook';
import {
  AgentEventOut,
  CellRef,
  CoderInfo,
  InlineCompleteRequest,
  InlineEditRequest,
  ModelsResponse,
  PermissionRequestOut
} from './models';

/**
 * Outgoing arguments for a user prompt.
 */
export interface IRunUserMessageOptions {
  panel: NotebookPanel;
  text: string;
  cellRefs?: CellRef[];
  fileRefs?: string[];
  planMode?: boolean;
}

/**
 * Aggregated state for a single chat turn (for UI rendering).
 */
export interface IAgentTurn {
  id: string;
  userText: string;
  events: AgentEventOut[];
  startedAt: number;
  finishedAt: number | null;
  isError: boolean;
}

/**
 * Core service exposed by the ai-coder library.
 */
export interface IAiCoderService {
  /**
   * Send a user prompt to the active notebook's agent session.
   */
  runUserMessage(options: IRunUserMessageOptions): Promise<void>;

  /**
   * Short, stateless code completion (Ghost Text).
   */
  generateInline(request: InlineCompleteRequest): Promise<string>;

  /**
   * Short, stateless code edit (Cmd+K).
   */
  editInline(request: InlineEditRequest): Promise<string>;

  /**
   * Cancel an in-flight agent run on the active notebook.
   */
  cancel(panel: NotebookPanel): Promise<void>;

  /**
   * Respond to a permission request previously emitted by the agent.
   */
  decidePermission(
    panel: NotebookPanel,
    requestId: string,
    decision: 'grant' | 'deny' | 'grant_session'
  ): Promise<void>;

  /**
   * Get the list of turns recorded for the active session (live updated).
   */
  getTurns(panel: NotebookPanel): IAgentTurn[];

  /**
   * List configured provider slots and the currently bound coder. Called by
   * the chat panel to populate its model picker.
   */
  listModels(): Promise<ModelsResponse>;

  /**
   * Hot-swap the active coder model. Returns the new ``CoderInfo`` and emits
   * :attr:`coderChanged` on success. If ``persist`` is true the change is
   * also written back to ``.clawcode.json``.
   */
  setCoderModel(opts: {
    model: string;
    providerKey?: string | null;
    persist?: boolean;
  }): Promise<CoderInfo>;

  /** Latest known coder info (populated by ``listModels`` / ``setCoderModel``). */
  readonly currentCoder: CoderInfo | null;

  /** Emitted on every event from the back-end. */
  readonly agentEvent: ISignal<this, { panel: NotebookPanel; event: AgentEventOut }>;

  /** Emitted whenever the back-end asks for permission. */
  readonly permissionRequest: ISignal<
    this,
    { panel: NotebookPanel; request: PermissionRequestOut }
  >;

  /** Emitted when an agent turn completes or fails. */
  readonly turnComplete: ISignal<this, { panel: NotebookPanel; turn: IAgentTurn }>;

  /** Emitted when the session for a panel is (re-)connected. */
  readonly sessionReady: ISignal<this, NotebookPanel>;

  /** Emitted whenever the active coder agent is swapped. */
  readonly coderChanged: ISignal<this, CoderInfo>;
}

/**
 * Token under which the front-end service plugin provides the service.
 */
export const IAiCoderService = new Token<IAiCoderService>(
  '@jupyterlab/ai-coder:IAiCoderService',
  'AI Coder service for chat, inline edit and notebook agent tools.'
);
