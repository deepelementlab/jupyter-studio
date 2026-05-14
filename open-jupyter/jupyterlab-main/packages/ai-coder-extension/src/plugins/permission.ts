// Copyright (c) Jupyter Studio AI.
//
// In addition to the inline banner inside the chat sidebar, surface a modal
// for ``dangerous`` tools (edit/insert/delete/run cell, bash, write, ...) so
// the user never misses a permission prompt while focused on a notebook.

import { IAiCoderService, PermissionRequestOut } from '@jupyterlab/ai-coder';
import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';
import { Dialog, showDialog } from '@jupyterlab/apputils';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

const DANGEROUS_TOOLS = new Set([
  'bash',
  'write',
  'edit',
  'patch',
  'execute_code',
  'edit_cell',
  'insert_cell',
  'delete_cell',
  'run_cell'
]);

export const permissionPlugin: JupyterFrontEndPlugin<void> = {
  id: '@jupyterlab/ai-coder-extension:permission',
  description: 'Modal dialog for AI tool permission requests.',
  autoStart: true,
  requires: [IAiCoderService],
  optional: [ITranslator],
  activate: (
    _app: JupyterFrontEnd,
    service: IAiCoderService,
    translator: ITranslator | null
  ): void => {
    const trans = (translator ?? nullTranslator).load('jupyterlab');

    service.permissionRequest.connect(async (_s, args) => {
      const req: PermissionRequestOut = args.request;
      if (!DANGEROUS_TOOLS.has(req.tool_name)) {
        // Non-dangerous prompts are still shown inline in the sidebar.
        return;
      }
      const body = document.createElement('div');
      body.style.maxWidth = '560px';
      const title = document.createElement('div');
      title.style.marginBottom = '6px';
      title.innerHTML = `<strong>${escapeHtml(
        req.tool_name
      )}</strong> &middot; ${escapeHtml(req.description)}`;
      body.appendChild(title);
      if (req.path) {
        const sub = document.createElement('div');
        sub.style.fontFamily = 'var(--jp-code-font-family)';
        sub.style.fontSize = 'var(--jp-code-font-size)';
        sub.style.color = 'var(--jp-ui-font-color2)';
        sub.textContent = req.path;
        body.appendChild(sub);
      }
      if (req.input) {
        const pre = document.createElement('pre');
        pre.style.background = 'var(--jp-layout-color2)';
        pre.style.padding = '6px';
        pre.style.borderRadius = '3px';
        pre.style.maxHeight = '240px';
        pre.style.overflow = 'auto';
        pre.textContent =
          typeof req.input === 'string'
            ? req.input
            : JSON.stringify(req.input, null, 2);
        body.appendChild(pre);
      }
      const result = await showDialog({
        title: trans.__('AI wants to call %1', req.tool_name),
        body: { node: body } as any,
        buttons: [
          Dialog.cancelButton({ label: trans.__('Deny') }),
          Dialog.warnButton({ label: trans.__('Allow once') }),
          Dialog.okButton({ label: trans.__('Allow session') })
        ]
      });
      const decision = mapAccept(result.button.label);
      await service.decidePermission(args.panel, req.request_id, decision);
    });
  }
};

function mapAccept(label: string): 'grant' | 'deny' | 'grant_session' {
  if (/session/i.test(label)) return 'grant_session';
  if (/once/i.test(label) || /allow/i.test(label)) return 'grant';
  return 'deny';
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
