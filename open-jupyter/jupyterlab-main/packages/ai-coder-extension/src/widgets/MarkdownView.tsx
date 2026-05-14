// Copyright (c) Jupyter Studio AI.
//
// React wrapper around a JupyterLab ``text/markdown`` mime renderer. Used for
// both the assistant's reply text and the foldable "Reasoning" block so that
// inline code, fenced code blocks, lists, tables and LaTeX go through the
// same pipeline notebooks use - including syntax highlighting and KaTeX.

import { MimeModel } from '@jupyterlab/rendermime';
import type {
  IRenderMime,
  IRenderMimeRegistry
} from '@jupyterlab/rendermime';
import * as React from 'react';

const MIME_MARKDOWN = 'text/markdown';

export interface MarkdownViewProps {
  /**
   * Markdown source. Updates re-render the same underlying widget so streaming
   * deltas don't reset KaTeX / highlighter state on every token.
   */
  content: string;

  /**
   * The shared rendermime registry. When ``null`` (rendermime token wasn't
   * provided by the host) we fall back to a plain ``<div>`` with whitespace
   * preserved - the chat still works, just without Markdown formatting.
   */
  rendermime: IRenderMimeRegistry | null;

  /**
   * Optional extra class name to merge on the host element.
   */
  className?: string;
}

/**
 * React component that mounts a single JupyterLab markdown renderer widget
 * inside a host ``<div>``. Streaming-friendly: re-rendering the same instance
 * with new content reuses the underlying widget and only triggers a re-parse.
 */
export function MarkdownView(props: MarkdownViewProps): JSX.Element {
  const hostRef = React.useRef<HTMLDivElement>(null);
  const rendererRef = React.useRef<IRenderMime.IRenderer | null>(null);
  const lastRenderedRef = React.useRef<string>('');

  // Mount / unmount lifecycle: create the renderer, append its DOM node,
  // dispose on unmount. We do NOT use ``Widget.attach`` because that is for
  // top-level Lumino attachment; for an embedded React host we just splice
  // ``renderer.node`` into the DOM and let React manage layout around it.
  React.useEffect(() => {
    const host = hostRef.current;
    if (!host || !props.rendermime) {
      return;
    }
    let renderer: IRenderMime.IRenderer;
    try {
      renderer = props.rendermime.createRenderer(MIME_MARKDOWN);
    } catch {
      return;
    }
    rendererRef.current = renderer;
    host.appendChild(renderer.node);
    return () => {
      try {
        renderer.dispose();
      } catch {
        /* swallow: dispose on a detached node can throw on some lumino versions */
      }
      rendererRef.current = null;
      if (host.contains(renderer.node)) {
        try {
          host.removeChild(renderer.node);
        } catch {
          /* ignore */
        }
      }
    };
    // We only want to attach once per component instance; content updates
    // are handled by the separate effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.rendermime]);

  // Re-render on content changes (or on initial mount once the renderer is up).
  React.useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer) {
      return;
    }
    if (lastRenderedRef.current === props.content) {
      return;
    }
    lastRenderedRef.current = props.content;
    const model = new MimeModel({
      data: { [MIME_MARKDOWN]: props.content },
      trusted: false
    });
    void renderer.renderModel(model);
  }, [props.content]);

  // Fallback: rendermime missing -> plain preformatted text (still readable,
  // just no Markdown). This keeps the chat panel functional even in stripped-
  // down hosts that don't provide ``IRenderMimeRegistry``.
  if (!props.rendermime) {
    return (
      <div
        className={
          'jp-AiCoder-markdown jp-AiCoder-markdown-plain' +
          (props.className ? ' ' + props.className : '')
        }
        style={{ whiteSpace: 'pre-wrap' }}
      >
        {props.content}
      </div>
    );
  }

  return (
    <div
      ref={hostRef}
      className={
        'jp-AiCoder-markdown' + (props.className ? ' ' + props.className : '')
      }
    />
  );
}
