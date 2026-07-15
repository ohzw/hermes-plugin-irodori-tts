import { useEffect, useRef, useState } from "react";
import {
  api,
  type AudioRecord,
  type Detail,
  type RequestRecord,
} from "../../shared/api";
import { formatBytes, formatTimestamp, display } from "../../shared/format";

function formatDuration(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const milliseconds = Number(value);
  if (!Number.isFinite(milliseconds)) return "—";
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  return `${(milliseconds / 1000).toFixed(2)} s`;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

function attemptLabel(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  const count = Number(value);
  if (!Number.isFinite(count)) return "—";
  return `${count} ${count === 1 ? "attempt" : "attempts"}`;
}
function merge(
  previous: Array<RequestRecord & { audio?: AudioRecord }>,
  requests: RequestRecord[],
  audio: AudioRecord[],
) {
  const safeAudio = Array.isArray(audio) ? audio : [];
  const byRequest = new Map(
    safeAudio
      .filter((item) => item.request_id)
      .map((item) => [String(item.request_id), item]),
  );
  const old = new Map(previous.map((item) => [item.request_id, item]));
  return requests.map(
    (request) =>
      old.get(request.request_id) || {
        ...request,
        audio: byRequest.get(request.request_id),
      },
  );
}

function AuthenticatedAudio({
  url,
  onRef,
}: {
  url: string;
  onRef: (element: HTMLAudioElement | null) => void;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    api
      .audioBlob(url)
      .then((blob) => {
        if (!active) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
      onRef(null);
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [url]);

  if (error) return <p className="muted">音声を読み込めませんでした。</p>;
  if (!objectUrl) return <p className="muted">音声を読み込んでいます…</p>;
  return <audio ref={onRef} controls preload="metadata" src={objectUrl} />;
}

export function History({ records }: { records: RequestRecord[] }) {
  const [items, setItems] = useState<
    Array<RequestRecord & { audio?: AudioRecord }>
  >([]);
  const [open, setOpen] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, Detail>>({});
  const audioRefs = useRef<Record<string, HTMLAudioElement | null>>({});
  useEffect(() => {
    let active = true;
    Promise.all([api.requests(), api.audioHistory()])
      .then(([requestData, audioData]) => {
        if (active)
          setItems((old) =>
            merge(old, requestData.requests || records, audioData.data || []),
          );
      })
      .catch(() => {
        if (active) setItems((old) => (old.length ? old : records));
      });
    return () => {
      active = false;
    };
  }, [records]);
  const toggle = async (id: string) => {
    if (open && open !== id) audioRefs.current[open]?.pause();
    if (open === id) {
      const audio = audioRefs.current[id];
      audio?.pause();
      if (audio) audio.currentTime = 0;
      setOpen(null);
      return;
    }
    setOpen(id);
    if (!details[id]) {
      try {
        const detail = await api.detail(id);
        setDetails((old) => ({ ...old, [id]: detail }));
      } catch {
        setDetails((old) => ({
          ...old,
          [id]: { request_id: id, error: "Detail unavailable" },
        }));
      }
    }
  };
  return (
    <section
      className="history-section history-surface"
      data-testid="history-surface"
    >
      <div className="page-heading">
        <div>
          <div className="eyebrow">HISTORY / REQUEST LOG</div>
          <h2>Recent requests</h2>
          <p>
            Stable request identity keeps playback and inspection state intact.
          </p>
        </div>
        <span className="panel-hint">{items.length} records</span>
      </div>
      <div className="request-list">
        {items.map((item) => {
          const detail = details[item.request_id];
          const audio = detail?.audio || item.audio;
          const timing = detail?.timing_ms || item.timing_ms || {};
          const rewrite = record(detail?.rewrite);
          const dictionary = record(detail?.dictionary);
          const originalText = detail?.original_text || item.original_text || "—";
          const speechText = detail?.speech_text || (detail ? "—" : "Loading…");
          const appliedCount = Array.isArray(dictionary.applied)
            ? dictionary.applied.length
            : dictionary.selected_count == null ? Number.NaN : Number(dictionary.selected_count);
          const audioSummary = audio?.format
            ? `${String(audio.format).toUpperCase()} · ${formatBytes(audio.bytes)}`
            : "—";
          return (
            <article
              className={`request-card ${open === item.request_id ? "is-open" : ""}`}
              data-request-id={item.request_id}
              key={item.request_id}
            >
              <div className="request-card-head">
                <div className="request-summary">
                  <strong>{item.original_text || "—"}</strong>
                  <small>{formatTimestamp(item.ts || item.created_at)}</small>
                </div>
                <span
                  className={`pill ${item.status === "ok" ? "ok" : item.status === "error" ? "err" : ""}`}
                >
                  {display(item.status)}
                </span>
                <button
                  className="ui-button ui-button-outline"
                  type="button"
                  onClick={() => void toggle(item.request_id)}
                >
                  {open === item.request_id ? "Close detail" : "Open detail"}
                </button>
              </div>
              {open === item.request_id && (
                <div className="history-detail-content" data-testid={`history-detail-${item.request_id}`}>
                  <section className="history-timing-section">
                    <div className="eyebrow">TIMING</div>
                    <div className="history-timing-grid">
                      <div className="history-timing-card"><span>Total</span><strong>{formatDuration(timing.total)}</strong></div>
                      <div className="history-timing-card"><span>Rewrite</span><strong>{formatDuration(timing.rewrite)}</strong></div>
                      <div className="history-timing-card"><span>Irodori</span><strong>{formatDuration(timing.irodori_request)}</strong></div>
                    </div>
                    <div className="history-timing-breakdown">
                      <span>Server / health <strong>{formatDuration(timing.server_start_or_health)}</strong></span>
                      <span>Write output <strong>{formatDuration(timing.write_output)}</strong></span>
                    </div>
                  </section>

                  <section className="history-transcript-section">
                    <div className="eyebrow">TRANSCRIPT COMPARISON</div>
                    <div className="history-transcript-grid">
                      <div className="history-transcript-panel">
                        <h3>Rewrite前</h3>
                        <p>{originalText}</p>
                      </div>
                      <div className="history-transcript-panel">
                        <h3>Rewrite後</h3>
                        <p>{speechText}</p>
                      </div>
                    </div>
                  </section>

                  {detail?.error != null && detail.error !== "" && (
                    <div className="history-error" role="alert">{display(detail.error)}</div>
                  )}

                  <div className="history-support-grid">
                    <section>
                    <div className="eyebrow">AUDIO ASSET</div>
                    <h3>Playback</h3>
                    {audio?.audio_id ? (
                      <audio
                        ref={(element) => {
                          audioRefs.current[item.request_id] = element;
                        }}
                        controls
                        preload="metadata"
                        src={
                          audio.url ||
                          `/api/audio/${encodeURIComponent(String(audio.audio_id))}`
                        }
                      />
                    ) : (
                      <p className="muted">
                        このリクエストの保存済み音声はありません。
                      </p>
                    )}
                    </section>

                    <section>
                      <div className="eyebrow">REQUEST DETAILS</div>
                      <dl className="history-metadata">
                        <div><dt>Rewrite state</dt><dd>{rewrite.enabled === true ? "Enabled" : rewrite.enabled === false ? "Disabled" : "—"}{rewrite.changed === true ? <small>Changed</small> : rewrite.changed === false ? <small>Unchanged</small> : null}</dd></div>
                        <div><dt>Rewrite model</dt><dd>{display(rewrite.model)}{rewrite.provider ? <small>{display(rewrite.provider)}</small> : null}</dd></div>
                        <div><dt>Dictionary</dt><dd>{Number.isFinite(appliedCount) ? `${appliedCount} applied` : "—"}</dd></div>
                        <div><dt>Attempts</dt><dd>{attemptLabel(detail?.attempts)}</dd></div>
                        <div><dt>Audio</dt><dd>{audioSummary}</dd></div>
                        <div><dt>Request ID</dt><dd><code>{item.request_id}</code></dd></div>
                      </dl>
                    </section>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
