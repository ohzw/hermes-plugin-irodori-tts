import React, {useCallback, useEffect, useState} from 'react';
import {api, type ConfigPayload, type DictionaryEntry, type Status} from './shared/api';
import {Overview} from './features/overview';
import {Workspace} from './features/workspace';
import {History} from './features/history';
import {Dictionary} from './features/dictionary';
import {Diagnostics} from './features/diagnostics';
import {Badge} from './components/ui';
import {
  canonicalPath,
  destinationFromPath,
  destinations,
  navigateTo,
  pathForDestination,
  type Destination,
} from './routing';

function Navigation({active}: {active: Destination}) {
  return (
    <nav className="shell-navigation" aria-label="Main navigation">
      <div className="shell-navigation-heading">Destinations</div>
      {destinations.map((destination) => (
        <a
          className={`shell-navigation-link ${active === destination.id ? 'is-active' : ''}`}
          href={pathForDestination(destination.id)}
          key={destination.id}
          aria-current={active === destination.id ? 'page' : undefined}
          onClick={(event) => {
            event.preventDefault();
            navigateTo(destination.id);
          }}
        >
          <span className="navigation-mark" aria-hidden="true" />
          {destination.label}
        </a>
      ))}
    </nav>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status>({});
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [dictionary, setDictionary] = useState<DictionaryEntry[]>([]);
  const [tab, setTab] = useState<Destination>(() => destinationFromPath(window.location.pathname));
  const [error, setError] = useState('');
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [connection, setConnection] = useState<'connecting' | 'live' | 'polling'>('connecting');

  const refresh = useCallback(async () => {
    try {
      const [next, cfg, entries] = await Promise.all([api.status(), api.config(), api.dictionary()]);
      setStatus(next);
      setConfig(cfg.data);
      setDictionary(entries.entries || []);
      setLastRefresh(new Date());
      setError('');
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : 'Unable to reach the service');
    }
  }, []);

  useEffect(() => {
    void refresh();
    let interval: number | null = null;
    let source: EventSource | null = null;
    const startPolling = () => {
      if (interval !== null) return;
      setConnection('polling');
      interval = window.setInterval(() => void refresh(), 5000);
    };
    const stopPolling = () => {
      if (interval === null) return;
      window.clearInterval(interval);
      interval = null;
    };
    startPolling();
    if (typeof EventSource !== 'undefined') {
      source = new EventSource('/api/events/status?limit=30');
      source.onopen = () => {
        stopPolling();
        setConnection('live');
      };
      source.addEventListener('status', (event) => {
        try {
          setStatus(JSON.parse((event as MessageEvent<string>).data) as Status);
          setLastRefresh(new Date());
          setError('');
        } catch {
          setError('Received an invalid live status update');
        }
      });
      source.onerror = () => startPolling();
    }
    const onLocationChange = () => {
      const canonical = canonicalPath(window.location.pathname);
      if (window.location.pathname !== canonical) {
        window.history.replaceState({destination: destinationFromPath(canonical)}, '', canonical);
      }
      setTab(destinationFromPath(canonical));
    };
    onLocationChange();
    window.addEventListener('popstate', onLocationChange);
    return () => {
      stopPolling();
      source?.close();
      window.removeEventListener('popstate', onLocationChange);
    };
  }, [refresh]);

  let content: React.ReactElement;
  if (tab === 'workspace') {
    const activity = (status.recent ?? [])
      .slice(0, 18)
      .reverse()
      .map((record) => Number(record.timing_ms?.irodori_request ?? record.timing_ms?.total ?? 0));
    content = <Workspace config={config} activity={activity} />;
  }
  else if (tab === 'history') content = <History records={status.recent || []} />;
  else if (tab === 'dictionary') content = <Dictionary entries={dictionary} onReload={refresh} />;
  else if (tab === 'diagnostics') content = <Diagnostics status={status} />;
  else content = <Overview status={status} />;

  return (
    <div className="irodori-plugin-root app-shell">
      <header className="shell-topbar">
        <div className="shell-brand">
          <div className="brand-glyph" aria-hidden="true">I</div>
          <div><strong>Irodori</strong><div className="eyebrow">LOCAL VOICE STUDIO</div></div>
        </div>
        <Navigation active={tab} />
        <div
          className="shell-status"
          aria-live="polite"
          title={`${connection}${lastRefresh ? ` · ${lastRefresh.toLocaleTimeString()}` : ''}`}
        >
          <Badge className={status.health?.ok ? 'badge-online' : 'badge-offline'}><span className="status-dot" />{status.health?.ok ? 'Service online' : 'Service unavailable'}</Badge>
          <span className="connection-label">
            {connection === 'live' ? 'Live' : connection === 'connecting' ? 'Connecting' : 'Reconnecting · 5s fallback'}
            {lastRefresh ? ` · ${lastRefresh.toLocaleTimeString()}` : ''}
          </span>
        </div>
      </header>
      <div className="shell-main">
        {error && <div className="shell-alert" role="alert">{error}</div>}
        <main className="shell-content">{content}</main>
      </div>
    </div>
  );
}
