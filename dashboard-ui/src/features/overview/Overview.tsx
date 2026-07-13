import type {Status} from '../../shared/api';
import {AreaChart} from '../../components/dither-kit/area-chart';
import {Area, Line} from '../../components/dither-kit/area';
import {XAxis} from '../../components/dither-kit/x-axis';
import {YAxis} from '../../components/dither-kit/y-axis';
import {Legend} from '../../components/dither-kit/legend';
import {Tooltip} from '../../components/dither-kit/tooltip';
import {Grid} from '../../components/dither-kit/grid';

function record(value: unknown): Record<string, unknown> { return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}; }
function numberAt(value: unknown, key: string): number { const candidate = Number(record(value)[key] ?? 0); return Number.isFinite(candidate) ? candidate : 0; }
function seconds(value: number): string { return value > 0 ? `${(value / 1000).toFixed(2)}s` : '—'; }
function chartLabel(value: unknown, index: number): string {
  if (typeof value !== 'string' || !value) return `#${index + 1}`;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
}
function axisDuration(value: unknown): string {
  const milliseconds = Number(value);
  if (!Number.isFinite(milliseconds)) return '';
  return milliseconds >= 1000 ? `${Math.round(milliseconds / 1000)}s` : `${Math.round(milliseconds)}ms`;
}
function SummaryRow({label, value}: {label: string; value: string}) { return <div className="row"><span>{label}</span><strong>{value}</strong></div>; }

export function Overview({status}: {status: Status}) {
  const summary = record(status.summary); const total = record(summary.total_ms); const rewrite = record(summary.rewrite_ms); const irodori = record(summary.irodori_request_ms); const server = record(summary.server_start_or_health_ms); const other = record(summary.other_ms);
  const threshold = Number(status.slow_threshold_ms ?? 0);
  const chartData = [...(status.recent ?? [])].reverse().map((item, index) => { const timing = item.timing_ms ?? {}; return { index: index + 1, label: chartLabel(item.ts || item.created_at, index), rewrite: Number(timing.rewrite ?? 0), irodori: Number(timing.irodori_request ?? 0), total: Number(timing.total ?? 0) }; });
  return <section className="tab-view active overview-surface" data-testid="overview-surface">
    <div className="page-heading"><div><div className="eyebrow">OVERVIEW / TELEMETRY</div><h2>Performance overview</h2><p>Inspect the latest voice requests without leaving the local console.</p></div><span className="panel-hint">直近30件</span></div>
    <section className="metric-strip" aria-label="パフォーマンス概要">
      <div className="metric-card"><span className="metric-label">平均レイテンシー</span><strong className="metric-value">{seconds(numberAt(total, 'avg'))}</strong><span className="metric-note">直近の成功リクエスト</span></div>
      <div className="metric-card"><span className="metric-label">主なボトルネック</span><strong className="metric-value metric-accent">{String(summary.bottleneck ?? 'n/a')}</strong><span className="metric-note">{status.recommendation || '計測結果を読み込み中'}</span></div>
      <div className="metric-card metric-threshold"><span className="metric-label">Slow threshold</span><strong className="metric-value">{seconds(threshold)}</strong><span className="metric-note">超過したリクエストを警告表示</span></div>
    </section>
    <section className="panel performance-panel dither-panel"><div className="panel-header"><div><div className="eyebrow">OBSERVE / DITHER TRACE</div><h2>Rewrite / Irodori processing</h2></div><span className="panel-hint">直近30件</span></div>
      <div className="chart-card overview-chart"><div className="chart-title"><strong>処理時間の推移</strong><span className="legend-hint">ms · hover for exact values</span></div>
        {chartData.length ? <AreaChart data={chartData} config={{rewrite:{label:'Rewrite',color:'blue'}, irodori:{label:'Irodori',color:'purple'}, total:{label:'Total',color:'green'}}} margins={{top:30,right:20,bottom:28,left:52}} bloom="low" replayOnDataChange={false} className="overview-chart-canvas"><Grid horizontal vertical={false}/><Area dataKey="total" variant="gradient" strokeVariant="solid"/><Line dataKey="irodori" variant="dotted" strokeVariant="solid"/><Line dataKey="rewrite" variant="dotted" strokeVariant="dashed"/><XAxis dataKey="label" maxTicks={6}/><YAxis tickFormatter={axisDuration}/><Legend isClickable align="right"/><Tooltip labelKey="label" valueFormatter={(value) => axisDuration(value)} /></AreaChart> : <div className="chart-empty">No recent timing data yet.</div>}
      </div>
      <div className="summary-grid"><SummaryRow label="runs" value={`${Number(summary.ok_runs ?? 0)} ok / ${Number(summary.error_runs ?? 0)} errors`}/><SummaryRow label="total avg / p90" value={`${seconds(numberAt(total, 'avg'))} / ${seconds(numberAt(total, 'p90'))}`}/><SummaryRow label="rewrite avg / p90" value={`${seconds(numberAt(rewrite, 'avg'))} / ${seconds(numberAt(rewrite, 'p90'))}`}/><SummaryRow label="irodori avg / p90" value={`${seconds(numberAt(irodori, 'avg'))} / ${seconds(numberAt(irodori, 'p90'))}`}/><SummaryRow label="server avg / p90" value={`${seconds(numberAt(server, 'avg'))} / ${seconds(numberAt(server, 'p90'))}`}/><SummaryRow label="other avg / p90" value={`${seconds(numberAt(other, 'avg'))} / ${seconds(numberAt(other, 'p90'))}`}/></div>
    </section>
  </section>;
}
