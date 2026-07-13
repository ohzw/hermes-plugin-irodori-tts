import {act, render, screen} from '@testing-library/react';
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
});
