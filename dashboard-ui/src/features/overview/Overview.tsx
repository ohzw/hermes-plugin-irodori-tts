import type {Status} from '../../shared/api';
import {BarChart} from '../../components/dither-kit/bar-chart';
import {Bar} from '../../components/dither-kit/bar';
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

function TimingVisualization({data}: {data: Array<{index: number; label: string; rewrite: number; irodori: number; total: number}>}) {
  if (data.length === 0) {
    return <div className="timing-state timing-empty"><strong>No timing samples yet</strong><span>Generate speech to start a real latency trace.</span></div>;
  }
  if (data.length === 1) {
    const latest = data.at(-1)!;
    return <div className="timing-state latest-timing"><div className="latest-timing-heading"><strong>Latest request timing</strong><span>{latest.label}</span></div><div className="latest-timing-grid"><div><span>Total</span><strong>{seconds(latest.total)}</strong></div><div><span>Irodori</span><strong>{seconds(latest.irodori)}</strong></div><div><span>Rewrite</span><strong>{seconds(latest.rewrite)}</strong></div></div></div>;
  }
  return <BarChart data={data} config={{rewrite:{label:'Rewrite',color:'grey'}, irodori:{label:'Irodori',color:'purple'}, total:{label:'Total',color:'blue'}}} stackType="default" margins={{top:30,right:20,bottom:28,left:52}} bloom="low" replayOnDataChange={false} className="overview-chart-canvas"><Grid horizontal vertical={false}/><Bar dataKey="total" variant="gradient" strokeVariant="solid"/><Bar dataKey="irodori" variant="dotted" strokeVariant="solid"/><Bar dataKey="rewrite" variant="hatched" strokeVariant="dashed"/><XAxis dataKey="label" maxTicks={6}/><YAxis tickFormatter={axisDuration}/><Legend isClickable align="right"/><Tooltip labelKey="label" valueFormatter={(value) => axisDuration(value)} /></BarChart>;
}

export function Overview({status}: {status: Status}) {
  const summary = record(status.summary); const total = record(summary.total_ms); const rewrite = record(summary.rewrite_ms); const irodori = record(summary.irodori_request_ms); const server = record(summary.server_start_or_health_ms); const other = record(summary.other_ms);
  const threshold = Number(status.slow_threshold_ms ?? 0);
  const chartData = [...(status.recent ?? [])].reverse().flatMap((item, index) => {
    const timing = item.timing_ms ?? {};
    const total = Number(timing.total);
    if (timing.total == null || !Number.isFinite(total)) return [];
    return [{ index: index + 1, label: chartLabel(item.ts || item.created_at, index), rewrite: Number(timing.rewrite ?? 0), irodori: Number(timing.irodori_request ?? 0), total }];
  });
  return <section className="tab-view active overview-surface" data-testid="overview-surface">
    <div className="page-heading"><div><div className="eyebrow">OVERVIEW / TELEMETRY</div><h2>Performance overview</h2><p>Inspect the latest voice requests without leaving the local console.</p></div><span className="panel-hint">直近30件</span></div>
    <section className="metric-strip" aria-label="パフォーマンス概要">
      <div className="metric-card"><span className="metric-label">平均レイテンシー</span><strong className="metric-value">{seconds(numberAt(total, 'avg'))}</strong><span className="metric-note">直近の成功リクエスト</span></div>
      <div className="metric-card"><span className="metric-label">主なボトルネック</span><strong className="metric-value metric-accent">{String(summary.bottleneck ?? 'n/a')}</strong><span className="metric-note">{status.recommendation || '計測結果を読み込み中'}</span></div>
      <div className="metric-card metric-threshold"><span className="metric-label">Slow threshold</span><strong className="metric-value">{seconds(threshold)}</strong><span className="metric-note">超過したリクエストを警告表示</span></div>
    </section>
    <section className="panel performance-panel dither-panel"><div className="panel-header"><div><div className="eyebrow">OBSERVE / {chartData.length >= 2 ? 'DITHER TRACE' : 'TIMING TRACE'}</div><h2>Rewrite / Irodori processing</h2></div><span className="panel-hint">直近30件</span></div>
      <div className="chart-card overview-chart"><div className="chart-title"><strong>処理時間の推移</strong><span className="legend-hint">{chartData.length >= 2 ? 'ms · hover for exact values' : 'latest request · ms'}</span></div>
        <TimingVisualization data={chartData} />
      </div>
      <div className="summary-grid"><SummaryRow label="runs" value={`${Number(summary.ok_runs ?? 0)} ok / ${Number(summary.error_runs ?? 0)} errors`}/><SummaryRow label="total avg / p90" value={`${seconds(numberAt(total, 'avg'))} / ${seconds(numberAt(total, 'p90'))}`}/><SummaryRow label="rewrite avg / p90" value={`${seconds(numberAt(rewrite, 'avg'))} / ${seconds(numberAt(rewrite, 'p90'))}`}/><SummaryRow label="irodori avg / p90" value={`${seconds(numberAt(irodori, 'avg'))} / ${seconds(numberAt(irodori, 'p90'))}`}/><SummaryRow label="server avg / p90" value={`${seconds(numberAt(server, 'avg'))} / ${seconds(numberAt(server, 'p90'))}`}/><SummaryRow label="other avg / p90" value={`${seconds(numberAt(other, 'avg'))} / ${seconds(numberAt(other, 'p90'))}`}/></div>
    </section>
  </section>;
}
