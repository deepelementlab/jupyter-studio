// Copyright (c) Jupyter Studio AI.

import { IAiCoderService } from '@jupyterlab/ai-coder';
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { INotebookTracker } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { getActiveCodeCell, cellErrorText } from '../utils';
import { InlineEditOverlay } from '../widgets/InlineEditOverlay';

export const INLINE_EDIT_COMMAND = 'ai-coder:inline-edit';
export const FIX_LAST_ERROR_COMMAND = 'ai-coder:fix-last-error';

export const inlineEditPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:inline-edit',
  description: 'Cmd+K-style inline cell edit overlay.',
  autoStart: true,
  requires: [IAiCoderService, INotebookTracker],
  optional: [ITranslator],
  activate: (
    app: JupyterFrontEnd,
    service: IAiCoderService,
    tracker: INotebookTracker,
    translator: ITranslator | null
  ): void => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');

    app.commands.addCommand(INLINE_EDIT_COMMAND, {
      label: trans.__('AI Coder: Edit Cell with AI (Cmd+K)'),
      isEnabled: () => getActiveCodeCell(tracker.currentWidget) !== null,
      execute: (args: any) => {
        const cell = getActiveCodeCell(tracker.currentWidget);
        if (!cell) return;
        const overlay = new InlineEditOverlay({
          cell,
          service,
          translator: translator ?? nullTranslator,
          initialInstruction: (args && args.instruction) || '',
          extraContext: (args && args.extraContext) || ''
        });
        overlay.open();
      }
    });

    app.commands.addCommand(FIX_LAST_ERROR_COMMAND, {
      label: trans.__('AI Coder: Fix last error in this cell'),
      isEnabled: () => {
        const cell = getActiveCodeCell(tracker.currentWidget);
        return !!cell && cellErrorText(cell).length > 0;
      },
      execute: () => {
        const cell = getActiveCodeCell(tracker.currentWidget);
        if (!cell) return;
        const err = cellErrorText(cell);
        const overlay = new InlineEditOverlay({
          cell,
          service,
          translator: translator ?? nullTranslator,
          initialInstruction: trans.__('Fix the following error in the cell above.'),
          extraContext: `\n[Error from cell execution]\n${err}\n`
        });
        overlay.open();
      }
    });

    app.commands.addKeyBinding({
      command: INLINE_EDIT_COMMAND,
      keys: ['Accel K'],
      selector: '.jp-Notebook .jp-CodeMirrorEditor'
    });
  }
};
