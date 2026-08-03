import {useEffect, useMemo, useState} from 'react';
import type {FormEvent} from 'react';
import {api, type ConfigPayload, type FieldMeta} from '../../shared/api';
import {Button, Card, CardContent, CardHeader, Input, Select, Switch, Tabs, TabsList, TabsTrigger, Textarea} from '../../components/ui';
import {Sparkline} from '@/components/dither-kit/sparkline';
import {DitherGradient} from '@/components/dither-kit/gradient';
import {Playground} from './Playground';

type VoiceAsset = {id: string; label: string; type?: string};
type ValidationResult = {warnings?: string[]; errors?: string[]};

type SettingGroup = {title: string; keys: string[]};
const basicGroups: SettingGroup[] = [{title: 'Generation basics', keys: ['caption', 'ref_wav', 'ref_wavs', 'ref_embed', 'max_ref_seconds', 'seed']}];
const advancedGroups: SettingGroup[] = [
  {title: 'Quality and speed', keys: ['num_steps', 't_schedule_mode', 'sway_coeff', 'cfg_scale_text', 'cfg_scale_caption', 'cfg_scale_speaker']},
  {title: 'Long-form processing', keys: ['chunking_enabled', 'chunk_min_chars', 'first_sentence_chunk_min_chars']},
  {title: 'Pronunciation and rewrite', keys: ['rewrite.enabled', 'rewrite.model', 'rewrite.fallback', 'rewrite.summary.enabled', 'rewrite.summary.trigger_chars', 'rewrite.summary.target_chars', 'rewrite.summary.max_chars', 'rewrite.summary.max_input_chars', 'pronunciation_dictionary.enabled', 'pronunciation_dictionary.max_prompt_entries']},
];

function configValue(values: Record<string, unknown>, key: string): unknown {
  if (Object.prototype.hasOwnProperty.call(values, key)) return values[key];
  return key.split('.').reduce<unknown>((current, part) => current && typeof current === 'object' ? (current as Record<string, unknown>)[part] : undefined, values);
}

function withConfigValue(values: Record<string, unknown>, key: string, value: unknown) {
  return {...values, [key]: value};
}

function FieldControl({
  meta,
  value,
  assets,
  onChange,
  onFile,
}: {
  meta: FieldMeta;
  value: unknown;
  assets: VoiceAsset[];
  onChange: (value: unknown) => void;
  onFile: (file: File) => Promise<void>;
}) {
  if (meta.type === 'boolean') {
    return (
      <Switch
        checked={Boolean(value)}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={meta.label}
      />
    );
  }

  if (meta.type === 'voice_assets') {
    const selected = Array.isArray(value) ? value.map(String) : [];
    const audioTypes: Record<string, true> = {wav: true, flac: true, mp3: true, ogg: true, opus: true};
    const audioAssets = assets.filter((asset) => {
      const type = asset.type?.toLowerCase() ?? asset.id.split('.').pop()?.toLowerCase();
      return type ? audioTypes[type] === true : false;
    });
    return (
      <div className="reference-assets-control">
        <Select
          multiple
          size={Math.max(3, Math.min(6, audioAssets.length || 3))}
          value={selected}
          onChange={(event) => onChange(Array.from(event.target.selectedOptions, (option) => option.value))}
          aria-label={meta.label}
        >
          {audioAssets.map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.label}
            </option>
          ))}
        </Select>
        <input
          className="ui-input"
          type="file"
          accept=".wav,.flac,.mp3,.ogg,.opus"
          aria-label={`${meta.label ?? '参照音声'}を追加`}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void onFile(file);
          }}
        />
      </div>
    );
  }

  if (meta.type === 'voice_asset' || meta.enum) {
    const options = meta.enum ?? assets.map((asset) => asset.id);
    return (
      <Select
        value={String(value ?? '')}
        onChange={(event) => onChange(event.target.value)}
        aria-label={meta.label}
      >
        <option value="">Select a value</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {assets.find((asset) => asset.id === option)?.label ?? option}
          </option>
        ))}
      </Select>
    );
  }

  if (meta.type === 'file') {
    return <input
      className="ui-input"
      type="file"
      accept=".wav,.flac,.mp3,.ogg,.opus"
      aria-label={meta.label}
      onChange={(event) => {
        const file = event.target.files?.[0];
        if (file) void onFile(file);
      }}
    />;
  }

  if (meta.type === 'textarea') {
    return (
      <Textarea
        value={String(value ?? '')}
        onChange={(event) => onChange(event.target.value)}
        aria-label={meta.label}
      />
    );
  }

  if (meta.type === 'string') {
    return (
      <Input
        value={String(value ?? '')}
        onChange={(event) => onChange(event.target.value)}
        aria-label={meta.label}
      />
    );
  }

  return (
    <Input
      type="number"
      step={meta.type === 'number' ? 0.1 : 1}
      min={meta.minimum}
      max={meta.maximum}
      value={value == null ? '' : String(value)}
      onChange={(event) => {
        const rawValue = event.target.value;
        if (rawValue === '') {
          onChange(null);
        } else if (meta.type === 'integer') {
          onChange(Number.parseInt(rawValue, 10));
        } else {
          onChange(Number.parseFloat(rawValue));
        }
      }}
      aria-label={meta.label}
    />
  );
}

function SettingsGroup({
  group,
  schema,
  draft,
  assets,
  onChange,
  onFile,
}: {
  group: SettingGroup;
  schema: Record<string, FieldMeta>;
  draft: Record<string, unknown>;
  assets: VoiceAsset[];
  onChange: (key: string, value: unknown) => void;
  onFile: (key: string, file: File) => Promise<void>;
}) {
  return (
    <section className="settings-group">
      <h3>{group.title}</h3>
      {group.keys.map((key) => {
        const meta = schema[key] ?? {label: key, type: 'string'};
        return (
          <label className="setting-field" key={key}>
            <span className="setting-label">
              {meta.label ?? key}
              {meta.description && <small>{meta.description}</small>}
            </span>
            <FieldControl
              meta={meta}
              value={configValue(draft, key)}
              assets={assets}
              onChange={(value) => onChange(key, value)}
              onFile={(file) => onFile(key, file)}
            />
          </label>
        );
      })}
    </section>
  );
}

export function Workspace({config: initial, activity}: {config: ConfigPayload | null; activity: number[]}) {
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState(initial?.values ?? {});
  const [assets, setAssets] = useState<VoiceAsset[]>([]);
  const [activeTab, setActiveTab] = useState<'basic' | 'advanced'>('basic');
  const [status, setStatus] = useState('Saved settings');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(saved?.values ?? {}), [draft, saved]);

  useEffect(() => {
    const wasDirty = JSON.stringify(draft) !== JSON.stringify(saved?.values ?? {});
    setSaved(initial);
    if (!wasDirty) setDraft(initial?.values ?? {});
  }, [initial]);
  useEffect(() => { void api.voiceAssets().then((result) => setAssets(result.data?.assets ?? [])).catch(() => setAssets([])); }, []);

  if (!saved) return <div className="workspace-loading">Loading configuration</div>;
  const schema = saved.schema?.fields ?? {};
  const updateValue = (key: string, value: unknown) => {
    setDraft((current) => {
      const next = withConfigValue(current, key, value);
      if (key === 'ref_wavs' && Array.isArray(value) && value.length > 0) {
        next.ref_wav = null;
        next.ref_embed = null;
      } else if (key === 'ref_wav' && value) {
        next.ref_wavs = [];
        next.ref_embed = null;
      } else if (key === 'ref_embed' && value) {
        next.ref_wavs = [];
        next.ref_wav = null;
      }
      return next;
    });
    setWarnings([]);
    setErrors([]);
  };
  const importReferenceAudio = async (key: string, file: File) => {
    setStatus('Importing reference audio'); setWarnings([]); setErrors([]);
    try {
      const result = await api.importReferenceAudio(file);
      const importedId = result.data.asset.id;
      if (key === 'ref_wavs') {
        const current = configValue(draft, key);
        const selected = Array.isArray(current) ? current.map(String) : [];
        updateValue(key, [...new Set([...selected, importedId])]);
      } else {
        updateValue(key, importedId);
      }
      setStatus('Imported · save the revision to apply');
    } catch (error) {
      setErrors([error instanceof Error ? error.message : 'Unable to import reference audio']);
      setStatus('Import failed');
    }
  };
  const resetConfig = () => { setDraft(saved.values ?? {}); setWarnings([]); setErrors([]); setStatus('Reset to saved values'); };
  const validateConfig = async () => {
    setStatus('Validating'); setWarnings([]); setErrors([]);
    try { const result = await api.validateConfig({revision: saved.revision, values: draft}); const validation = result.data as ValidationResult; setWarnings(validation.warnings ?? []); setErrors(validation.errors ?? []); setStatus(validation.errors?.length ? 'Validation failed' : 'Configuration is valid'); }
    catch (error) { setErrors([error instanceof Error ? error.message : 'Validation failed']); setStatus('Validation failed'); }
  };
  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setStatus('Saving'); setWarnings([]); setErrors([]);
    try { const result = await api.saveConfig({revision: saved.revision, values: draft}); const next = {...result.data, schema: result.data.schema ?? saved.schema}; setSaved(next); setDraft(next.values ?? {}); setStatus('Saved · applies to the next generation'); }
    catch (error) { setErrors([error instanceof Error ? error.message : 'Unable to save settings']); setStatus('Save failed'); }
  };
  const groups = activeTab === 'basic' ? basicGroups : advancedGroups;
  const latestLatency = activity.at(-1);
  const hasLatencyTrend = activity.length >= 2;
  return <section className="workspace-page">
    <div className="workspace-hero">
      <div className="page-heading"><div><div className="eyebrow">WORKSPACE</div><h2>Voice workspace</h2><p>Shape a voice, then test it against real text.</p></div></div>
      <div className="workspace-telemetry" aria-label="Recent total latency">
        <DitherGradient from="blue" direction="left" cell={4} opacity={0.12} bloom="off" className="workspace-gradient" />
        <div className="workspace-telemetry-copy">
          <span className="metric-label">Recent total latency</span>
          {latestLatency == null
            ? <strong className="telemetry-empty">No timing samples yet</strong>
            : <><strong className="telemetry-value">{latestLatency >= 1000 ? `${(latestLatency / 1000).toFixed(2)}s` : `${Math.round(latestLatency)}ms`}</strong><span className="metric-note">{activity.length} recent {activity.length === 1 ? 'sample' : 'samples'}</span></>}
        </div>
        {hasLatencyTrend && <div className="dither-activity" data-testid="dither-activity" aria-hidden="true">
          <Sparkline
            data={activity}
            color="blue"
            variant="gradient"
            bloom="off"
            animate={false}
            className="dither-activity-chart"
          />
        </div>}
      </div>
    </div>
    <div className="workspace-layout">
      <Card className="settings-card"><CardHeader><div><h3>Settings</h3><p>Draft changes stay local until saved.</p></div></CardHeader><CardContent>
        <Tabs><TabsList><TabsTrigger active={activeTab === 'basic'} onClick={() => setActiveTab('basic')}>Basic</TabsTrigger><TabsTrigger active={activeTab === 'advanced'} onClick={() => setActiveTab('advanced')}>Advanced</TabsTrigger></TabsList>
          <form className="settings-form" onSubmit={saveConfig}><div role="tabpanel" aria-label={`${activeTab} settings`}><div className="settings-groups">{groups.map((group) => <SettingsGroup key={group.title} group={group} schema={schema} draft={draft} assets={assets} onChange={updateValue} onFile={importReferenceAudio} />)}</div></div>
            <div className="settings-actions"><Button type="submit" disabled={!dirty || errors.length > 0}>Save revision</Button><Button type="button" variant="outline" onClick={() => void validateConfig()}>Validate</Button><Button type="button" variant="ghost" onClick={resetConfig} disabled={!dirty}>Reset</Button><span role="status">{status}</span></div>
            {warnings.length > 0 && <ul className="config-warnings" role="status">{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
            {errors.length > 0 && <ul className="config-errors" role="alert">{errors.map((error) => <li key={error}>{error}</li>)}</ul>}
          </form>
        </Tabs>
      </CardContent></Card>
      <Card className="playground-card"><CardContent><Playground /></CardContent></Card>
    </div>
  </section>;
}
