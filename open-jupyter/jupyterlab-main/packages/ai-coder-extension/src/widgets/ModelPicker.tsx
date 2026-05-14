// Copyright (c) Jupyter Studio AI.
//
// Compact model picker rendered above the chat composer. Mirrors clawcode's
// TUI Ctrl+O picker: one row per ``Settings.providers`` slot, greying out
// slots that are disabled or missing an api_key.

import { CoderInfo, ProviderInfo } from '@jupyterlab/ai-coder';
import { ITranslator } from '@jupyterlab/translation';
import * as React from 'react';

export interface ModelPickerProps {
  coder: CoderInfo | null;
  providers: ProviderInfo[];
  busy: boolean;
  error: string | null;
  translator: ITranslator;
  onSelect: (
    model: string,
    providerKey: string | null,
    persist: boolean
  ) => Promise<void> | void;
  onReload: () => Promise<void> | void;
}

interface FlatOption {
  value: string;
  label: string;
  provider_key: string;
  disabled: boolean;
  hasApiKey: boolean;
}

function encodeOption(model: string, providerKey: string): string {
  return `${providerKey}::${model}`;
}

function decodeOption(value: string): { model: string; providerKey: string } | null {
  const idx = value.indexOf('::');
  if (idx < 0) return null;
  return {
    providerKey: value.slice(0, idx),
    model: value.slice(idx + 2)
  };
}

function buildOptions(providers: ProviderInfo[]): FlatOption[] {
  const out: FlatOption[] = [];
  for (const prov of providers) {
    for (const model of prov.models) {
      out.push({
        value: encodeOption(model, prov.provider_key),
        label: `${prov.provider_key} · ${model}`,
        provider_key: prov.provider_key,
        disabled: prov.disabled || !prov.has_api_key,
        hasApiKey: prov.has_api_key
      });
    }
  }
  return out;
}

export function ModelPicker(props: ModelPickerProps): JSX.Element {
  const trans = props.translator.load('jupyterlab');
  const { coder, providers, busy, error } = props;
  const [persist, setPersist] = React.useState(false);
  const [pending, setPending] = React.useState(false);

  const options = React.useMemo(() => buildOptions(providers), [providers]);

  const activeValue =
    coder && coder.model
      ? encodeOption(coder.model, coder.provider_key || '')
      : '';

  const handleChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const decoded = decodeOption(event.target.value);
    if (!decoded) return;
    setPending(true);
    try {
      await props.onSelect(decoded.model, decoded.providerKey || null, persist);
    } finally {
      setPending(false);
    }
  };

  const noOptions = options.length === 0;

  return (
    <div className="jp-AiCoder-modelPicker">
      <label
        className="jp-AiCoder-modelPicker-label"
        htmlFor="jp-AiCoder-modelPicker-select"
        title={
          coder?.provider_class
            ? `${coder.provider_class} → ${coder.model_in_use ?? coder.model ?? ''}`
            : trans.__('Active LLM for chat, Cmd+K and Ghost Text')
        }
      >
        {trans.__('Model')}
      </label>
      <select
        id="jp-AiCoder-modelPicker-select"
        className="jp-AiCoder-modelPicker-select"
        value={activeValue}
        onChange={handleChange}
        disabled={busy || pending || noOptions}
        title={
          noOptions
            ? trans.__(
                'No models configured. Edit providers[*].models in your .clawcode.json.'
              )
            : trans.__('Switch the coder model (hot-reload)')
        }
      >
        {activeValue && !options.some(o => o.value === activeValue) ? (
          <option value={activeValue}>
            {coder?.provider_key
              ? `${coder.provider_key} · ${coder.model ?? '?'}`
              : coder?.model || '?'}
            {' '}
            {trans.__('(current)')}
          </option>
        ) : null}
        {options.map(opt => (
          <option
            key={opt.value}
            value={opt.value}
            disabled={opt.disabled}
          >
            {opt.label}
            {opt.disabled ? (opt.hasApiKey ? ' [disabled]' : ' [no key]') : ''}
          </option>
        ))}
      </select>
      <label
        className="jp-AiCoder-modelPicker-persist"
        title={trans.__('Also write the new selection to .clawcode.json')}
      >
        <input
          type="checkbox"
          checked={persist}
          onChange={e => setPersist(e.target.checked)}
        />
        {trans.__('save')}
      </label>
      <button
        className="jp-AiCoder-button"
        onClick={() => void props.onReload()}
        title={trans.__('Reload provider list from server')}
        disabled={pending}
      >
        ↻
      </button>
      {error ? (
        <div
          className="jp-AiCoder-modelPicker-error"
          title={error}
        >
          {trans.__('error: ')}
          {error.length > 60 ? error.slice(0, 60) + '…' : error}
        </div>
      ) : null}
    </div>
  );
}
