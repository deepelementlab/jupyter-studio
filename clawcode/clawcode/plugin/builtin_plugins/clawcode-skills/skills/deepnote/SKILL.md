---
name: deepnote
description: "DeepNote knowledge base: persistent interlinked markdown wiki with ingest, query, lint, link graph and history."
allowed-tools: [wiki_orient, wiki_ingest, wiki_query, wiki_lint, wiki_link, wiki_history, view, glob, grep]
context: inline
user-invocable: true
disable-model-invocation: false
---

# DeepNote Wiki

DeepNote is the improved `llm-wiki` implementation for ClawCode.

## Quick Start

1. Call `wiki_orient` to load schema, index, and recent logs.
2. Call `wiki_ingest` to save sources and update pages.
3. Call `wiki_query` to retrieve knowledge.
4. Call `wiki_lint` regularly to prevent drift.
5. Use `wiki_link` / `wiki_history` for maintenance and traceability.

## Storage Layout

- Root path from config: `deepnote.path` (default `~/deepnote`)
- Immutable sources in `raw/`
- Compiled pages in `entities/`, `concepts/`, `comparisons/`, `queries/`
- Metadata in `.deepnote/` (graph, history, index)

## Improvements vs llm-wiki

- Dedicated tools instead of pure convention.
- Structured lint checks for frontmatter, links, and schema taxonomy.
- Persistent link graph and operation history.
- Hybrid retrieval path with optional vector-store backend.

