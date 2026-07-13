import {render} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {Line} from '../src/components/dither-kit/area';
import {ChartContext, type ChartContextValue} from '../src/components/dither-kit/chart-context';

describe('mixed continuous chart series', () => {
  it('allows a line series in an area chart context', () => {
    const context = {
      chartType: 'area',
      config: {component: {label: 'Component', color: 'purple'}},
      registerSeries: vi.fn(),
      unregisterSeries: vi.fn(),
      bands: {},
      ready: false,
    } as unknown as ChartContextValue;

    expect(() => render(
      <ChartContext value={context}>
        <Line dataKey="component" />
      </ChartContext>,
    )).not.toThrow();
  });
});
