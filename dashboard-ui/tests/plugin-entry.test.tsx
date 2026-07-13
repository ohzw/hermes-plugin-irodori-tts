import {beforeEach, describe, expect, it, vi} from 'vitest';

vi.mock('../src/launcher/Launcher', () => ({default: function MockLauncher() { return null; }}));

describe('Hermes dashboard plugin entry', () => {
  beforeEach(() => {
    vi.resetModules();
    Object.assign(window, {
      __HERMES_PLUGINS__: {register: vi.fn()},
    });
  });

  it('registers the Irodori page with Hermes', async () => {
    await import('../src/plugin-entry');

    expect(window.__HERMES_PLUGINS__.register).toHaveBeenCalledWith(
      'irodori-tts',
      expect.any(Function),
    );
  });
});
