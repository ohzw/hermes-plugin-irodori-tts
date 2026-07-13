import {act, render, screen} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import App from '../src/App';

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = String(input);
    if (url.includes('/api/status')) return new Response(JSON.stringify({
      now: 'now', health: {ok: true},
      recent: [{request_id: 'r1', text: 'hello', status: 'ok', timing_ms: {rewrite: 12, irodori_request: 48, total: 60}}],
      summary: {},
    }));
    if (url === '/api/config') return new Response(JSON.stringify({data: {revision: 'r1', values: {}, schema: {fields: {}}}}));
    if (url === '/api/dictionary') return new Response(JSON.stringify({entries: [{id: 'd1', from: 'AI', to: 'エーアイ'}]}));
    if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: []}}));
    if (url.includes('/api/history/')) return new Response(JSON.stringify({record: {request_id: 'r1', text: 'hello'}}));
    return new Response(JSON.stringify({ok: true, data: {}}));
  });
});

describe('remaining redesigned surfaces', () => {
  it.each([
    ['overview', 'overview-surface'],
    ['history', 'history-surface'],
    ['dictionary', 'dictionary-surface'],
    ['diagnostics', 'diagnostics-surface'],
  ])('renders %s in the new surface system', async (path, testId) => {
    window.history.replaceState(null, '', `/${path}`);
    vi.useFakeTimers();
    render(<App />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByTestId(testId)).toBeInTheDocument();
  });
});
