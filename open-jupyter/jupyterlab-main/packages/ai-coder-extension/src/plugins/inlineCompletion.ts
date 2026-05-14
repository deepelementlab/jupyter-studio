// Copyright (c) Jupyter Studio AI.
//
// Inline completion (Ghost Text) provider backed by jupyter_studio_ai's
// stateless /inline/complete endpoint. Registers via the standard
// `ICompletionProviderManager.registerInlineProvider` hook so it composes
// with the rest of JupyterLab's ghost-text UI.

import { IAiCoderService } from '@jupyterlab/ai-coder';
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import {
  CompletionHandler,
  ICompletionProviderManager,
  IInlineCompletionContext,
  IInlineCompletionItem,
  IInlineCompletionList,
  IInlineCompletionProvider
} from '@jupyterlab/completer';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { aiCoderSparkleIcon } from '../icons';

class ClawInlineProvider implements IInlineCompletionProvider {
  readonly name = 'AI Coder';
  readonly identifier = '@jupyterlab/ai-coder:inline-completion';
  readonly icon = aiCoderSparkleIcon;

  constructor(opts: { service: IAiCoderService; translator: ITranslator }) {
    this._service = opts.service;
  }

  async fetch(
    request: CompletionHandler.IRequest,
    _context: IInlineCompletionContext
  ): Promise<IInlineCompletionList<IInlineCompletionItem>> {
    const offset = request.offset ?? request.text.length;
    const prefix = request.text.slice(0, offset);
    const suffix = request.text.slice(offset);
    try {
      const text = await this._service.generateInline({
        prefix,
        suffix,
        language: 'python',
        max_tokens: 80
      });
      if (!text) {
        return { items: [] };
      }
      return {
        items: [
          {
            insertText: text,
            isIncomplete: false
          }
        ]
      };
    } catch (err) {
      console.warn('AI Coder inline completion failed:', err);
      return { items: [] };
    }
  }

  private _service: IAiCoderService;
}

export const inlineCompletionPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:inline-completion',
  description: 'AI inline completion (Ghost Text) provider.',
  autoStart: true,
  requires: [ICompletionProviderManager, IAiCoderService],
  optional: [ITranslator],
  activate: (
    _app: JupyterFrontEnd,
    completionManager: ICompletionProviderManager,
    service: IAiCoderService,
    translator: ITranslator | null
  ): void => {
    completionManager.registerInlineProvider(
      new ClawInlineProvider({
        service,
        translator: translator ?? nullTranslator
      })
    );
  }
};
