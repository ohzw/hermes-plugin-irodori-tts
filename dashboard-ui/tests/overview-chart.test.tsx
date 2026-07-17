import {render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {Overview} from '../src/features/overview/Overview';

const chartProps = vi.hoisted(() => ({current: null as null | Record<string, unknown>}));

vi.mock('../src/components/dither-kit/bar-chart', () => ({
  BarChart: (props: Record<string, unknown>) => {
    chartProps.current = props;
    return <div data-testid="bar-chart-root">{props.children as React.ReactNode}</div>;
  },
}));
vi.mock('../src/components/dither-kit/bar', () => ({
  Bar: ({dataKey, variant, strokeVariant}: {dataKey: string; variant?: string; strokeVariant?: string}) => <div data-testid={`bar-${dataKey}`} data-variant={variant} data-stroke={strokeVariant} />,
}));
vi.mock('../src/components/dither-kit/x-axis', () => ({XAxis: () => null}));
vi.mock('../src/components/dither-kit/y-axis', () => ({YAxis: () => null}));
vi.mock('../src/components/dither-kit/legend', () => ({Legend: () => null}));
vi.mock('../src/components/dither-kit/tooltip', () => ({Tooltip: () => null}));
vi.mock('../src/components/dither-kit/grid', () => ({Grid: () => null}));

describe('Overview timing chart', () => {
  it('shows an empty state instead of mounting a chart without timing samples', () => {
    render(<Overview status={{recent: []}} />);

    expect(screen.getByText('No timing samples yet')).toBeInTheDocument();
    expect(screen.queryByTestId('bar-chart-root')).not.toBeInTheDocument();
  });

  it('shows a latest-request breakdown for a single sample', () => {
    render(<Overview status={{recent: [
      {request_id: 'latest', ts: '2026-07-11T15:00:00Z', timing_ms: {rewrite: 200, irodori_request: 900, total: 1200}},
    ]}} />);

    expect(screen.getByText('Latest request timing')).toBeInTheDocument();
    expect(screen.getByText('1.20s')).toBeInTheDocument();
    expect(screen.queryByTestId('bar-chart-root')).not.toBeInTheDocument();
  });

  it('renders a semantic timing stack once two samples are available', () => {
    render(<Overview status={{recent: [
      {request_id: 'latest', ts: '2026-07-11T15:00:00Z', timing_ms: {rewrite: 200, irodori_request: 900, total: 1200}},
      {request_id: 'previous', ts: '2026-07-10T15:00:00Z', timing_ms: {rewrite: 100, irodori_request: 800, total: 1000}},
    ]}} />);

    expect(screen.getByTestId('bar-chart-root')).toBeInTheDocument();
    expect(screen.queryByTestId('bar-total')).not.toBeInTheDocument();
    expect(screen.getByTestId('bar-rewrite')).toHaveAttribute('data-variant', 'dotted');
    expect(screen.getByTestId('bar-irodori')).toHaveAttribute('data-variant', 'gradient');
    expect(screen.getByTestId('bar-other')).toHaveAttribute('data-variant', 'hatched');
    expect(chartProps.current?.stackType).toBe('stacked');
    expect(screen.getByText('stack height = Total')).toBeInTheDocument();
  });

  it('uses distinct bar variants and orders samples oldest to newest', () => {
    render(<Overview status={{recent: [
      {request_id: 'new', ts: '2026-07-11T15:00:00Z', timing_ms: {rewrite: 2, irodori_request: 18, total: 25}},
      {request_id: 'middle', ts: '2026-07-10T18:00:00Z', timing_ms: {rewrite: 1.5, irodori_request: 13, total: 20}},
      {request_id: 'old', ts: '2026-07-10T15:00:00Z', timing_ms: {rewrite: 1, irodori_request: 9, total: 12}},
    ]}} />);

    expect(screen.getByTestId('bar-rewrite')).toHaveAttribute('data-variant', 'dotted');
    expect(screen.getByTestId('bar-irodori')).toHaveAttribute('data-variant', 'gradient');
    expect(screen.getByTestId('bar-other')).toHaveAttribute('data-variant', 'hatched');
    expect(screen.getByTestId('bar-irodori')).toHaveAttribute('data-stroke', 'solid');
    expect(screen.getByTestId('bar-other')).toHaveAttribute('data-stroke', 'dashed');
    expect(chartProps.current?.bloom).toBe('low');
    const config = chartProps.current?.config as Record<string, {color: string}>;
    expect(config.rewrite.color).toBe('purple');
    expect(config.irodori.color).toBe('blue');
    expect(config.other.color).toBe('grey');
    expect((chartProps.current?.data as Array<{total: number}>).map(item => item.total)).toEqual([12, 20, 25]);
    expect((chartProps.current?.data as Array<{other: number}>).map(item => item.other)).toEqual([2, 5.5, 5]);
  });
});
