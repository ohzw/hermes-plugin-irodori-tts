import {act, fireEvent, render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../src/App';

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  vi.restoreAllMocks();
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = String(input);
    if (url.includes('/api/status')) return new Response(JSON.stringify({now: 'now', health: {ok: true}, recent: []}));
    if (url === '/api/config') return new Response(JSON.stringify({data: {revision: 'r1', values: {caption: 'voice'}, schema: {fields: {caption: {label: '声のキャプション', type: 'string'}, num_steps: {label: '生成ステップ数', type: 'integer'}}}}}));
    if (url === '/api/dictionary') return new Response(JSON.stringify({entries: []}));
    if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: []}}));
    return new Response(JSON.stringify({ok: true, data: {}}));
  });
});

async function renderLoadedApp() {
  vi.useFakeTimers();
  render(<App/>);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe('redesigned app shell and workspace', () => {
  it('opens Workspace by default with five navigation destinations', async () => {
    await renderLoadedApp();
    expect(screen.getByRole('heading', {name: 'Voice workspace'})).toBeInTheDocument();
    expect(screen.getByRole('navigation', {name: 'Main navigation'})).toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(5);
  });

  it('shows Basic and Advanced settings tabs beside a single Playground', async () => {
    await renderLoadedApp();
    expect(screen.getByRole('tab', {name: 'Basic'})).toBeInTheDocument();
    expect(screen.getByRole('tab', {name: 'Advanced'})).toBeInTheDocument();
    expect(screen.getAllByRole('heading', {name: 'Playground'})).toHaveLength(1);
  });

  it('uses the installed Dither Kit for the workspace atmosphere', async () => {
    await renderLoadedApp();
    expect(screen.getByTestId('dither-activity')).toBeInTheDocument();
  });

  it('reads and writes dotted configuration keys without nesting them', async () => {
    let submitted: Record<string, unknown> | undefined;
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      const config = {
        revision: 'r1',
        values: {'rewrite.enabled': true, 'rewrite.model': 'configured-model', 'rewrite.fallback': 'original'},
        schema: {fields: {
          'rewrite.enabled': {label: 'テキスト Rewrite', type: 'boolean'},
          'rewrite.model': {label: 'Rewrite モデル', type: 'string'},
          'rewrite.fallback': {label: 'Rewrite 失敗時', type: 'string', enum: ['original', 'empty', 'error']},
        }},
      };
      if (url.includes('/api/status')) return new Response(JSON.stringify({now: 'now', health: {ok: true}, recent: []}));
      if (url === '/api/config' && init?.method === 'PATCH') {
        submitted = JSON.parse(String(init.body));
        return new Response(JSON.stringify({data: {...config, values: (submitted as {values: Record<string, unknown>}).values}}));
      }
      if (url === '/api/config') return new Response(JSON.stringify({data: config}));
      if (url === '/api/dictionary') return new Response(JSON.stringify({entries: []}));
      if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: []}}));
      return new Response(JSON.stringify({ok: true, data: {}}));
    });

    await renderLoadedApp();
    fireEvent.click(screen.getByRole('tab', {name: 'Advanced'}));

    expect(screen.getByRole('checkbox', {name: 'テキスト Rewrite'})).toBeChecked();
    expect(screen.getByRole('textbox', {name: 'Rewrite モデル'})).toHaveValue('configured-model');
    expect(screen.getByRole('combobox', {name: 'Rewrite 失敗時'})).toHaveValue('original');

    fireEvent.change(screen.getByRole('textbox', {name: 'Rewrite モデル'}), {target: {value: 'updated-model'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save revision'}));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(submitted).toBeDefined();
    const values = (submitted as {values: Record<string, unknown>}).values;
    expect(values['rewrite.model']).toBe('updated-model');
    expect(values).not.toHaveProperty('rewrite');
  });
});
