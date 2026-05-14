// Copyright (c) Jupyter Studio AI.
//
// Registers cross-cutting commands (open chat, cancel, explain/test/refactor
// shortcuts that target the active cell) and a context-menu entry.

import { IAiCoderService } from '@jupyterlab/ai-coder';
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { ICommandPalette } from '@jupyterlab/apputils';
import { INotebookTracker } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import {
  applySlashCommand,
  getActiveCodeCell,
  SLASH_COMMANDS
} from '../utils';
import { OPEN_CHAT_COMMAND } from './sidebar';
import { INLINE_EDIT_COMMAND } from './inlineEdit';

export const CANCEL_COMMAND = 'ai-coder:cancel';
export const EXPLAIN_COMMAND = 'ai-coder:explain-cell';
export const TEST_COMMAND = 'ai-coder:test-cell';
export const REFACTOR_COMMAND = 'ai-coder:refactor-selection';
export const SEND_COMMAND = 'ai-coder:send';

const CATEGORY = 'AI Coder';

export const commandsPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:commands',
  description: 'AI Coder commands and context menu.',
  autoStart: true,
  requires: [IAiCoderService, INotebookTracker],
  optional: [ICommandPalette, ITranslator],
  activate: (
    app: JupyterFrontEnd,
    service: IAiCoderService,
    tracker: INotebookTracker,
    palette: ICommandPalette | null,
    translator: ITranslator | null
  ): void => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');

    app.commands.addCommand(CANCEL_COMMAND, {
      label: trans.__('AI Coder: Cancel current run'),
      isEnabled: () => !!tracker.currentWidget,
      execute: () => {
        const panel = tracker.currentWidget;
        if (panel) return service.cancel(panel);
      }
    });

    const runWithReference = (slash: string) => async () => {
      const panel = tracker.currentWidget;
      const cell = getActiveCodeCell(panel);
      if (!panel || !cell) return;
      const idx = panel.content.activeCellIndex;
      const text = `/${slash} @cell-${idx}`;
      const parsed = applySlashCommand(text);
      await service.runUserMessage({
        panel,
        text: parsed.text,
        cellRefs: [
          {
            index: idx,
            source: cell.model.sharedModel.getSource()
          }
        ],
        planMode: parsed.planMode
      });
      app.commands.execute(OPEN_CHAT_COMMAND);
    };

    app.commands.addCommand(EXPLAIN_COMMAND, {
      label: trans.__('AI Coder: Explain Cell'),
      isEnabled: () => getActiveCodeCell(tracker.currentWidget) !== null,
      execute: runWithReference('explain')
    });

    app.commands.addCommand(TEST_COMMAND, {
      label: trans.__('AI Coder: Generate Tests for Cell'),
      isEnabled: () => getActiveCodeCell(tracker.currentWidget) !== null,
      execute: runWithReference('test')
    });

    app.commands.addCommand(REFACTOR_COMMAND, {
      label: trans.__('AI Coder: Refactor Cell'),
      isEnabled: () => getActiveCodeCell(tracker.currentWidget) !== null,
      execute: runWithReference('refactor')
    });

    app.commands.addCommand(SEND_COMMAND, {
      label: trans.__('AI Coder: Send prompt'),
      execute: async (args: any) => {
        const panel = tracker.currentWidget;
        if (!panel) return;
        const text = String(args?.text ?? '').trim();
        if (!text) return;
        const parsed = applySlashCommand(text);
        await service.runUserMessage({
          panel,
          text: parsed.text,
          planMode: parsed.planMode
        });
        app.commands.execute(OPEN_CHAT_COMMAND);
      }
    });

    // Context menu on a cell.
    app.contextMenu.addItem({
      command: INLINE_EDIT_COMMAND,
      selector: '.jp-Notebook .jp-Cell',
      rank: 0.1
    });
    app.contextMenu.addItem({
      command: EXPLAIN_COMMAND,
      selector: '.jp-Notebook .jp-Cell',
      rank: 0.2
    });
    app.contextMenu.addItem({
      command: TEST_COMMAND,
      selector: '.jp-Notebook .jp-Cell',
      rank: 0.3
    });
    app.contextMenu.addItem({
      command: REFACTOR_COMMAND,
      selector: '.jp-Notebook .jp-Cell',
      rank: 0.4
    });
    app.contextMenu.addItem({
      type: 'separator',
      selector: '.jp-Notebook .jp-Cell',
      rank: 0.5
    });

    // Top-level shortcut: Accel L opens chat. (Schema also adds this; the
    // explicit registration here is robust against schema-load failures.)
    app.commands.addKeyBinding({
      command: OPEN_CHAT_COMMAND,
      keys: ['Accel L'],
      selector: 'body'
    });

    if (palette) {
      for (const cmd of [
        OPEN_CHAT_COMMAND,
        CANCEL_COMMAND,
        EXPLAIN_COMMAND,
        TEST_COMMAND,
        REFACTOR_COMMAND
      ]) {
        palette.addItem({ command: cmd, category: CATEGORY });
      }
      for (const cmd of Object.keys(SLASH_COMMANDS)) {
        // No standalone palette entry for /plan etc. (covered above).
        void cmd;
      }
    }
  }
};
