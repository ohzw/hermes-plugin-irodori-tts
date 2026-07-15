export type Timing = Record<string, number | undefined>;
export interface RequestRecord { request_id: string; ts?: string; created_at?: string; status?: string; original_text?: string; input_chars?: number; timing_ms?: Timing; audio_id?: string; [key: string]: unknown }
export interface AudioRecord { request_id?: string; audio_id?: string; url?: string; format?: string; bytes?: number; created_at?: string; duration_ms?: number; input_preview?: string; speech_preview?: string; status?: string; [key: string]: unknown }
export interface Detail { request_id: string; status?: string; original_text?: string; speech_text?: string; timing_ms?: Timing; attempts?: number; audio?: AudioRecord; audio_id?: string; rewrite?: Record<string, unknown>; dictionary?: Record<string, unknown>; error?: unknown; [key: string]: unknown }
export interface Status { now?: string; health?: {ok?: boolean; url?: string; latency_ms?: number; error?: string}; recommendation?: string; summary?: Record<string, unknown>; recent?: RequestRecord[]; config?: Record<string, unknown>; latest_debug?: Record<string, unknown>; server_log?: { lines?: string[]; [key: string]: unknown }; [key: string]: unknown }
export interface FieldMeta { label?: string; type?: string; enum?: string[]; minimum?: number; maximum?: number; max_length?: number; description?: string }
export interface ConfigPayload { values?: Record<string, unknown>; schema?: { fields?: Record<string, FieldMeta> }; revision?: string; [key: string]: unknown }
export interface DictionaryEntry { id?: string; surface: string; reading: string; aliases?: string[]; match?: string; mode?: string; enabled?: boolean; [key: string]: unknown }
export interface Validation { ok: boolean; errors?: Array<{message?: string; code?: string}>; warnings?: Array<{message?: string; code?: string}>; info?: Array<{message?: string; code?: string}> }
export interface ConfigView { groups?: Array<{id?: string; title?: string; items?: Array<{key?: string; label?: string; value?: unknown; source?: string; help?: string}>}>; warnings?: string[]; [key: string]: unknown }
function record(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object'; }
export const API_BASE = '/api';
const apiPath = (path: string) => `${API_BASE}${path}`;
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const dashboardWindow = typeof window !== 'undefined'
    ? window as unknown as {__HERMES_PLUGIN_SDK__?: {fetchJSON?: <R>(url: string, init?: RequestInit) => Promise<R>}}
    : undefined;
  const fetchJSON = dashboardWindow?.__HERMES_PLUGIN_SDK__?.fetchJSON;
  if (fetchJSON) return fetchJSON<T>(url, init);
  const response = await fetch(url, init); const data: unknown = await response.json(); if (!response.ok || (record(data) && data.ok === false)) { const detail = record(data) && record(data.error) ? data.error : {}; const message = typeof detail.message === 'string' ? detail.message : response.statusText || 'API request failed'; const error = new Error(message) as Error & {status?: number; code?: string}; error.status = response.status; if (typeof detail.code === 'string') error.code = detail.code; throw error; } return data as T;
}
async function authenticatedBlob(url: string): Promise<Blob> {
  const dashboardWindow = typeof window !== 'undefined'
    ? window as unknown as {__HERMES_PLUGIN_SDK__?: {authedFetch?: (url: string, init?: RequestInit) => Promise<Response>}}
    : undefined;
  const response = dashboardWindow?.__HERMES_PLUGIN_SDK__?.authedFetch
    ? await dashboardWindow.__HERMES_PLUGIN_SDK__.authedFetch(url)
    : await fetch(url);
  if (!response.ok) throw new Error(response.statusText || `Audio request failed (${response.status})`);
  return response.blob();
}
const post = (payload: unknown): RequestInit => ({ method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
export const api = {
  status: () => request<Status>(apiPath('/status?limit=30')),
  config: () => request<{data: ConfigPayload}>(apiPath('/config')),
  voiceAssets: () => request<{data: {assets: Array<{id: string; label: string}>}}>(apiPath('/config/voice-assets')),
  validateConfig: (payload: unknown) => request<{data: ConfigPayload; warnings?: unknown[]}>(apiPath('/config/validate'), post(payload)),
  saveConfig: (payload: unknown) => request<{data: ConfigPayload; warnings?: unknown[]}>(apiPath('/config'), {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}),
  dictionary: () => request<{entries: DictionaryEntry[]}>(apiPath('/dictionary')),
  validateDictionary: (entry: unknown) => request<{data: Validation}>(apiPath('/dictionary/validate'), post({entry})),
  dictionaryAdd: (payload: unknown) => request<unknown>(apiPath('/dictionary/add'), post(payload)),
  dictionaryUpdate: (payload: unknown) => request<unknown>(apiPath('/dictionary/update'), post(payload)),
  dictionaryDelete: (payload: unknown) => request<unknown>(apiPath('/dictionary/delete'), post(payload)),
  requests: () => request<{requests: RequestRecord[]}>(apiPath('/requests?limit=50')),
  audioHistory: () => request<{data: AudioRecord[]; disabled?: boolean; warnings?: string[]}>(apiPath('/audio-history?limit=50')),
  audioBlob: (url: string) => authenticatedBlob(url),
  detail: (id: string) => request<Detail>(apiPath(`/requests/${encodeURIComponent(id)}`)),
  configView: () => request<ConfigView>(apiPath('/config/view')),
  rewritePreview: (payload: unknown) => request<{data: Record<string, unknown>}>(apiPath('/playground/rewrite-preview'), post(payload)),
  tts: (payload: unknown) => request<{data: Record<string, unknown>}>(apiPath('/playground/tts'), post(payload)),
};
