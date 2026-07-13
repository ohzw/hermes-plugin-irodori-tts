import {describe, expect, it, vi, beforeEach} from 'vitest';
import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import App from '../src/App';
import type {RequestRecord} from '../src/shared/api';

const baseConfig = {revision: 'r1', values: {caption: 'server'}, schema: {fields: {caption: {type: 'string'}}}};
const baseDictionary = [{id: 'd1', surface: 'old', reading: 'おーるど', enabled: true}];
let serverConfig = baseConfig;
let serverDictionary = baseDictionary;
let serverRequests: RequestRecord[] = [{request_id: 'one', status: 'ok', original_text: 'first', audio_id: 'audio', timing_ms: {}}];

beforeEach(() => {
  window.history.replaceState(null, '', '/overview');
  serverConfig = structuredClone(baseConfig);
  serverDictionary = structuredClone(baseDictionary);
  serverRequests = [{request_id: 'one', status: 'ok', original_text: 'first', audio_id: 'audio', timing_ms: {}}];
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
    const url = String(input);
    if (url.includes('/api/status')) return new Response(JSON.stringify({now: 'now', health: {ok: true}, recent: serverRequests}));
    if (url === '/api/config') return new Response(JSON.stringify({data: serverConfig}));
    if (url === '/api/dictionary') return new Response(JSON.stringify({entries: serverDictionary}));
    if (url === '/api/requests?limit=50') return new Response(JSON.stringify({requests: serverRequests}));
    if (url === '/api/audio-history?limit=50') return new Response(JSON.stringify({data: []}));
    if (url.startsWith('/api/requests/')) return new Response(JSON.stringify({request_id: 'one', speech_text: 'speech', audio: {audio_id: 'audio', url: '/api/audio/audio'}}));
    if (url === '/api/config/voice-assets') return new Response(JSON.stringify({data: {assets: []}}));
    return new Response(JSON.stringify({ok: true, data: {}}));
  });
});

async function renderWithInitialLoad() {
  vi.useFakeTimers();
  render(<App/>);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe('dashboard state preservation', () => {
  it('keeps the opened audio element and currentTime when polling adds a request', async () => {
    window.history.replaceState(null, '', '/history');
    await renderWithInitialLoad();
    expect(screen.getByText('first')).toBeInTheDocument();
    const item = document.querySelector('[data-request-id="one"]');
    fireEvent.click(screen.getByText('Open detail'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const audio = document.querySelector('audio') as HTMLAudioElement;
    expect(audio).toBeTruthy();
    Object.defineProperty(audio, 'currentTime', {configurable: true, writable: true, value: 17});
    serverRequests = [
      {request_id: 'two', status: 'ok', original_text: 'second', timing_ms: {}},
      ...serverRequests,
    ];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByText('second')).toBeInTheDocument();
    expect(document.querySelector('[data-request-id="one"]')).toBe(item);
    expect(document.querySelector('audio')).toBe(audio);
    expect(audio.currentTime).toBe(17);
  });

  it('keeps a dirty config draft across polling', async () => {
    window.history.replaceState(null, '', '/workspace');
    await renderWithInitialLoad();
    fireEvent.change(screen.getByDisplayValue('server'), {target: {value: 'draft'}});
    serverConfig = {...baseConfig, revision: 'r2', values: {caption: 'server-updated'}};
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByDisplayValue('draft')).toBeInTheDocument();
  });

  it('keeps a dirty dictionary draft across polling', async () => {
    window.history.replaceState(null, '', '/dictionary');
    await renderWithInitialLoad();
    fireEvent.click(screen.getByText('Edit'));
    fireEvent.change(screen.getByDisplayValue('old'), {target: {value: 'draft'}});
    serverDictionary = [{...baseDictionary[0], surface: 'server-updated'}];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByDisplayValue('draft')).toBeInTheDocument();
  });

  it('shows API errors', async () => {
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new Error('offline'));
    render(<App/>);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('offline'));
  });
});
