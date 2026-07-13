import {render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {Overview} from '../src/features/overview/Overview';

const chartProps = vi.hoisted(() => ({current: null as null | Record<string, unknown>}));

vi.mock('../src/components/dither-kit/area-chart', () => ({
  AreaChart: (props: Record<string, unknown>) => {
    chartProps.current = props;
    return <div data-testid="chart-root">{props.children as React.ReactNode}</div>;
  },
}));
vi.mock('../src/components/dither-kit/area', () => ({
  Area: ({dataKey, variant}: {dataKey: string; variant?: string}) => <div data-testid={`area-${dataKey}`} data-variant={variant} />,
  Line: ({dataKey, variant, strokeVariant}: {dataKey: string; variant?: string; strokeVariant?: string}) => <div data-testid={`line-${dataKey}`} data-variant={variant} data-stroke={strokeVariant} />,
}));
vi.mock('../src/components/dither-kit/x-axis', () => ({XAxis: () => null}));
vi.mock('../src/components/dither-kit/y-axis', () => ({YAxis: () => null}));
vi.mock('../src/components/dither-kit/legend', () => ({Legend: () => null}));
vi.mock('../src/components/dither-kit/tooltip', () => ({Tooltip: () => null}));
vi.mock('../src/components/dither-kit/grid', () => ({Grid: () => null}));

describe('Overview timing chart', () => {
  it('uses one total area with component lines and orders samples oldest to newest', () => {
    render(<Overview status={{recent: [
      {request_id: 'new', ts: '2026-07-11T15:00:00Z', timing_ms: {rewrite: 2, irodori_request: 18, total: 20}},
      {request_id: 'old', ts: '2026-07-10T15:00:00Z', timing_ms: {rewrite: 1, irodori_request: 9, total: 10}},
    ]}} />);

    expect(screen.getByTestId('area-total')).toHaveAttribute('data-variant', 'gradient');
    expect(screen.getByTestId('line-irodori')).toHaveAttribute('data-stroke', 'solid');
    expect(screen.getByTestId('line-rewrite')).toHaveAttribute('data-stroke', 'dashed');
    expect(screen.queryByTestId('area-irodori')).not.toBeInTheDocument();
    expect(screen.queryByTestId('area-rewrite')).not.toBeInTheDocument();
    expect(chartProps.current?.bloom).toBe('low');
    expect((chartProps.current?.data as Array<{total: number}>).map(item => item.total)).toEqual([10, 20]);
  });
});
