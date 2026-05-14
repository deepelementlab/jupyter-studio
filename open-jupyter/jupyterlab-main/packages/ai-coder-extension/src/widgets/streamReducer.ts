// Copyright (c) Jupyter Studio AI.
//
// Pure reducer that collapses a stream of ``AgentEventOut`` frames into the
// list of UI items the chat panel actually renders. Kept free of React /
// DOM so it can be unit tested in plain Node (see ``streamReducer.spec.ts``).
//
// The bug this fixes: providers like ``glm-5.1`` / ``deepseek-reasoner``
// stream ``thinking`` content as one event per token (often single words /
// punctuation). Rendering each event in its own ``<div>`` produced the
// "one word per line" mess users were seeing. We coalesce consecutive
// ``thinking`` events (and likewise ``content_delta``) into a single
// buffer that becomes one ``StreamItem``.

import type { AgentEventOut } from '@jupyterlab/ai-coder';

/**
 * Discriminated union: one entry per rendered block in the chat panel.
 */
export type StreamItem =
  | { kind: 'thinking'; content: string }
  | { kind: 'text'; content: string }
  | {
      kind: 'tool';
      tool_name: string;
      status: 'pending' | 'done' | 'error';
      result?: string;
    }
  | { kind: 'error'; message: string };

/**
 * Collapse an event stream into rendered items.
 *
 * Contract:
 *
 * - Consecutive ``thinking`` events with non-empty ``content`` are
 *   concatenated into one ``thinking`` item.
 * - Consecutive ``content_delta`` events are concatenated into one ``text``
 *   item.
 * - When the stream transitions from one kind to another, the current
 *   buffer is flushed (so we don't smear thinking text into the answer).
 * - Empty buffers are never emitted (so the initial empty-thinking "ack"
 *   we send from the server stays invisible).
 * - ``tool_use`` opens a pending ``tool`` chip; the matching ``tool_result``
 *   flips its status to ``done`` / ``error`` and attaches a truncated
 *   preview. If multiple tool_use share a name, the most recent pending one
 *   is closed (LIFO match).
 * - ``error`` flushes both buffers and appends an ``error`` block.
 * - Unknown event types (``usage`` / ``response`` / others) are ignored;
 *   ``response`` is the turn terminator and carries no displayable text.
 */
export function reduceStreamEvents(events: AgentEventOut[]): StreamItem[] {
  const items: StreamItem[] = [];
  let textBuf = '';
  let thinkingBuf = '';
  let activeBuf: 'text' | 'thinking' | null = null;

  const flushBuffers = () => {
    if (activeBuf === 'thinking' && thinkingBuf.length > 0) {
      items.push({ kind: 'thinking', content: thinkingBuf });
    } else if (activeBuf === 'text' && textBuf.length > 0) {
      items.push({ kind: 'text', content: textBuf });
    }
    textBuf = '';
    thinkingBuf = '';
    activeBuf = null;
  };

  const switchBuffer = (next: 'text' | 'thinking') => {
    if (activeBuf === next) {
      return;
    }
    flushBuffers();
    activeBuf = next;
  };

  for (const ev of events) {
    if (!ev || typeof ev.event_type !== 'string') {
      continue;
    }
    switch (ev.event_type) {
      case 'thinking': {
        switchBuffer('thinking');
        if (typeof ev.content === 'string' && ev.content.length > 0) {
          thinkingBuf += ev.content;
        }
        break;
      }
      case 'content_delta': {
        switchBuffer('text');
        if (typeof ev.content === 'string' && ev.content.length > 0) {
          textBuf += ev.content;
        }
        break;
      }
      case 'tool_use': {
        flushBuffers();
        items.push({
          kind: 'tool',
          tool_name: ev.tool_name || 'tool',
          status: 'pending'
        });
        break;
      }
      case 'tool_result': {
        flushBuffers();
        const targetName = ev.tool_name;
        for (let i = items.length - 1; i >= 0; i--) {
          const it = items[i];
          if (
            it.kind === 'tool' &&
            it.status === 'pending' &&
            (!targetName || it.tool_name === targetName)
          ) {
            it.status = ev.is_error ? 'error' : 'done';
            if (typeof ev.tool_result === 'string' && ev.tool_result.length > 0) {
              it.result =
                ev.tool_result.length > 200
                  ? ev.tool_result.slice(0, 200) + '…'
                  : ev.tool_result;
            }
            break;
          }
        }
        break;
      }
      case 'error': {
        flushBuffers();
        const msg =
          typeof ev.error === 'string' && ev.error.length > 0
            ? ev.error
            : 'Unknown error';
        items.push({ kind: 'error', message: msg });
        break;
      }
      // 'usage' / 'response' / anything else: not directly rendered.
      default:
        break;
    }
  }
  flushBuffers();
  return items;
}
