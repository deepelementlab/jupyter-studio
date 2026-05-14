// Copyright (c) Jupyter Studio AI.

import { Cell, CodeCell } from '@jupyterlab/cells';
import { NotebookPanel } from '@jupyterlab/notebook';

/** Return the active code cell, or null. */
export function getActiveCodeCell(panel: NotebookPanel | null): CodeCell | null {
  if (!panel) return null;
  const cell = panel.content.activeCell;
  if (cell instanceof CodeCell) return cell;
  return null;
}

/** Best-effort line-based unified diff. */
export interface DiffLine {
  kind: 'add' | 'del' | 'ctx';
  text: string;
}

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before.split('\n');
  const b = after.split('\n');
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array(b.length + 1).fill(0)
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      if (a[i] === b[j]) {
        lcs[i][j] = lcs[i + 1][j + 1] + 1;
      } else {
        lcs[i][j] = Math.max(lcs[i + 1][j], lcs[i][j + 1]);
      }
    }
  }
  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      lines.push({ kind: 'ctx', text: a[i] });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      lines.push({ kind: 'del', text: a[i] });
      i++;
    } else {
      lines.push({ kind: 'add', text: b[j] });
      j++;
    }
  }
  while (i < a.length) {
    lines.push({ kind: 'del', text: a[i++] });
  }
  while (j < b.length) {
    lines.push({ kind: 'add', text: b[j++] });
  }
  return lines;
}

/**
 * Concatenate stream/error outputs of a code cell as plain text. Used to
 * build the "Fix with AI" context.
 */
export function cellErrorText(cell: Cell): string {
  if (!(cell instanceof CodeCell)) return '';
  const outputs = (cell.model as any).outputs;
  const buf: string[] = [];
  for (let i = 0; i < outputs.length; i++) {
    const out = outputs.get(i);
    const data = out.toJSON();
    if (data.output_type === 'error') {
      buf.push(`${data.ename}: ${data.evalue}`);
      if (Array.isArray(data.traceback)) buf.push(data.traceback.join('\n'));
    } else if (data.output_type === 'stream' && data.name === 'stderr') {
      buf.push(String(data.text ?? ''));
    }
  }
  return buf.join('\n');
}

/** Extract @cell-N and #path references from the user input. */
export interface ParsedReferences {
  cellRefs: number[];
  fileRefs: string[];
}

export function parseReferences(text: string): ParsedReferences {
  const cellRefs: number[] = [];
  const fileRefs: string[] = [];
  const reCell = /@cell-(\d+)/g;
  const reFile = /#([\w./\\-]+)/g;
  let m: RegExpExecArray | null;
  while ((m = reCell.exec(text)) !== null) {
    const n = Number(m[1]);
    if (!Number.isNaN(n)) cellRefs.push(n);
  }
  while ((m = reFile.exec(text)) !== null) {
    fileRefs.push(m[1]);
  }
  return { cellRefs: dedupNum(cellRefs), fileRefs: dedupStr(fileRefs) };
}

function dedupNum(xs: number[]): number[] {
  return Array.from(new Set(xs));
}

function dedupStr(xs: string[]): string[] {
  return Array.from(new Set(xs));
}

/** Mapping of slash-commands to canned prompts (used by the composer). */
export const SLASH_COMMANDS: Record<
  string,
  { label: string; prompt: (rest: string) => string }
> = {
  explain: {
    label: 'Explain selected cell',
    prompt: rest => `Explain this code in plain language. ${rest}`.trim()
  },
  test: {
    label: 'Write tests for selected code',
    prompt: rest => `Generate unit tests for the referenced code. ${rest}`.trim()
  },
  refactor: {
    label: 'Refactor selected code',
    prompt: rest =>
      `Refactor the referenced code for clarity and correctness without changing behaviour. ${rest}`.trim()
  },
  plan: {
    label: 'Plan multi-step changes',
    prompt: rest =>
      `Use plan mode: outline the steps to accomplish the task before touching anything. ${rest}`.trim()
  }
};

export function applySlashCommand(text: string): {
  text: string;
  planMode: boolean;
} {
  const m = /^\s*\/(\w+)\s*(.*)$/s.exec(text);
  if (!m) return { text, planMode: false };
  const cmd = m[1].toLowerCase();
  const rest = m[2];
  const handler = SLASH_COMMANDS[cmd];
  if (!handler) return { text, planMode: false };
  return {
    text: handler.prompt(rest),
    planMode: cmd === 'plan'
  };
}
