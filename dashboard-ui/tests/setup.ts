import '@testing-library/jest-dom/vitest';
import {cleanup} from '@testing-library/react';
import {afterEach, vi} from 'vitest';

vi.mock('chart.js/auto', () => ({
  default: class MockChart {
    data = {
      labels: [] as string[],
      datasets: [
        {data: [] as number[]},
        {data: [] as number[]},
        {data: [] as number[]},
      ],
    };
    update() {}
    destroy() {}
  },
}));

vi.mock('@/components/dither-kit/sparkline', () => ({
  Sparkline: () => null,
}));

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
});
class TestResizeObserver {
  observe() {}
  disconnect() {}
  unobserve() {}
}
if (!globalThis.ResizeObserver) globalThis.ResizeObserver = TestResizeObserver as unknown as typeof ResizeObserver;
HTMLCanvasElement.prototype.getContext = (() => ({
  clearRect() {},
  fillRect() {},
  beginPath() {},
  moveTo() {},
  lineTo() {},
  stroke() {},
  fill() {},
  save() {},
  restore() {},
  setTransform() {},
  createLinearGradient: () => ({addColorStop() {}}),
  measureText: () => ({width: 0}),
}) as unknown as CanvasRenderingContext2D) as unknown as typeof HTMLCanvasElement.prototype.getContext;
