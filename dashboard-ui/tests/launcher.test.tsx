import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import Launcher from '../src/launcher/Launcher';

const URL = 'http://127.0.0.1:9120/workspace';

describe('Hermes Irodori dashboard launcher', () => {
  const fetchJSON = vi.fn();
  const open = vi.fn();

  beforeEach(() => {
    vi.restoreAllMocks();
    fetchJSON.mockReset();
    fetchJSON.mockResolvedValueOnce({running: false, url: URL});
    Object.assign(window, {
      __HERMES_PLUGIN_SDK__: {React: {}, fetchJSON},
      open,
    });
  });

  it('starts, opens, and stops the standalone dashboard', async () => {
    fetchJSON
      .mockResolvedValueOnce({running: true, url: URL, pid: 42})
      .mockResolvedValueOnce({running: false, url: URL});

    render(<Launcher />);
    const start = await screen.findByRole('button', {name: 'Start & Open'});
    fireEvent.click(start);

    await waitFor(() => expect(open).toHaveBeenCalledWith(URL, '_blank', 'noopener,noreferrer'));
    expect(fetchJSON).toHaveBeenCalledWith(
      '/api/plugins/irodori-tts/dashboard/start',
      {method: 'POST'},
    );

    fireEvent.click(await screen.findByRole('button', {name: 'Stop'}));
    await waitFor(() => expect(fetchJSON).toHaveBeenCalledWith(
      '/api/plugins/irodori-tts/dashboard/stop',
      {method: 'POST'},
    ));
  });
});
