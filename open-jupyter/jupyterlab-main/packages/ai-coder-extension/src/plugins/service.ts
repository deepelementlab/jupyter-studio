// Copyright (c) Jupyter Studio AI.

import { AiCoderService, IAiCoderService } from '@jupyterlab/ai-coder';
import { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { INotebookTracker } from '@jupyterlab/notebook';

export const servicePlugin: JupyterFrontEndPlugin<IAiCoderService> = {
  id: '@jupyterlab/ai-coder-extension:service',
  description: 'Provides the AI coder service singleton.',
  autoStart: true,
  requires: [INotebookTracker],
  provides: IAiCoderService,
  activate: (_app: JupyterFrontEnd, tracker: INotebookTracker): IAiCoderService => {
    return new AiCoderService({ tracker });
  }
};
