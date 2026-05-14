// Copyright (c) Jupyter Studio AI.
//
// Standalone test runner. Run via:
//
//     jlpm test
//
// which builds the package and executes ``node lib/widgets/streamReducer.spec.js``.
//
// Deliberately uses zero external test framework: ``@types/node`` is NOT a
// devDependency of this package (the JupyterLab base tsconfig sets
// ``"types": []`` so adding it would also require ``"types": ["node"]``
// override here). Instead we ship a tiny built-in ``assert`` and rely on a
// thrown error at the end to give Node a non-zero exit code.

import type { AgentEventOut } from '@jupyterlab/ai-coder';

import { reduceStreamEvents, StreamItem } from './streamReducer';
import { estimateTokens } from './thinkingPrefs';

// ---------------------------------------------------------------------------
// Local micro-assert (drop-in subset of ``node:assert/strict``).
// ---------------------------------------------------------------------------

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) {
    return true;
  }
  if (a === null || b === null || a === undefined || b === undefined) {
    return false;
  }
  if (typeof a !== typeof b || typeof a !== 'object') {
    return false;
  }
  if (Array.isArray(a) !== Array.isArray(b)) {
    return false;
  }
  if (Array.isArray(a)) {
    const bArr = b as unknown[];
    if (a.length !== bArr.length) {
      return false;
    }
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], bArr[i])) {
        return false;
      }
    }
    return true;
  }
  const aObj = a as Record<string, unknown>;
  const bObj = b as Record<string, unknown>;
  const aKeys = Object.keys(aObj);
  const bKeys = Object.keys(bObj);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  for (const k of aKeys) {
    if (!deepEqual(aObj[k], bObj[k])) {
      return false;
    }
  }
  return true;
}

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

const assert = {
  equal(actual: unknown, expected: unknown, message?: string): void {
    if (actual !== expected) {
      throw new Error(
        `assert.equal failed: ${pretty(actual)} !== ${pretty(expected)}` +
          (message ? `\n  ${message}` : '')
      );
    }
  },
  deepEqual(actual: unknown, expected: unknown, message?: string): void {
    if (!deepEqual(actual, expected)) {
      throw new Error(
        'assert.deepEqual failed:\n' +
          `  actual:   ${pretty(actual)}\n` +
          `  expected: ${pretty(expected)}` +
          (message ? `\n  ${message}` : '')
      );
    }
  },
  ok(value: unknown, message?: string): void {
    if (!value) {
      throw new Error(
        `assert.ok failed: ${pretty(value)}` +
          (message ? `\n  ${message}` : '')
      );
    }
  }
};

type TestCase = [string, () => void];
const tests: TestCase[] = [];

function test(name: string, fn: () => void): void {
  tests.push([name, fn]);
}

function ev(partial: Partial<AgentEventOut>): AgentEventOut {
  return { kind: 'agent_event', event_type: 'content_delta', ...partial } as AgentEventOut;
}

// ---------------------------------------------------------------------------
// Baseline / empty
// ---------------------------------------------------------------------------

test('empty event list yields no items', () => {
  assert.deepEqual(reduceStreamEvents([]), []);
});

test('a single empty thinking ack is invisible', () => {
  const items = reduceStreamEvents([ev({ event_type: 'thinking', content: '' })]);
  assert.deepEqual(items, []);
});

// ---------------------------------------------------------------------------
// The bug this commit fixes: thinking deltas coalesce
// ---------------------------------------------------------------------------

test('many thinking deltas collapse into ONE thinking item', () => {
  const events = [
    ev({ event_type: 'thinking', content: 'I ' }),
    ev({ event_type: 'thinking', content: 'should ' }),
    ev({ event_type: 'thinking', content: 'think ' }),
    ev({ event_type: 'thinking', content: 'about ' }),
    ev({ event_type: 'thinking', content: 'this.' })
  ];
  const items = reduceStreamEvents(events);
  assert.equal(items.length, 1);
  assert.deepEqual(items[0], {
    kind: 'thinking',
    content: 'I should think about this.'
  });
});

test('per-character thinking deltas (deepseek-reasoner style)', () => {
  const chars = 'hello world'.split('').map(c =>
    ev({ event_type: 'thinking', content: c })
  );
  const items = reduceStreamEvents(chars);
  assert.equal(items.length, 1);
  assert.equal((items[0] as Extract<StreamItem, { kind: 'thinking' }>).content, 'hello world');
});

test('content_delta deltas coalesce into ONE text item', () => {
  const events = [
    ev({ event_type: 'content_delta', content: 'Hello' }),
    ev({ event_type: 'content_delta', content: ', ' }),
    ev({ event_type: 'content_delta', content: 'world!' })
  ];
  const items = reduceStreamEvents(events);
  assert.deepEqual(items, [{ kind: 'text', content: 'Hello, world!' }]);
});

// ---------------------------------------------------------------------------
// Transitions between buffers
// ---------------------------------------------------------------------------

test('thinking then text emits two separate blocks in order', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'thinking', content: 'reasoning...' }),
    ev({ event_type: 'content_delta', content: 'the answer is 42' })
  ]);
  assert.deepEqual(items, [
    { kind: 'thinking', content: 'reasoning...' },
    { kind: 'text', content: 'the answer is 42' }
  ]);
});

test('interleaved thinking and text produces 4 alternating blocks', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'thinking', content: 'first thought' }),
    ev({ event_type: 'content_delta', content: 'partial answer ' }),
    ev({ event_type: 'thinking', content: 'second thought' }),
    ev({ event_type: 'content_delta', content: 'final answer' })
  ]);
  assert.equal(items.length, 4);
  assert.deepEqual(items.map(i => i.kind), ['thinking', 'text', 'thinking', 'text']);
});

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

test('tool_use creates a pending chip; tool_result closes it as done', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'tool_use', tool_name: 'list_cells' }),
    ev({ event_type: 'tool_result', tool_name: 'list_cells', tool_result: 'ok' })
  ]);
  assert.equal(items.length, 1);
  assert.deepEqual(items[0], {
    kind: 'tool',
    tool_name: 'list_cells',
    status: 'done',
    result: 'ok'
  });
});

test('tool_result with is_error marks the chip as error', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'tool_use', tool_name: 'edit_cell' }),
    ev({
      event_type: 'tool_result',
      tool_name: 'edit_cell',
      is_error: true,
      tool_result: 'permission denied'
    })
  ]);
  assert.equal((items[0] as Extract<StreamItem, { kind: 'tool' }>).status, 'error');
});

test('tool_result without a matching pending tool is harmlessly ignored', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'tool_result', tool_name: 'ghost', tool_result: 'x' })
  ]);
  assert.deepEqual(items, []);
});

test('tool_result truncates long previews to 200 chars + ellipsis', () => {
  const big = 'x'.repeat(500);
  const items = reduceStreamEvents([
    ev({ event_type: 'tool_use', tool_name: 'bash' }),
    ev({ event_type: 'tool_result', tool_name: 'bash', tool_result: big })
  ]);
  const tool = items[0] as Extract<StreamItem, { kind: 'tool' }>;
  assert.equal((tool.result || '').length, 201); // 200 chars + the ellipsis char
  assert.ok((tool.result || '').endsWith('…'));
});

test('two pending tools of the same name close LIFO', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'tool_use', tool_name: 'view' }),
    ev({ event_type: 'tool_use', tool_name: 'view' }),
    ev({ event_type: 'tool_result', tool_name: 'view', tool_result: 'second' })
  ]);
  const tools = items.filter(i => i.kind === 'tool') as Array<
    Extract<StreamItem, { kind: 'tool' }>
  >;
  assert.equal(tools.length, 2);
  assert.equal(tools[0].status, 'pending');
  assert.equal(tools[1].status, 'done');
  assert.equal(tools[1].result, 'second');
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

test('error event flushes buffers and appends an error block', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'content_delta', content: 'partial reply' }),
    ev({ event_type: 'error', error: 'rate limit' })
  ]);
  assert.deepEqual(items, [
    { kind: 'text', content: 'partial reply' },
    { kind: 'error', message: 'rate limit' }
  ]);
});

test('error event without message falls back to a placeholder', () => {
  const items = reduceStreamEvents([ev({ event_type: 'error' })]);
  assert.equal(items.length, 1);
  assert.equal((items[0] as Extract<StreamItem, { kind: 'error' }>).message, 'Unknown error');
});

// ---------------------------------------------------------------------------
// Defensive: events the reducer should NOT crash on
// ---------------------------------------------------------------------------

test('unknown event types are ignored, not displayed', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'usage' as any }),
    ev({ event_type: 'response' as any }),
    ev({ event_type: 'weird_new_event' as any, content: 'should not appear' }),
    ev({ event_type: 'content_delta', content: 'hi' })
  ]);
  assert.deepEqual(items, [{ kind: 'text', content: 'hi' }]);
});

test('null/undefined inside events does not throw', () => {
  const items = reduceStreamEvents([
    // @ts-expect-error - simulate a malformed frame surviving wire layer
    null,
    // @ts-expect-error - missing event_type
    { kind: 'agent_event' },
    ev({ event_type: 'content_delta', content: undefined as any }),
    ev({ event_type: 'thinking', content: undefined as any }),
    ev({ event_type: 'content_delta', content: 'real text' })
  ]);
  // Should NOT crash; only the real text item should survive.
  assert.deepEqual(items, [{ kind: 'text', content: 'real text' }]);
});

test('thinking with empty deltas + one real delta yields one item', () => {
  const items = reduceStreamEvents([
    ev({ event_type: 'thinking', content: '' }),
    ev({ event_type: 'thinking', content: '' }),
    ev({ event_type: 'thinking', content: 'actual reasoning' })
  ]);
  assert.deepEqual(items, [{ kind: 'thinking', content: 'actual reasoning' }]);
});

// ---------------------------------------------------------------------------
// Full real-world scenario
// ---------------------------------------------------------------------------

test('end-to-end: thinking -> tool -> result -> text -> done', () => {
  const events: AgentEventOut[] = [
    // 1. server's ack ping
    ev({ event_type: 'thinking', content: '' }),
    // 2. model streams a few thinking chunks
    ev({ event_type: 'thinking', content: 'Let me ' }),
    ev({ event_type: 'thinking', content: 'inspect ' }),
    ev({ event_type: 'thinking', content: 'the notebook.' }),
    // 3. model calls a tool
    ev({ event_type: 'tool_use', tool_name: 'list_cells' }),
    ev({ event_type: 'tool_result', tool_name: 'list_cells', tool_result: '3 code cells' }),
    // 4. model resumes thinking briefly
    ev({ event_type: 'thinking', content: 'Got it.' }),
    // 5. final answer
    ev({ event_type: 'content_delta', content: 'You have ' }),
    ev({ event_type: 'content_delta', content: '3 code cells.' }),
    // 6. response terminator (no displayable text)
    ev({ event_type: 'response' as any })
  ];
  const items = reduceStreamEvents(events);
  assert.deepEqual(items, [
    { kind: 'thinking', content: 'Let me inspect the notebook.' },
    { kind: 'tool', tool_name: 'list_cells', status: 'done', result: '3 code cells' },
    { kind: 'thinking', content: 'Got it.' },
    { kind: 'text', content: 'You have 3 code cells.' }
  ]);
});

// ---------------------------------------------------------------------------
// estimateTokens heuristic
// ---------------------------------------------------------------------------

test('estimateTokens: empty string is 0', () => {
  assert.equal(estimateTokens(''), 0);
});

test('estimateTokens: ascii ~ ceil(chars / 4)', () => {
  // 16 ascii chars -> 4 tokens
  assert.equal(estimateTokens('Hello, world! :)'), Math.ceil(16 / 4));
});

test('estimateTokens: CJK counts as ~1 token per character', () => {
  // 5 CJK chars => 5 tokens
  assert.equal(estimateTokens('你好世界呀'), 5);
});

test('estimateTokens: mixed CJK + ascii', () => {
  // 4 CJK + 5 ascii(" code") -> 4 + ceil(5/4) = 4 + 2 = 6
  assert.equal(estimateTokens('代码很好 code'), 4 + Math.ceil(5 / 4));
});

test('estimateTokens: scales roughly linearly with content size', () => {
  const sample = 'hello world test sentence';
  const tiny = estimateTokens(sample);
  const big = estimateTokens(sample.repeat(100));
  // 100x source should give ~100x tokens within +/- 25% (ceil() rounding +
  // CJK boundary fuzz can shift slightly).
  assert.ok(big >= 75 * tiny, `expected big (${big}) >= ${75 * tiny}`);
  assert.ok(big <= 125 * tiny, `expected big (${big}) <= ${125 * tiny}`);
});

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

function main(): void {
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      fn();
      // eslint-disable-next-line no-console
      console.log(`  \u2713  ${name}`);
    } catch (err) {
      failed++;
      // eslint-disable-next-line no-console
      console.log(`  \u2717  ${name}`);
      // eslint-disable-next-line no-console
      console.log(
        `       ${err instanceof Error ? err.stack ?? err.message : String(err)}`
      );
    }
  }
  if (failed > 0) {
    // Throwing at top level yields exit code 1 from Node without needing
    // ``@types/node`` for ``process.exit``.
    throw new Error(
      `${failed} of ${tests.length} streamReducer tests FAILED.`
    );
  }
  // eslint-disable-next-line no-console
  console.log(`\nAll ${tests.length} streamReducer tests passed.`);
}

main();
