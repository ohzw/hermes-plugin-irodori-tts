"use client"

import { BarCanvas } from "./bar-canvas"
import { type CartesianChartProps, CartesianRoot } from "./cartesian-root"

// Keep this aligned with the locally installed CartesianRoot version.
type Row = Record<string, unknown>

/** Composable dither **bar** chart — `<Bar>` series, grouped or stacked. */
export function BarChart<TData extends Row>(props: CartesianChartProps<TData>) {
  return <CartesianRoot chartType="bar" Canvas={BarCanvas} {...props} />
}
