// Copyright (c) Jupyter Studio AI.

import { IAiCoderService } from '@jupyterlab/ai-coder';
import {
  ILayoutRestorer,
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { INotebookTracker } from '@jupyterlab/notebook';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { aiCoderSparkleIcon } from '../icons';
import { TaskPanelWidget } from '../widgets/TaskPanel';

const PANEL_ID = 'jp-ai-coder-task-panel';
export const OPEN_TASKS_COMMAND = 'ai-coder:open-tasks';

export const taskPanelPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:task-panel',
  description: 'Side panel showing the AI agent task list (TodoWrite).',
  autoStart: true,
  requires: [IAiCoderService, INotebookTracker],
  optional: [ILayoutRestorer, ITranslator],
  activate: (
    app: JupyterFrontEnd,
    service: IAiCoderService,
    tracker: INotebookTracker,
    restorer: ILayoutRestorer | null,
    translator: ITranslator | null
  ): void => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');
    const widget = new TaskPanelWidget({
      service,
      tracker,
      translator: translator ?? nullTranslator
    });
    widget.title.icon = aiCoderSparkleIcon;
    widget.title.caption = trans.__('AI Tasks');

    app.shell.add(widget, 'right', { type: 'AI Tasks', rank: 870 });
    if (restorer) restorer.add(widget, PANEL_ID);

    app.commands.addCommand(OPEN_TASKS_COMMAND, {
      label: trans.__('AI Coder: Open Tasks Panel'),
      icon: aiCoderSparkleIcon,
      execute: () => {
        if (!widget.isAttached) {
          app.shell.add(widget, 'right', { type: 'AI Tasks' });
        }
        app.shell.activateById(widget.id);
      }
    });
  }
};
