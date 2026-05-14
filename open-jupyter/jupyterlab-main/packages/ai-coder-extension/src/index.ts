// Copyright (c) Jupyter Studio AI.
//
// Entry point: every plugin is registered via the default export, which is
// the shape JupyterLab expects from a federated/built-in extension.
/**
 * @packageDocumentation
 * @module ai-coder-extension
 */

import { JupyterFrontEndPlugin } from '@jupyterlab/application';

import { cellFooterPlugin } from './plugins/cellFooter';
import { commandsPlugin } from './plugins/commands';
import { errorFixPlugin } from './plugins/errorFix';
import { inlineCompletionPlugin } from './plugins/inlineCompletion';
import { inlineEditPlugin } from './plugins/inlineEdit';
import { permissionPlugin } from './plugins/permission';
import { servicePlugin } from './plugins/service';
import { sidebarPlugin } from './plugins/sidebar';
import { taskPanelPlugin } from './plugins/taskPanel';

const plugins: JupyterFrontEndPlugin<any>[] = [
  servicePlugin,
  sidebarPlugin,
  inlineEditPlugin,
  inlineCompletionPlugin,
  cellFooterPlugin,
  permissionPlugin,
  errorFixPlugin,
  taskPanelPlugin,
  commandsPlugin
];

export default plugins;
