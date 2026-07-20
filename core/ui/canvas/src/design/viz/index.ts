// core/ui/canvas/src/design/viz/index.ts
//
// The visualization primitives — ACE's charting surface.
//
// This is a KERNEL primitive (Apache-2.0), not an extension's private code: any
// extension that can emit the shapes in ./types can drive it. The engine renders in
// pure React + SVG (no charting library, no canvas 2D, no WebGL) into a 0..100
// viewBox, so it scales to any container and every mark is inspectable in the DOM.
//
// Colors come exclusively from Layer 4 --ace-chart-* tokens, mirrored in
// ./chartTokens as numeric RGB channels because a data chart does color MATH — an
// intensity ramp multiplies a hue by a computed alpha, and you cannot multiply a
// var() string. __enforcement__/chartTokensParity.test.ts holds the two in sync.

// The renderer
export { PriceChart } from './PriceChart'
export type { OIProfileMode, ZoneMethod } from './PriceChart'
export { WindParticleLayer } from './WindParticleLayer'
export type { ParticleShape } from './WindParticleLayer'
export { ChartLabelsOverlay } from './ChartLabelsOverlay'
export { LisBandLayer } from './LisBandLayer'
// Signed-proportion + directional-ramp primitives. Generic: the kernel does not know what
// a greek is. A consuming extension composes them into its own read panel.
export { SplitBar } from './SplitBar'
export type { SplitBarProps } from './SplitBar'
export { RampBars } from './RampBars'
export type { RampBarsProps } from './RampBars'
export { useChartViewport } from './useChartViewport'

// Tokens + color math
export {
  chartInk,
  chartLayout,
  chartNumericFont,
  hues,
  rgb,
  rgba,
  DIFF_CALL_COLOR,
  DIFF_PUT_COLOR,
  FUTURE_LIS_COLOR,
  ROLL3_LIS_COLOR,
  SHORT_TERM_COLOR,
} from './chartTokens'
export type { HueName, Rgb } from './chartTokens'

// Derivation (pure, tested — the chart's brain)
export { selectFlowProfile } from './flowProfile'
export type { FlowCell, FlowHue } from './flowProfile'
export { windToParticles } from './windParticles'
export type { ParticleDrive } from './windParticles'
export { ladderCascades } from './cascadeZones'
export { wallLabels } from './chartLabels'

// The data contract
export type * from './types'
