import {act, fireEvent, render, screen, within} from '@testing-library/react';
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

function requestValues(body: BodyInit | null | undefined): Record<string, unknown> {
  const parsed: unknown = JSON.parse(String(body));
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) || !('values' in parsed)) {
    throw new Error('Expected a config payload');
  }
  const values = parsed.values;
  if (!values || typeof values !== 'object' || Array.isArray(values)) {
    throw new Error('Expected config values');
  }
  return Object.fromEntries(Object.entries(values));
}

describe('redesigned app shell and workspace', () => {
  it('opens Workspace by default with five navigation destinations', async () => {
    await renderLoadedApp();
    expect(screen.getByRole('heading', {name: 'Voice workspace'})).toBeInTheDocument();
    expect(screen.getByRole('navigation', {name: 'Main navigation'})).toBeInTheDocument();
    expect(screen.getAllByRole('link')).toHaveLength(5);
  });

  it('uses the approved top navigation shell instead of a vertical sidebar', async () => {
    await renderLoadedApp();
    const topbar = screen.getByRole('banner');
    const navigation = within(topbar).getByRole('navigation', {name: 'Main navigation'});
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    expect(within(navigation).getByRole('link', {name: 'Workspace'})).toHaveAttribute('aria-current', 'page');
  });

  it('shows Basic and Advanced settings tabs beside a single Playground', async () => {
    await renderLoadedApp();
    expect(screen.getByRole('tab', {name: 'Basic'})).toBeInTheDocument();
    expect(screen.getByRole('tab', {name: 'Advanced'})).toBeInTheDocument();
    expect(screen.getAllByRole('heading', {name: 'Test this voice'})).toHaveLength(1);
    expect(screen.getByRole('button', {name: 'Generate TTS'}).querySelector('canvas')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Preview'}).querySelector('canvas')).not.toBeInTheDocument();
  });

  it('uses a native file input for reference audio', async () => {
    let importedBody: BodyInit | null | undefined;
    let savedValues: Record<string, unknown> | undefined;
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/api/status')) return new Response(JSON.stringify({now: 'now', health: {ok: true}, recent: []}));
      if (url === '/api/config' && init?.method === 'PATCH') {
        savedValues = requestValues(init.body);
        return new Response(JSON.stringify({data: {revision: 'r2', values: savedValues}}));
      }
      if (url === '/api/config') return new Response(JSON.stringify({data: {
        revision: 'r1',
        values: {ref_wav: null, ref_embed: 'speaker.safetensors'},
        schema: {fields: {
          ref_wav: {label: '参照音声', type: 'file'},
          ref_embed: {label: '話者埋め込み', type: 'voice_asset'},
        }},
      }}));
      if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: [
        {id: 'speaker.safetensors', label: 'speaker.safetensors'},
      ]}}));
      if (url.includes('/api/config/reference-audio')) {
        importedBody = init?.body;
        return new Response(JSON.stringify({data: {asset: {id: 'sample.wav', label: 'sample.wav'}}}));
      }
      if (url === '/api/dictionary') return new Response(JSON.stringify({entries: []}));
      return new Response(JSON.stringify({ok: true, data: {}}));
    });

    await renderLoadedApp();
    const input = screen.getByLabelText('参照音声');
    expect(input).toHaveAttribute('type', 'file');
    expect(input).toHaveAttribute('accept', '.wav,.flac,.mp3,.ogg,.opus');
    expect(screen.queryByRole('spinbutton', {name: '参照音声'})).not.toBeInTheDocument();

    const file = new File(['wave'], 'sample.wav', {type: 'audio/wav'});
    fireEvent.change(input, {target: {files: [file]}});
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(importedBody).toBe(file);
    expect(screen.getByRole('button', {name: 'Save revision'})).toBeEnabled();
    fireEvent.click(screen.getByRole('button', {name: 'Save revision'}));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(savedValues?.ref_wav).toBe('sample.wav');
    expect(screen.getByLabelText('参照音声')).toHaveAttribute('type', 'file');
  });


  it('imports and saves multiple v4 long-reference clips', async () => {
    let savedValues: Record<string, unknown> | undefined;
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/api/status')) return new Response(JSON.stringify({now: 'now', health: {ok: true}, recent: []}));
      if (url === '/api/config' && init?.method === 'PATCH') {
        savedValues = requestValues(init.body);
        return new Response(JSON.stringify({data: {revision: 'r2', values: savedValues}}));
      }
      if (url === '/api/config') return new Response(JSON.stringify({data: {
        revision: 'r1',
        values: {ref_wavs: []},
        schema: {fields: {
          ref_wavs: {label: '長時間参照音声', type: 'voice_assets'},
        }},
      }}));
      if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: [
        {id: 'existing.wav', label: 'existing.wav', type: 'wav'},
      ]}}));
      if (url.includes('/api/config/reference-audio')) {
        return new Response(JSON.stringify({data: {asset: {id: 'imported.wav', label: 'imported.wav', type: 'wav'}}}));
      }
      if (url === '/api/dictionary') return new Response(JSON.stringify({entries: []}));
      return new Response(JSON.stringify({ok: true, data: {}}));
    });

    await renderLoadedApp();
    expect(screen.getByRole('listbox', {name: '長時間参照音声'})).toBeInTheDocument();
    const input = screen.getByLabelText('長時間参照音声を追加');
    fireEvent.change(input, {target: {files: [new File(['wave'], 'imported.wav', {type: 'audio/wav'})]}});
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getByRole('button', {name: 'Save revision'}));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(savedValues?.ref_wavs).toEqual(['imported.wav']);
  });

  it('does not invent decorative timing data when the workspace has no samples', async () => {
    await renderLoadedApp();
    expect(screen.getByText('No timing samples yet')).toBeInTheDocument();
    expect(screen.queryByTestId('dither-activity')).not.toBeInTheDocument();
  });

  it('reads and writes dotted configuration keys without nesting them', async () => {
    let submitted: Record<string, unknown> | undefined;
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      const config = {
        revision: 'r1',
        values: {'rewrite.enabled': true, 'rewrite.model': 'configured-model', 'rewrite.fallback': 'original', 'rewrite.summary.enabled': true, 'rewrite.summary.trigger_chars': 1200, 'rewrite.summary.target_chars': 350, 'rewrite.summary.max_chars': 400, 'rewrite.summary.max_input_chars': 16000},
        schema: {fields: {
          'rewrite.enabled': {label: 'テキスト Rewrite', type: 'boolean'},
          'rewrite.model': {label: 'Rewrite モデル', type: 'string'},
          'rewrite.fallback': {label: 'Rewrite 失敗時', type: 'string', enum: ['original', 'empty', 'error']},
          'rewrite.summary.enabled': {label: '長文の要約', type: 'boolean'},
          'rewrite.summary.trigger_chars': {label: '要約を開始する文字数', type: 'integer'},
          'rewrite.summary.target_chars': {label: '要約の目標文字数', type: 'integer'},
          'rewrite.summary.max_chars': {label: '要約の最大文字数', type: 'integer'},
          'rewrite.summary.max_input_chars': {label: '要約へ渡す最大文字数', type: 'integer'},
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
    expect(screen.getByRole('checkbox', {name: '長文の要約'})).toBeChecked();
    expect(screen.getByRole('textbox', {name: 'Rewrite モデル'})).toHaveValue('configured-model');
    expect(screen.getByRole('combobox', {name: 'Rewrite 失敗時'})).toHaveValue('original');
    expect(screen.getByRole('spinbutton', {name: '要約の目標文字数'})).toHaveValue(350);

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
