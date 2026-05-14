// Copyright (c) Jupyter Studio AI.
//
// Small utilities for the foldable "Reasoning" block:
//   - tokens-estimate (no model-specific tokenizer, just a sensible heuristic)
//   - a global "open by default?" preference persisted to ``localStorage``.

const LS_KEY = 'jp-AiCoder.thinking.defaultOpen';

/**
 * Best-effort token estimate without a model-specific tokenizer.
 *
 * Heuristic, calibrated against typical chat-completion usage:
 *
 * - CJK characters cost ~1 token each (BPE tokenizers don't merge them).
 * - Non-CJK characters cost ~1 token per 4 chars (GPT-3.5/4 average).
 *
 * Will be within ~10-30% of the model-reported count for English+Chinese
 * mixed content; for code-heavy or pure Japanese/Korean text the gap can
 * grow, but the value is intentionally an "estimate" surfaced to the user
 * with a "~" prefix.
 */
export function estimateTokens(text: string): number {
  if (!text) {
    return 0;
  }
  // CJK Unified Ideographs + CJK Extension A + Hiragana/Katakana + Hangul.
  // (Not exhaustive - extension B/C ideographs and CJK symbols are rare in
  //  chat output, and the heuristic is forgiving anyway.)
  const cjkRegex =
    /[\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]/g;
  const cjkCount = (text.match(cjkRegex) || []).length;
  const nonCjkLen = Array.from(text).length - cjkCount;
  const nonCjkTokens = Math.ceil(nonCjkLen / 4);
  return cjkCount + nonCjkTokens;
}

/**
 * Read the "should new thinking blocks render expanded?" preference.
 *
 * Defaults to ``false`` (collapsed) - we don't want chain-of-thought to take
 * over the chat panel on first use.
 */
export function readThinkingDefaultOpen(): boolean {
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    return raw === '1' || raw === 'true';
  } catch {
    return false;
  }
}

/**
 * Persist the user's most-recent toggle so future thinking blocks (and the
 * next chat session) start in the same state.
 *
 * Failures (private mode, quota, etc.) are swallowed because this is purely
 * a convenience.
 */
export function writeThinkingDefaultOpen(open: boolean): void {
  try {
    window.localStorage.setItem(LS_KEY, open ? '1' : '0');
  } catch {
    /* localStorage may be unavailable in some embedded hosts */
  }
}
