import {describe, expect, it} from 'vitest';
import {seriesPaintOrder} from '../src/components/dither-kit/cartesian-canvas';

describe('dither series paint order', () => {
  it('paints later aggregate series behind earlier component series', () => {
    const legendOrder = ['rewrite', 'irodori', 'total'];

    expect(seriesPaintOrder(legendOrder)).toEqual(['total', 'irodori', 'rewrite']);
    expect(legendOrder).toEqual(['rewrite', 'irodori', 'total']);
  });
});
