import React, {useCallback, useEffect, useState} from 'react';
import {api, type ConfigPayload, type DictionaryEntry, type Status} from './shared/api';
import {Overview} from './features/overview';
import {Workspace} from './features/workspace';
import {History} from './features/history';
import {Dictionary} from './features/dictionary';
import {Diagnostics} from './features/diagnostics';
import {Badge, Separator} from './components/ui';
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
    const interval = window.setInterval(() => void refresh(), 5000);
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
      window.clearInterval(interval);
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
      <aside className="shell-sidebar">
        <div className="shell-brand">
          <div className="brand-glyph" aria-hidden="true">I</div>
          <div><div className="eyebrow">IRODORI TTS</div><strong>Voice console</strong></div>
        </div>
        <Navigation active={tab} />
        <div className="sidebar-note"><span className="dither-orb" aria-hidden="true" />Local-first voice tools</div>
      </aside>
      <div className="shell-main">
        <header className="shell-header">
          <div className="mobile-brand"><span className="brand-glyph" aria-hidden="true">I</span><strong>Irodori TTS</strong></div>
          <div className="shell-title"><span className="eyebrow">LOCAL VOICE GENERATION</span><h1>{destinations.find((item) => item.id === tab)?.label}</h1></div>
          <div className="shell-status" aria-live="polite">
            <Badge className={status.health?.ok ? 'badge-online' : 'badge-offline'}><span className="status-dot" />{status.health?.ok ? 'Service online' : 'Service unavailable'}</Badge>
            <span className="refresh-label">Refreshes every 5 seconds{lastRefresh ? ` · ${lastRefresh.toLocaleTimeString()}` : ''}</span>
          </div>
        </header>
        <Separator />
        {error && <div className="shell-alert" role="alert">{error}</div>}
        <main className="shell-content">{content}</main>
      </div>
    </div>
  );
}
