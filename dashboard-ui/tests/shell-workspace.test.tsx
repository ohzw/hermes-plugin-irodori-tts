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
    expect(topbar.querySelector('.brand-glyph .brand-mascot')).toHaveAttribute('src', expect.stringMatching(/irodori-voice-mascot(?:-[^/]+)?\.png$/));
  });

  it('shows Basic and Advanced settings tabs beside a single Playground', async () => {
    await renderLoadedApp();
    expect(screen.getByRole('tab', {name: 'Basic'})).toBeInTheDocument();
    expect(screen.getByRole('tab', {name: 'Advanced'})).toBeInTheDocument();
    expect(screen.getAllByRole('heading', {name: 'Playground'})).toHaveLength(1);
    expect(screen.getByRole('button', {name: 'Generate TTS'}).querySelector('canvas')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Preview'}).querySelector('canvas')).not.toBeInTheDocument();
  });

  it('opens native file selectors and selects an imported reference asset', async () => {
    let importedBody: BodyInit | null | undefined;
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      const config = {
        revision: 'r1',
        values: {ref_wav: 'existing.wav', ref_embed: 'speaker.safetensors'},
        schema: {fields: {
          ref_wav: {label: '参照音声', type: 'reference_audio'},
          ref_embed: {label: '話者埋め込み', type: 'speaker_embedding'},
        }},
      };
      if (url.includes('/api/status')) return new Response(JSON.stringify({now: 'now', health: {ok: true}, recent: []}));
      if (url === '/api/config' && init?.method === 'PATCH') {
        const submitted = JSON.parse(String(init.body)) as {values: Record<string, unknown>};
        return new Response(JSON.stringify({data: {revision: 'r2', values: submitted.values}}));
      }
      if (url === '/api/config') return new Response(JSON.stringify({data: config}));
      if (url === '/api/dictionary') return new Response(JSON.stringify({entries: []}));
      if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: [
        {id: 'existing.wav', label: 'existing.wav', type: 'wav'},
        {id: 'speaker.safetensors', label: 'speaker.safetensors', type: 'safetensors'},
      ]}}));
      if (url.includes('/api/config/voice-assets/import')) {
        importedBody = init?.body;
        return new Response(JSON.stringify({data: {asset: {id: 'new.wav', label: 'new.wav', type: 'wav'}}}));
      }
      return new Response(JSON.stringify({ok: true, data: {}}));
    });

    await renderLoadedApp();
    expect(screen.getByRole('combobox', {name: '参照音声'})).toHaveValue('existing.wav');
    expect(screen.getByRole('combobox', {name: '話者埋め込み'})).toHaveValue('speaker.safetensors');

    const input = screen.getByLabelText('参照音声ファイルを選択');
    const file = new File(['wave-data'], 'new.wav', {type: 'audio/wav'});
    fireEvent.change(input, {target: {files: [file]}});
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(importedBody).toBe(file);
    expect(screen.getByRole('combobox', {name: '参照音声'})).toHaveValue('new.wav');
    expect(screen.getByRole('option', {name: 'new.wav'})).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Save revision'}));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole('combobox', {name: '参照音声'})).toHaveValue('new.wav');
    expect(screen.getByRole('combobox', {name: '話者埋め込み'})).toHaveValue('speaker.safetensors');
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
