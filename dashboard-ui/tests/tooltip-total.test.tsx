import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {CommonChartContext, type CommonChart} from '../src/components/dither-kit/common-context';
import {Tooltip} from '../src/components/dither-kit/tooltip';
import {PALETTE} from '../src/components/dither-kit/palette';

describe('Dither chart tooltip totals', () => {
  it('shows the sum of stacked segments as Total', () => {
    const chart: CommonChart = {
      names: ['rewrite', 'irodori', 'other'],
      labelOf: name => name,
      seedOf: () => PALETTE.blue,
      selectedDataKey: null,
      selectDataKey: () => undefined,
      focusDataKey: null,
      setFocusDataKey: () => undefined,
      hoverIndex: 0,
      heading: () => '07/17, 12:00 PM',
      itemsAt: () => [
        {name: 'rewrite', label: 'Rewrite', value: 200, seed: PALETTE.purple, dimmed: false},
        {name: 'irodori', label: 'Irodori', value: 900, seed: PALETTE.blue, dimmed: false},
        {name: 'other', label: 'Other / overhead', value: 100, seed: PALETTE.grey, dimmed: false},
      ],
      ready: true,
      tooltipLeft: 100,
      tooltipTop: 100,
    };

    render(
      <CommonChartContext value={chart}>
        <Tooltip showTotal totalLabel="Total" valueFormatter={value => `${value}ms`} />
      </CommonChartContext>,
    );

    expect(screen.getByText('Total')).toBeInTheDocument();
    expect(screen.getByText('1200ms')).toBeInTheDocument();
  });
});
