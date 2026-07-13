import {useEffect, useMemo, useState} from 'react';
import type {FormEvent} from 'react';
import {api, type ConfigPayload, type FieldMeta} from '../../shared/api';
import {Button, Card, CardContent, CardHeader, Input, Select, Switch, Tabs, TabsList, TabsTrigger, Textarea} from '../../components/ui';
import {Sparkline} from '@/components/dither-kit/sparkline';
import {Playground} from './Playground';

type VoiceAsset = {id: string; label: string};
type ValidationResult = {warnings?: string[]; errors?: string[]};

type SettingGroup = {title: string; keys: string[]};
const basicGroups: SettingGroup[] = [{title: 'Generation basics', keys: ['caption', 'ref_embed', 'seed']}];
const advancedGroups: SettingGroup[] = [
  {title: 'Quality and speed', keys: ['num_steps', 't_schedule_mode', 'sway_coeff', 'cfg_scale_text', 'cfg_scale_caption', 'cfg_scale_speaker']},
  {title: 'Long-form processing', keys: ['chunking_enabled', 'chunk_min_chars', 'first_sentence_chunk_min_chars']},
  {title: 'Pronunciation and rewrite', keys: ['rewrite.enabled', 'rewrite.model', 'rewrite.fallback', 'pronunciation_dictionary.enabled', 'pronunciation_dictionary.max_prompt_entries']},
];

function nestedValue(values: Record<string, unknown>, key: string): unknown {
  return key.split('.').reduce<unknown>((current, part) => current && typeof current === 'object' ? (current as Record<string, unknown>)[part] : undefined, values);
}

function withNestedValue(values: Record<string, unknown>, key: string, value: unknown) {
  const result = {...values};
  const parts = key.split('.');
  let target = result;
  parts.forEach((part, index) => {
    if (index === parts.length - 1) target[part] = value;
    else {
      const child = target[part];
      target[part] = child && typeof child === 'object' ? {...child as Record<string, unknown>} : {};
      target = target[part] as Record<string, unknown>;
    }
  });
  return result;
}

function FieldControl({
  meta,
  value,
  assets,
  onChange,
}: {
  meta: FieldMeta;
  value: unknown;
  assets: VoiceAsset[];
  onChange: (value: unknown) => void;
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
}: {
  group: SettingGroup;
  schema: Record<string, FieldMeta>;
  draft: Record<string, unknown>;
  assets: VoiceAsset[];
  onChange: (key: string, value: unknown) => void;
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
              value={nestedValue(draft, key)}
              assets={assets}
              onChange={(value) => onChange(key, value)}
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
  const updateValue = (key: string, value: unknown) => { setDraft((current) => withNestedValue(current, key, value)); setWarnings([]); setErrors([]); };
  const resetConfig = () => { setDraft(saved.values ?? {}); setWarnings([]); setErrors([]); setStatus('Reset to saved values'); };
  const validateConfig = async () => {
    setStatus('Validating'); setWarnings([]); setErrors([]);
    try { const result = await api.validateConfig({revision: saved.revision, values: draft}); const validation = result.data as ValidationResult; setWarnings(validation.warnings ?? []); setErrors(validation.errors ?? []); setStatus(validation.errors?.length ? 'Validation failed' : 'Configuration is valid'); }
    catch (error) { setErrors([error instanceof Error ? error.message : 'Validation failed']); setStatus('Validation failed'); }
  };
  const saveConfig = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setStatus('Saving'); setWarnings([]); setErrors([]);
    try { const result = await api.saveConfig({revision: saved.revision, values: draft}); setSaved(result.data); setDraft(result.data.values ?? {}); setStatus('Saved · applies to the next generation'); }
    catch (error) { setErrors([error instanceof Error ? error.message : 'Unable to save settings']); setStatus('Save failed'); }
  };
  const groups = activeTab === 'basic' ? basicGroups : advancedGroups;
  return <section className="workspace-page">
    <div className="workspace-hero">
      <div className="page-heading"><div><div className="eyebrow">WORKSPACE</div><h2>Voice workspace</h2><p>Shape a voice, then test it against real text.</p></div></div>
      <div className="dither-activity" data-testid="dither-activity" aria-hidden="true">
        <Sparkline
          data={activity.length > 1 ? activity : [8, 18, 12, 31, 20, 44, 28, 52, 34, 61]}
          color="blue"
          variant="dotted"
          bloom="aura"
          animate
          className="dither-activity-chart"
        />
      </div>
    </div>
    <div className="workspace-layout">
      <Card className="settings-card"><CardHeader><div><h3>Settings</h3><p>Draft changes stay local until saved.</p></div></CardHeader><CardContent>
        <Tabs><TabsList><TabsTrigger active={activeTab === 'basic'} onClick={() => setActiveTab('basic')}>Basic</TabsTrigger><TabsTrigger active={activeTab === 'advanced'} onClick={() => setActiveTab('advanced')}>Advanced</TabsTrigger></TabsList>
          <form className="settings-form" onSubmit={saveConfig}><div role="tabpanel" aria-label={`${activeTab} settings`}><div className="settings-groups">{groups.map((group) => <SettingsGroup key={group.title} group={group} schema={schema} draft={draft} assets={assets} onChange={updateValue} />)}</div></div>
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
