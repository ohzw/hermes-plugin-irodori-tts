import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../src/App';

const request = {
  request_id: 'req-1',
  ts: '2026-07-15T12:00:00Z',
  status: 'ok',
  original_text: 'Rewrite前の文章',
  timing_ms: {total: 1870, rewrite: 320, irodori_request: 1200},
};

beforeEach(() => {
  window.history.replaceState(null, '', '/history');
  vi.restoreAllMocks();
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = String(input);
    if (url.includes('/api/status')) return new Response(JSON.stringify({now: 'now', health: {ok: true}, recent: [request]}));
    if (url === '/api/config') return new Response(JSON.stringify({data: {revision: 'r1', values: {}, schema: {fields: {}}}}));
    if (url === '/api/dictionary') return new Response(JSON.stringify({entries: []}));
    if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: []}}));
    if (url === '/api/requests?limit=50') return new Response(JSON.stringify({requests: [request]}));
    if (url === '/api/audio-history?limit=50') return new Response(JSON.stringify({data: []}));
    if (url === '/api/requests/req-1') return new Response(JSON.stringify({
      ...request,
      speech_text: 'Rewrite後の文章',
      timing_ms: {
        total: 1870,
        rewrite: 320,
        irodori_request: 1200,
        server_start_or_health: 200,
        write_output: 50,
      },
      rewrite: {enabled: true, changed: true, provider: 'openai-codex', model: 'rewrite-model', error: null},
      dictionary: {enabled: true, selected_count: 2, applied: [{surface: 'AI', reading: 'エーアイ'}]},
      attempts: 1,
      audio: {audio_id: 'audio-1', url: '/api/audio/audio-1', format: 'ogg', bytes: 2048},
    }));
    return new Response(JSON.stringify({ok: true, data: {}}));
  });
});

describe('History request detail', () => {
  it('shows transcript comparison, timing hierarchy, and useful metadata', async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText('Rewrite前の文章')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', {name: 'Open detail'}));
    await waitFor(() => expect(screen.getByText('Rewrite後の文章')).toBeInTheDocument());

    const detail = screen.getByTestId('history-detail-req-1');
    expect(within(detail).getByRole('heading', {name: 'Rewrite前'})).toBeInTheDocument();
    expect(within(detail).getByRole('heading', {name: 'Rewrite後'})).toBeInTheDocument();

    expect(within(detail).getByText('Total')).toBeInTheDocument();
    expect(within(detail).getByText('1.87 s')).toBeInTheDocument();
    expect(within(detail).getByText('Rewrite')).toBeInTheDocument();
    expect(within(detail).getByText('320 ms')).toBeInTheDocument();
    expect(within(detail).getByText('Irodori')).toBeInTheDocument();
    expect(within(detail).getByText('1.20 s')).toBeInTheDocument();
    expect(within(detail).getByText('Server / health')).toBeInTheDocument();
    expect(within(detail).getByText('200 ms')).toBeInTheDocument();
    expect(within(detail).getByText('Write output')).toBeInTheDocument();
    expect(within(detail).getByText('50 ms')).toBeInTheDocument();

    expect(within(detail).getByText('rewrite-model')).toBeInTheDocument();
    expect(within(detail).getByText('Changed')).toBeInTheDocument();
    expect(within(detail).getByText('1 applied')).toBeInTheDocument();
    expect(within(detail).getByText('1 attempt')).toBeInTheDocument();
    expect(within(detail).getByText('OGG · 2.0 KB')).toBeInTheDocument();
    expect(within(detail).getByText('req-1')).toBeInTheDocument();
  });
});
