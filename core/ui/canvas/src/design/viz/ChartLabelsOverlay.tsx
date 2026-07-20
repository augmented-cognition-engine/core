// HTML overlay labels for the price chart — avoids SVG-text horizontal-stretch
// distortion under preserveAspectRatio='none'. Each label is an absolutely
// positioned <div> inside the chart's overlay container. Coordinates mirror the
// SVG viewBox 0..100 system: left/top values are percentages, matching the
// priceToY(p) → 0..100 contract. Plot-area anchors (dataEnd, annotationX) come
// from the single owner chartLayout, not local literals.

import { wallLabels } from './chartLabels'
import { chartLayout, chartInk, rgba } from './chartTokens'
import type { OIProfileView, CharmLine } from './types'

// A template literal, not a plain string: the token must be EVALUATED. Left as a
// quoted string it would emit the literal text "rgba(chartInk.scrim, 0.7)", which is
// invalid CSS — the browser drops the declaration and every label silently loses the
// shadow that makes it readable over candles.
const SHADOW = `0 0 2px ${rgba(chartInk.scrim, 0.7)}`

export function ChartLabelsOverlay({
  charmLines,
  oiProfile,
  priceToY,
  scenarioMap = null,
}: {
  charmLines: CharmLine[] | undefined
  oiProfile: OIProfileView | null
  priceToY: (p: number) => number
  /** Scenario zones attached to their price spans (Edwin 2026-07-09: the
   *  scenario-map table moved onto the chart). Label at each zone's mid-Y. */
  scenarioMap?: { zones: { lo: number; hi: number; scenario: string; play: string }[]; spot_zone?: number | null } | null
}) {
  // When warming (no prior same-expiry snapshot), oiFlowLabel/wallLabels
  // already short-circuit (no fabricated flow/wall Δ). That suppression stays
  // SILENT — the old "warming — posture only" chip was GE-era cold-start
  // signage and read as noise under theta (Edwin 2026-07-09), where the flow
  // story lives in the Flow strip anyway.
  const walls = oiProfile ? wallLabels(oiProfile) : []
  return (
    <>
      {/* Scenario zones — labels attached to their price spans (left column).
          Spot's zone renders bright; the others dim. Boundary rules are SVG
          (ScenarioZoneLayer in PriceChart); these are the words. */}
      {(scenarioMap?.zones ?? []).map((z, i) => {
        const y = priceToY((z.lo + z.hi) / 2)
        if (!isFinite(y)) return null
        const inSpot = scenarioMap?.spot_zone === i
        return (
          <div
            key={`zone-${z.lo}-${z.hi}`}
            className="absolute font-data text-annotation"
            title={z.play}
            style={{
              left: `${chartLayout.annotationX}%`,
              top: `${y}%`,
              transform: 'translateY(-50%)',
              opacity: inSpot ? 0.95 : 0.55,
              whiteSpace: 'nowrap',
              textShadow: SHADOW,
              color: 'var(--ace-ink-muted)',
              fontWeight: inSpot ? 600 : 400,
            }}
          >
            {z.scenario}
          </div>
        )
      })}
      {/* Charm line labels — right of data area (x ≈ X_DATA_END + 0.6%) */}
      {(charmLines ?? []).map((cl, i) => {
        const y = priceToY(cl.price_contract)
        if (!isFinite(y)) return null
        return (
          <div
            key={`charm-${i}`}
            className="absolute font-data text-annotation text-charm"
            style={{
              left: `${chartLayout.dataEnd + 0.6}%`,
              top: `${y}%`,
              transform: 'translateY(-50%)',
              opacity: 0.9,
              whiteSpace: 'nowrap',
              textShadow: SHADOW,
            }}
          >
            {cl.label} {cl.price_contract.toFixed(0)}
          </div>
        )
      })}

      {/* Wall Δ tags — left edge (x ≈ 1.5%), major clusters above noise floor */}
      {walls.map((w, i) => {
        const y = priceToY(w.strike)
        if (!isFinite(y)) return null
        return (
          <div
            key={`wall-${i}`}
            className={`absolute font-data text-annotation ${w.built ? 'text-built' : 'text-drained'}`}
            style={{
              left: `${chartLayout.annotationX}%`,
              top: `${y - 0.7}%`,
              transform: 'translateY(-50%)',
              opacity: 0.95,
              whiteSpace: 'nowrap',
              textShadow: SHADOW,
            }}
          >
            {w.text}
          </div>
        )
      })}

    </>
  )
}
