import {useCallback, useEffect, useState} from 'react';

interface DashboardState {
  running: boolean;
  url: string;
  pid?: number | null;
  error?: string | null;
}

const API_BASE = '/api/plugins/irodori-tts/dashboard';

function sdkFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const fetchJSON = window.__HERMES_PLUGIN_SDK__?.fetchJSON;
  if (!fetchJSON) return Promise.reject(new Error('Hermes dashboard SDK is unavailable'));
  return fetchJSON<T>(url, init);
}

async function post(action: 'start' | 'stop'): Promise<DashboardState> {
  return sdkFetch<DashboardState>(`${API_BASE}/${action}`, {method: 'POST'});
}

export default function Launcher() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      setState(await sdkFetch<DashboardState>(`${API_BASE}/status`));
      setError('');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Unable to inspect Irodori Dashboard');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const startAndOpen = async () => {
    setBusy(true);
    try {
      const next = state?.running ? state : await post('start');
      setState(next);
      window.open(next.url, '_blank', 'noopener,noreferrer');
      setError('');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Unable to start Irodori Dashboard');
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      setState(await post('stop'));
      setError('');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Unable to stop Irodori Dashboard');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="irodori-launcher">
      <div className="irodori-launcher__mark" aria-hidden="true">I</div>
      <div className="irodori-launcher__content">
        <div className="irodori-launcher__eyebrow">LOCAL VOICE DASHBOARD</div>
        <h2>Irodori TTS</h2>
        <p className="irodori-launcher__status" aria-live="polite">
          <span className={state?.running ? 'is-online' : 'is-offline'} />
          {state?.running ? 'Running' : 'Stopped'}
        </p>
        {state?.url && <code>{state.url}</code>}
        {error && <p className="irodori-launcher__error" role="alert">{error}</p>}
        <div className="irodori-launcher__actions">
          <button type="button" disabled={busy} onClick={() => void startAndOpen()}>
            {state?.running ? 'Open Dashboard' : 'Start & Open'}
          </button>
          <button type="button" disabled={busy || !state?.running} onClick={() => void stop()}>
            Stop
          </button>
        </div>
      </div>
    </section>
  );
}
