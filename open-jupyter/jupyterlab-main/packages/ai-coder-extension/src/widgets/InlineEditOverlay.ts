// Copyright (c) Jupyter Studio AI.
//
// Vanilla-DOM Cmd+K overlay attached at the bottom of the active cell
// editor. Built without React to avoid pulling react-dom into a widget
// that already lives inside CodeMirror; the API is tiny.

import { IAiCoderService } from '@jupyterlab/ai-coder';
import { CodeCell } from '@jupyterlab/cells';
import { ITranslator, nullTranslator } from '@jupyterlab/translation';

import { lineDiff } from '../utils';

export interface IInlineEditOptions {
  cell: CodeCell;
  service: IAiCoderService;
  translator?: ITranslator;
  initialInstruction?: string;
  extraContext?: string;
}

export class InlineEditOverlay {
  constructor(opts: IInlineEditOptions) {
    this._cell = opts.cell;
    this._service = opts.service;
    this._translator = opts.translator ?? nullTranslator;
    this._extraContext = opts.extraContext ?? '';
    this._initialSource = this._cell.model.sharedModel.getSource();
    this._build(opts.initialInstruction ?? '');
  }

  /**
   * Mount the overlay into the cell's editor wrapper.
   */
  open(): void {
    if (this._mounted) return;
    const editorNode = this._cell.editor?.host as HTMLElement | undefined;
    if (!editorNode) return;
    editorNode.parentElement?.insertBefore(
      this._root,
      editorNode.nextSibling
    );
    this._mounted = true;
    this._input.focus();
  }

  close(): void {
    if (!this._mounted) return;
    this._root.remove();
    this._mounted = false;
  }

  // ---------------------------------------------------------------------

  private _build(initialInstruction: string): void {
    const trans = this._translator.load('jupyterlab');

    this._root = document.createElement('div');
    this._root.className = 'jp-AiInlineOverlay';

    const title = document.createElement('div');
    title.className = 'jp-AiInlineOverlay-title';
    title.textContent = '✨ ' + trans.__('AI Edit');
    this._root.appendChild(title);

    this._input = document.createElement('input');
    this._input.className = 'jp-AiInlineOverlay-input';
    this._input.type = 'text';
    this._input.value = initialInstruction;
    this._input.placeholder = trans.__('Describe the change you want…');
    this._root.appendChild(this._input);

    this._statusLine = document.createElement('div');
    this._statusLine.className = 'jp-AiInlineOverlay-help';
    this._root.appendChild(this._statusLine);

    this._diffContainer = document.createElement('div');
    this._diffContainer.style.display = 'none';
    this._root.appendChild(this._diffContainer);

    const footer = document.createElement('div');
    footer.className = 'jp-AiInlineOverlay-footer';

    const help = document.createElement('span');
    help.className = 'jp-AiInlineOverlay-help';
    help.textContent = trans.__('Esc to cancel · Enter to generate');
    footer.appendChild(help);

    const buttons = document.createElement('div');
    const gen = this._mkButton(trans.__('Generate'), () => this._generate(), true);
    gen.dataset.role = 'generate';
    this._generateBtn = gen;
    buttons.appendChild(gen);
    footer.appendChild(buttons);

    this._root.appendChild(footer);

    this._input.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        e.preventDefault();
        this.close();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        void this._generate();
      }
    });
  }

  private _mkButton(label: string, onClick: () => void, primary = false): HTMLButtonElement {
    const b = document.createElement('button');
    b.className = 'jp-AiCoder-button' + (primary ? ' jp-mod-primary' : '');
    b.textContent = label;
    b.onclick = onClick;
    return b;
  }

  private async _generate(): Promise<void> {
    const instruction = this._input.value.trim();
    if (!instruction) return;
    this._statusLine.textContent = '… ' + this._translator.load('jupyterlab').__('Generating');
    this._generateBtn.disabled = true;
    try {
      const newSource = await this._service.editInline({
        instruction,
        selection: this._initialSource,
        cell_source: this._initialSource,
        language: 'python',
        extra_context: this._extraContext
      });
      this._showDiff(newSource);
      this._statusLine.textContent = '';
    } catch (err) {
      this._statusLine.textContent = String(err);
    } finally {
      this._generateBtn.disabled = false;
    }
  }

  private _showDiff(newSource: string): void {
    this._diffContainer.style.display = '';
    this._diffContainer.innerHTML = '';
    const trans = this._translator.load('jupyterlab');
    const wrap = document.createElement('div');
    wrap.className = 'jp-AiDiffOverlay';

    const diff = lineDiff(this._initialSource, newSource);
    for (const line of diff) {
      const span = document.createElement('span');
      if (line.kind === 'add') span.className = 'jp-AiDiff-add';
      else if (line.kind === 'del') span.className = 'jp-AiDiff-del';
      else span.className = 'jp-AiDiff-ctx';
      span.textContent =
        (line.kind === 'add' ? '+ ' : line.kind === 'del' ? '- ' : '  ') +
        line.text;
      wrap.appendChild(span);
    }

    const bar = document.createElement('div');
    bar.className = 'jp-AiDiffOverlay-toolbar';
    bar.appendChild(
      this._mkButton(trans.__('Retry'), () => void this._generate())
    );
    bar.appendChild(
      this._mkButton(trans.__('Reject'), () => this.close())
    );
    bar.appendChild(
      this._mkButton(
        trans.__('Accept'),
        () => {
          this._cell.model.sharedModel.transact(() => {
            this._cell.model.sharedModel.setSource(newSource);
          });
          this.close();
        },
        true
      )
    );
    wrap.appendChild(bar);
    this._diffContainer.appendChild(wrap);
  }

  private _cell: CodeCell;
  private _service: IAiCoderService;
  private _translator: ITranslator;
  private _initialSource: string;
  private _extraContext: string;
  private _root!: HTMLDivElement;
  private _input!: HTMLInputElement;
  private _statusLine!: HTMLDivElement;
  private _diffContainer!: HTMLDivElement;
  private _generateBtn!: HTMLButtonElement;
  private _mounted = false;
}
