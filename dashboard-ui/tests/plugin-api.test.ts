import {beforeEach, describe, expect, it, vi} from 'vitest';
import {api} from '../src/shared/api';

describe('Hermes plugin API client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    delete (window as unknown as Record<string, unknown>).__HERMES_PLUGIN_SDK__;
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({health: {ok: true}}), {status: 200}),
    );
  });

  it('routes requests through the plugin API mount', async () => {
    await api.status();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/status?limit=30',
      undefined,
    );
  });

  it('uses the Hermes authenticated fetch helper when available', async () => {
    const fetchJSON = vi.fn().mockResolvedValue({health: {ok: true}});
    Object.assign(window, {
      __HERMES_PLUGIN_SDK__: {React: {}, fetchJSON},
    });

    await api.status();

    expect(fetchJSON).toHaveBeenCalledWith(
      '/api/status?limit=30',
      undefined,
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('uses the Hermes authenticated raw fetch helper for audio', async () => {
    const audio = new Blob(['audio'], {type: 'audio/mpeg'});
    const authedFetch = vi.fn().mockResolvedValue(
      new Response(audio, {status: 200, headers: {'Content-Type': 'audio/mpeg'}}),
    );
    Object.assign(window, {
      __HERMES_PLUGIN_SDK__: {React: {}, authedFetch},
    });

    const result = await api.audioBlob('/api/audio/audio-1');

    expect(authedFetch).toHaveBeenCalledWith('/api/audio/audio-1');
    expect(result.type).toBe('audio/mpeg');
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
