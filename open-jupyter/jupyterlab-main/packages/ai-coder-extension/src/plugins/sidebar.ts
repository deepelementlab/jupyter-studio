// Copyright (c) Jupyter Studio AI.

import { IAiCoderService } from '@jupyterlab/ai-coder';
import {
  ILabShell,
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { INotebookTracker } from '@jupyterlab/notebook';
import { IRenderMimeRegistry } from '@jupyterlab/rendermime';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { aiCoderRobotIcon } from '../icons';
import { ChatPanelWidget } from '../widgets/ChatPanel';

export const SIDEBAR_ID = 'jp-ai-coder-sidebar';
export const OPEN_CHAT_COMMAND = 'ai-coder:open-chat';

export const sidebarPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:sidebar',
  description: 'AI Coder chat side bar.',
  autoStart: true,
  requires: [IAiCoderService, INotebookTracker],
  optional: [IRenderMimeRegistry, ILayoutRestorer, ILabShell, ITranslator],
  activate: (
    app: JupyterFrontEnd,
    service: IAiCoderService,
    tracker: INotebookTracker,
    rendermime: IRenderMimeRegistry | null,
    restorer: ILayoutRestorer | null,
    labShell: ILabShell | null,
    translator: ITranslator | null
  ): void => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');
    const widget = new ChatPanelWidget({
      service,
      tracker,
      translator: translator ?? nullTranslator,
      rendermime
    });
    widget.title.icon = aiCoderRobotIcon;
    widget.title.caption = trans.__('AI Coder');

    app.shell.add(widget, 'right', { type: 'AI Coder', rank: 850 });

    if (restorer) {
      restorer.add(widget, SIDEBAR_ID);
    }

    app.commands.addCommand(OPEN_CHAT_COMMAND, {
      label: trans.__('AI Coder: Open Chat'),
      icon: aiCoderRobotIcon,
      execute: () => {
        if (!widget.isAttached) {
          app.shell.add(widget, 'right', { type: 'AI Coder' });
        }
        app.shell.activateById(widget.id);
      }
    });

    void labShell;
  }
};
