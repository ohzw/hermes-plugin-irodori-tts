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

  it('renders a grouped bar chart once two timing samples are available', () => {
    render(<Overview status={{recent: [
      {request_id: 'latest', ts: '2026-07-11T15:00:00Z', timing_ms: {rewrite: 200, irodori_request: 900, total: 1200}},
      {request_id: 'previous', ts: '2026-07-10T15:00:00Z', timing_ms: {rewrite: 100, irodori_request: 800, total: 1000}},
    ]}} />);

    expect(screen.getByTestId('bar-chart-root')).toBeInTheDocument();
    expect(screen.getByTestId('bar-total')).toHaveAttribute('data-variant', 'gradient');
    expect(screen.getByTestId('bar-irodori')).toHaveAttribute('data-variant', 'dotted');
    expect(screen.getByTestId('bar-rewrite')).toHaveAttribute('data-variant', 'hatched');
    expect(chartProps.current?.stackType).toBe('default');
  });

  it('uses distinct bar variants and orders samples oldest to newest', () => {
    render(<Overview status={{recent: [
      {request_id: 'new', ts: '2026-07-11T15:00:00Z', timing_ms: {rewrite: 2, irodori_request: 18, total: 20}},
      {request_id: 'middle', ts: '2026-07-10T18:00:00Z', timing_ms: {rewrite: 1.5, irodori_request: 13, total: 15}},
      {request_id: 'old', ts: '2026-07-10T15:00:00Z', timing_ms: {rewrite: 1, irodori_request: 9, total: 10}},
    ]}} />);

    expect(screen.getByTestId('bar-total')).toHaveAttribute('data-variant', 'gradient');
    expect(screen.getByTestId('bar-irodori')).toHaveAttribute('data-variant', 'dotted');
    expect(screen.getByTestId('bar-rewrite')).toHaveAttribute('data-variant', 'hatched');
    expect(screen.getByTestId('bar-irodori')).toHaveAttribute('data-stroke', 'solid');
    expect(screen.getByTestId('bar-rewrite')).toHaveAttribute('data-stroke', 'dashed');
    expect(chartProps.current?.bloom).toBe('low');
    expect((chartProps.current?.config as Record<string, {color: string}>).total.color).toBe('blue');
    expect((chartProps.current?.config as Record<string, {color: string}>).irodori.color).toBe('purple');
    expect((chartProps.current?.data as Array<{total: number}>).map(item => item.total)).toEqual([10, 15, 20]);
  });
});
