import { useEffect, useMemo, useRef, useState } from 'react'
import {
  robustSigma,
  spotWindowIndices,
  VA_COLOR_DELTA,
  VA_COLOR_CHARM,
  VA_COLOR_VANNA,
  medianStrikeGap,
  padBand,
  SAT_SIGMA,
  OI_ALPHA_FLOOR,
  OI_ALPHA_CEIL,
  sigmaTierMag,
  intensityAlpha,
} from './chartMath'
import {
  FUTURE_LIS_COLOR,
  ROLL3_LIS_COLOR,
  SHORT_TERM_COLOR,
  chartInk,
  hues as tokenHues,
  rgb,
  rgba,
} from './chartTokens'
import type {
  CandlePoint,
  CascadeBand,
  CentroidBand,
  ChartData,
  LinePoint,
  LinregLine,
  OIProfileView,
  WindRead,
} from './types'
import { useChartViewport, type Viewport } from './useChartViewport'
import { ladderCascades } from './cascadeZones'
import { ChartLabelsOverlay } from './ChartLabelsOverlay'
import { WindParticleLayer } from './WindParticleLayer'
import { windToParticles } from './windParticles'
import { LisBandLayer } from './LisBandLayer'
import { gaussianKernel, convolveSame } from './chartCorridor'
import { selectFlowProfile } from './flowProfile'

/**
 * PriceChart — pure React + SVG implementation.
 *
 * Replaces the earlier Lightweight Charts attempt: too much friction
 * customising the visual layers we need (translucent density bands,
 * marching-ants linregs, custom level pills). This implementation owns
 * every pixel directly via SVG primitives, mirroring the legacy
 * live_read_legacy.py `_build_price_path` ladder's visual semantics:
 *
 *   - viewBox 0..100 with preserveAspectRatio='none', so coordinates
 *     are percentages of the chart area
 *   - Data layers (bands, candles, VWAPs, linregs, levels) all drawn
 *     as SVG primitives — polygons, polylines, rects, lines
 *   - Axis labels (price + time) rendered as HTML overlay divs
 *     positioned absolutely (SVG <text> distorts under
 *     preserveAspectRatio='none')
 *   - Time mapping: PT session 06:30 → 13:00, x=0..82
 *   - Price mapping: data range + ±2% padding, y=4..93
 *
 * This is also the foundation for Phase 5 (trade-from-screen) since
 * SVG primitives accept click/drag handlers natively.
 */

// ── Coordinate system ───────────────────────────────────────────────────────

const X_DATA_END = 82   // right edge of data area (0..100 viewBox); 82..100 left for level labels
const Y_DATA_TOP = 4    // top padding
const Y_DATA_BOTTOM = 93 // bottom of data area (above time axis strip)
const Y_DATA_HEIGHT = Y_DATA_BOTTOM - Y_DATA_TOP  // 89

// PT timezone constant for tick formatting.
const PT_TZ = 'America/Los_Angeles'

// ── Band fill opacities — denser toward the median ──────────────────────────

const BAND_FILL_OPAC: Record<string, number> = {
  '10-20': 0.06,
  '20-30': 0.10,
  '30-40': 0.16,
  '40-50': 0.22,
}

// Tape wing fills fade with distance so the deep tail reads as atmosphere.
const TAPE_FILL_OPAC: Record<string, number> = {
  '50-75': 0.16,
  '75-90': 0.09,
  '90-95': 0.045,
}
const TAPE_VWAP_COLOR = rgb(chartInk.tape) // violet — the tape LIS slot in the LIS vocab

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Format a UNIX epoch as PT HH:MM (24-hour, no leading zero on hour).
 */
function epochToPtLabel(epoch: number): string {
  const s = new Date(epoch * 1000).toLocaleTimeString('en-US', {
    timeZone: PT_TZ,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  return s.replace(/^0/, '')
}

/**
 * Generate evenly-spaced time-axis ticks across the visible viewport.
 * Step is chosen by viewport duration so the chart shows ~3-8 ticks at
 * any zoom level. Pure: returns ticks in epoch seconds.
 */
function computeTimeTicks(viewport: Viewport): Array<{ epoch: number; label: string }> {
  const range = viewport.end - viewport.start
  let stepMin: number
  if (range <= 15 * 60) stepMin = 2
  else if (range <= 30 * 60) stepMin = 5
  else if (range <= 60 * 60) stepMin = 10
  else if (range <= 2 * 60 * 60) stepMin = 15
  else if (range <= 4 * 60 * 60) stepMin = 30
  else if (range <= 8 * 60 * 60) stepMin = 60
  else stepMin = 120
  const stepSec = stepMin * 60
  const startTick = Math.ceil(viewport.start / stepSec) * stepSec
  const ticks: Array<{ epoch: number; label: string }> = []
  for (let t = startTick; t <= viewport.end && ticks.length < 12; t += stepSec) {
    ticks.push({ epoch: t, label: epochToPtLabel(t) })
  }
  return ticks
}

/**
 * Compute scale functions given a price range + viewport. Returns
 * timeToX/priceToY. timeToX maps relative to the *current viewport*,
 * not a fixed session — so panning + zooming "just work."
 */
function makeScales(yMin: number, yMax: number, viewport: Viewport) {
  const yRange = (yMax - yMin) || 1
  const tRange = (viewport.end - viewport.start) || 1
  return {
    timeToX: (epoch: number): number => {
      const frac = (epoch - viewport.start) / tRange
      return frac * X_DATA_END
    },
    priceToY: (p: number): number => {
      const frac = (yMax - p) / yRange
      return Y_DATA_TOP + Math.max(-50, Math.min(150, frac)) * Y_DATA_HEIGHT
    },
  }
}

// ── Main component ──────────────────────────────────────────────────────────

export type OIProfileMode = 'total' | 'call' | 'put' | 'net' | 'change'
export type ZoneMethod = 'va' | 'fwhm' | 'hvn' | 'slope' | 'mountain' | 'auto'

export function PriceChart({
  data,
  oiProfile,
  height = 720,
  profileWidth = OI_BAR_WIDTH_DEFAULT,
  ratioScale = 1.0,
  showCOTM = true,
  oiMode = 'total',
  secondaryGreek = 'delta',
  showPresent = true,
  showSierraVwap = true,
  showOtmVwap = false,
  tapeLens = 'anchored',
  showRoll5 = true,
  showRoll3 = true,
  flowSmooth = 3,
  oiSmooth = 3,
  greekSmooth = null,
  scenarioMap = null,
  spot = null,
  windRead = null,
}: {
  data: ChartData
  oiProfile?: OIProfileView | null
  height?: number
  profileWidth?: number
  /** Color-saturation tanh scale, shared by all five profile layers.
   *  Affects color intensity only — bar length is always linear-normalized
   *  per profile, so changing this knob never warps bar sizes. */
  ratioScale?: number
  showCOTM?: boolean
  /** What the OI profile (left strip) displays:
   *   'total' — current smoothed_total + net_oi coloring + multi-peak VAs
   *   'call'  — smoothed_call (single-side green) + va_call (POC=COI, VAH=COTMC)
   *   'put'   — smoothed_put  (single-side red)   + va_put  (POC=POI, VAL=COTMP) */
  oiMode?: OIProfileMode
  /** Which initiator-Greek renders in the far-right secondary slot. */
  secondaryGreek?: SecondaryGreek
  /** Show the present (0DTE) OI profile strip. Default on. */
  showPresent?: boolean
  /** Show the Sierra futures daily RTH VWAP (pink line). Default on. */
  showSierraVwap?: boolean
  /** OTM vwap dashed mean — observation-only checkbox (default off). */
  showOtmVwap?: boolean
  /** Tape wing/center lens: anchored (cumulative session pools) or flow
   *  (45min-half-life age decay — breathes with the current tape). The
   *  solid full-chain violet VWAP is always anchored. */
  tapeLens?: 'anchored' | 'flow' 
  /** Rolling-LIS overlays (LIS zone only, NO profile — Edwin 2026-07-09):
   *  flip zones of the standing next-5 (cyan) / next-3 (teal) books beyond
   *  today. Both default ON to A/B live; drop one later. */
  showRoll5?: boolean
  showRoll3?: boolean
  /** Flow strip SHAPE smoothing radius (bar length only). Color + LIS stay
   *  pinned at r=3 so hue and the amber core always agree. */
  flowSmooth?: number
  /** 0DTE profile SHAPE re-smooth (null = server r=6; DEFAULT 3 — Edwin
   *  2026-07-09 "default to 3 smoothing for everything"). Shape only —
   *  color/LIS/walls/peaks stay server-pinned. */
  oiSmooth?: number | null
  /** Greek profiles (gamma + secondary) shape re-smooth (null = server r=3).
   *  Server states/peaks/VAs stay doctrine-pinned; leg-split mirror untouched. */
  greekSmooth?: number | null
  /** Scenario zones attached to their price spans (boundary rules + left
   *  labels via the overlay) — the scenario-map table moved on-chart. */
  scenarioMap?: { zones: { lo: number; hi: number; scenario: string; play: string }[]; spot_zone?: number | null } | null
  /** Index-scale spot (spot_qqq). Centers the OI-profile normalization window. */
  spot?: number | null
  windRead?: WindRead | null
}) {
  // Cascade zones: the GE-fed list has been empty since 2026-06-04 (retired); the
  // theta transition ladder's cascade_id clusters feed the same striped grammar.
  // Only clusters draw — isolated crossings carry no zone.
  const cascades = data.cascades.length > 0
    ? data.cascades
    : ladderCascades(data.transition_ladder, spot, data.strike_spacing)

  // Default viewport = full session (06:30 → 13:00 PT). The linregs are
  // the authoritative source for these epoch values (the backend already
  // computed session open/close from today's date there).
  const { defaultStart, defaultEnd } = useMemo(() => {
    if (data.linregs.length > 0) {
      return {
        defaultStart: data.linregs[0].open_time,
        defaultEnd: data.linregs[0].close_time,
      }
    }
    const tv = data.tape_vwap ?? []
    if (tv.length > 0) {
      // Session viewport from the tape line: open = first block, close = open + 6.5h
      return { defaultStart: tv[0].time, defaultEnd: tv[0].time + 23400 }
    }
    const firstBar = data.bars[0]?.time
    return {
      defaultStart: firstBar ?? 0,
      defaultEnd: (firstBar ?? 0) + 23400, // 6.5 hours fallback
    }
  }, [data])

  // Outer bounds for clamping (we allow some right-side projection space
  // past the latest data so EWMA endpoint chips stay visible on zoom-out).
  const { dataMin, dataMax } = useMemo(() => {
    const firstBar = data.bars[0]?.time
    const lastBar = data.bars[data.bars.length - 1]?.time
    return {
      dataMin: Math.min(defaultStart, firstBar ?? defaultStart),
      dataMax: Math.max(defaultEnd, lastBar ?? defaultEnd),
    }
  }, [data, defaultStart, defaultEnd])

  // Ref the hook reads at gesture time to anchor y-zoom at the cursor's
  // current price. Updated below once we know the effective y bounds.
  const effectiveYRef = useRef({ yMin: 0, yMax: 1 })

  const { viewport, reset, isDragging, dragAxis, svgRef, handlers } = useChartViewport({
    dataMin,
    dataMax,
    defaultStart,
    defaultEnd,
    effectiveY: effectiveYRef,
  })

  // Y bounds: explicit viewport overrides take priority; otherwise auto-fit
  // from data visible inside the current x-viewport.
  const { yMin, yMax } = useMemo(() => {
    if (viewport.yMin != null && viewport.yMax != null) {
      return { yMin: viewport.yMin, yMax: viewport.yMax }
    }
    return computePriceRange(data, viewport)
  }, [data, viewport])

  // Keep the ref in sync so the hook can read current bounds during
  // shift+wheel / shift+drag gestures.
  useEffect(() => {
    effectiveYRef.current = { yMin, yMax }
  }, [yMin, yMax])

  const { timeToX, priceToY } = useMemo(
    () => makeScales(yMin, yMax, viewport),
    [yMin, yMax, viewport],
  )

  const yTicks = useMemo(() => computeYTicks(yMin, yMax), [yMin, yMax])
  const xTicks = useMemo(() => computeTimeTicks(viewport), [viewport])

  // Crosshair state — null when mouse is outside the chart OR mid-drag.
  // Stored in viewBox coords (0..100). Tooltip text via inverse maps.
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null)

  function onMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current
    if (!svg) return
    // Suppress crosshair while panning — it'd lag behind and feel wrong.
    if (isDragging()) {
      if (cursor !== null) setCursor(null)
      return
    }
    const rect = svg.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    if (x < 0 || x > X_DATA_END || y < Y_DATA_TOP || y > Y_DATA_BOTTOM) {
      setCursor(null)
    } else {
      setCursor({ x, y })
    }
  }
  function onMouseLeave() {
    setCursor(null)
  }

  // Inverse helpers for tooltip read-out.
  const yToPrice = (y: number): number =>
    yMax - ((y - Y_DATA_TOP) / Y_DATA_HEIGHT) * (yMax - yMin)
  const xToPtLabel = (x: number): string => {
    const epoch = viewport.start + (x / X_DATA_END) * (viewport.end - viewport.start)
    return epochToPtLabel(epoch)
  }

  // ── Wind particle drives ─────────────────────────────────────────────────
  // Theta view: both winds come from the self-computed wind_read (the better read).
  // GE view (windRead null): charm stays on GE's charm_centroid (unchanged), no vanna.
  const cc = oiProfile?.charm_centroid
  const charmDrive = windRead
    ? windToParticles(windRead.charm)
    : {
        intensity: cc?.intensity ?? 0,
        direction: (cc?.push == null || cc.push === 0
          ? 'none'
          : cc.push > 0
          ? 'up'
          : 'down') as 'up' | 'down' | 'none',
      }
  const vannaDrive = windToParticles(windRead?.vanna)

  return (
    <div className="flex items-stretch w-full" style={{ height }}>
      {/* Scenario zone CARDS — left gutter, each card's top/bottom aligned to
          its zone's prices (Edwin 2026-07-09: "the three scenarios as cards,
          tops and bottoms aligning with their prices; hover shows the whole
          thing"). Shares this chart's priceToY, so cards track pan/zoom. */}
      {scenarioMap && scenarioMap.zones.length > 0 && (
        <div className="relative w-40 shrink-0 mr-1">
          {scenarioMap.zones.map((z, i) => {
            const yTopRaw = priceToY(z.hi)
            const yBotRaw = priceToY(z.lo)
            if (!isFinite(yTopRaw) || !isFinite(yBotRaw)) return null
            const yTop = Math.max(0, Math.min(100, yTopRaw))
            const yBot = Math.max(0, Math.min(100, yBotRaw))
            if (yBot - yTop < 0.5) return null
            const inSpot = scenarioMap.spot_zone === i
            return (
              <div
                key={`sz-${z.lo}-${z.hi}`}
                title={`${z.hi.toFixed(2)}–${z.lo.toFixed(2)} · ${z.scenario} — ${z.play}`}
                className={`absolute left-0 right-0 overflow-hidden rounded border px-1.5 py-1 text-[10px] leading-tight ${
                  inSpot
                    ? 'border-[var(--ace-ink)] bg-[var(--ace-surface-card)] text-[var(--ace-ink)]'
                    : 'border-[var(--ace-line)] bg-[var(--ace-surface-card)] text-[var(--ace-ink-muted)] opacity-80'
                }`}
                style={{ top: `${yTop}%`, height: `${yBot - yTop}%` }}
              >
                <div className={`font-mono ${inSpot ? 'font-semibold' : ''}`}>{z.scenario}</div>
                <div className="text-[var(--ace-ink-faint)]">{z.play}</div>
              </div>
            )
          })}
        </div>
      )}
    <div
      className="relative flex-1 min-w-0 h-full rounded border border-[var(--ace-line)] bg-[var(--ace-surface-canvas)] overflow-hidden"
    >
      <svg
        ref={svgRef}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="absolute inset-0 w-full h-full"
        aria-label="Price + VWAPs + GE volume framework"
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
        onWheel={handlers.onWheel}
        onMouseDown={handlers.onMouseDown}
        style={{
          cursor: isDragging()
            ? dragAxis() === 'y'
              ? 'ns-resize'
              : 'grabbing'
            : 'grab',
        }}
      >
        {/* SVG defs for the diagonal-stripe pattern used by cascade bands.
            Two pattern variants — looser stripes for normal clusters,
            tighter for razor-thin ones. */}
        <defs>
          {/* Softer cascade stripes — wider spacing, thinner lines,
              lower opacity. The cascade is context, not signal; it
              should whisper, not shout. */}
          <pattern
            id="cascade-stripes"
            patternUnits="userSpaceOnUse"
            width="2.4"
            height="2.4"
            patternTransform="rotate(45)"
          >
            <line
              x1="0"
              y1="0"
              x2="0"
              y2="2.4"
              stroke="#fbbf24"
              strokeWidth="0.28"
              opacity="0.28"
            />
          </pattern>
          <pattern
            id="cascade-stripes-razor"
            patternUnits="userSpaceOnUse"
            width="1.6"
            height="1.6"
            patternTransform="rotate(45)"
          >
            <line
              x1="0"
              y1="0"
              x2="0"
              y2="1.6"
              stroke="#fb923c"
              strokeWidth="0.28"
              opacity="0.42"
            />
          </pattern>

          {/* GEX chop hatch — diagonal lines inside the GEX trans band.
              Visually says "low MM pressure, choppy back-and-forth." */}
          <pattern
            id="gex-chop"
            patternUnits="userSpaceOnUse"
            width="2.0"
            height="2.0"
            patternTransform="rotate(-30)"
          >
            <line
              x1="0" y1="0" x2="0" y2="2.0"
              stroke={rgba(tokenHues.gamma, 0.55)}
              strokeWidth="0.20"
            />
          </pattern>


          {/* DEX sentiment tint — narrow band just above DEX_PTRANS
              (call-dom side, green) and just below DEX_NTRANS (put-dom
              side, red). Much narrower than a full half-chart wash —
              ~3pt tall, fading away from the boundary line. */}
          <linearGradient id="dex-call-above" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%"   stopColor={rgba(tokenHues.vanna, 0.30)} />
            <stop offset="100%" stopColor={rgba(tokenHues.vanna, 0.00)} />
          </linearGradient>
          <linearGradient id="dex-put-below" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={rgba(tokenHues.put, 0.30)} />
            <stop offset="100%" stopColor={rgba(tokenHues.put, 0.00)} />
          </linearGradient>

          {/* Decay hatch — diagonal amber/desaturated stripe for the gross-mode
              "remove" diff segment: volume that left overnight (the unwind).
              Prominent (tighter spacing) to stand out as the decay signal. */}
          <pattern
            id="decay-hatch"
            patternUnits="userSpaceOnUse"
            width="1.8"
            height="1.8"
            patternTransform="rotate(45)"
          >
            <line
              x1="0"
              y1="0"
              x2="0"
              y2="1.8"
              stroke={rgba(chartInk.goldDeep, 0.70)}
              strokeWidth="0.55"
            />
          </pattern>

          {/* DS rubber-band — amber gradient strong at the DS edge,
              fades toward the trans edge. The visual metaphor: the
              further from trans, the stronger the mean-reversion pull. */}
          <linearGradient id="ds-upper-pull" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%"   stopColor={rgba(tokenHues.pin, 0.00)} />
            <stop offset="100%" stopColor={rgba(tokenHues.pin, 0.38)} />
          </linearGradient>
          <linearGradient id="ds-lower-pull" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={rgba(tokenHues.pin, 0.00)} />
            <stop offset="100%" stopColor={rgba(tokenHues.pin, 0.38)} />
          </linearGradient>
        </defs>
        {/* Horizontal price gridlines */}
        {yTicks.map(({ y }, i) => (
          <line
            key={`y-${i}`}
            x1={0}
            y1={y}
            x2={X_DATA_END}
            y2={y}
            stroke="var(--ace-line)"
            strokeWidth={0.3}
            opacity={0.4}
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {/* Vertical time gridlines — dynamic ticks from viewport */}
        {xTicks.map(({ epoch, label }) => {
          const x = timeToX(epoch)
          if (x < 0 || x > X_DATA_END) return null
          return (
            <line
              key={`x-${label}`}
              x1={x}
              y1={Y_DATA_TOP}
              x2={x}
              y2={Y_DATA_BOTTOM}
              stroke="var(--ace-line)"
              strokeWidth={0.3}
              opacity={0.25}
              strokeDasharray="0.6 1.2"
              vectorEffect="non-scaling-stroke"
            />
          )
        })}

        {/* ── Layer stack (back → front) ────────────────────────────────
            0. DEX regime wash — direction compass (call/put dominance)
            0a. Cluster bands — generic zone regions; faint when a
               specialized layer paints the same area. Hover surface.
            1. Candles — price action
            2. VWAPs — reference lines drawn on top of candles
            2a. GEX chop band — acceleration timing (chop inside,
               pressure fade outside)
            2b. DS rubber-band — mean-reversion gradient between trans
               outer edges and DS limits
            3. Cascade bands — multi-Greek flip danger (striped)
            4. Centroid density bands — translucent density on top
            5. Level horizontal lines — structural references
            6. Linregs — interactive trajectory lines, top data layer */}

        {/* v2.7 — DEX / GEX / DS trans-zone overlays removed. All structural
            zone information now derives from the smoothed OI + Gamma
            profiles on the chart's flanks; the chart's central canvas
            stays focused on price action without duplicate overlays. */}

        {/* Animated wind layers — charm (gold motes) + vanna (cyan streaks)
            SMIL particles. Both sit behind all other layers so the price
            action always paints on top. */}
        {/* Charm wind — steady gold motes (theta: wind_read.charm; GE: charm_centroid). */}
        <WindParticleLayer intensity={charmDrive.intensity} direction={charmDrive.direction} color="rgb(255,205,90)" shape="mote" />
        {/* Vanna wind — sharp cyan streaks, only when the sword is active (vol moving). */}
        <WindParticleLayer intensity={vannaDrive.intensity} direction={vannaDrive.direction} color="rgb(56,189,248)" shape="streak" />

        {/* OI Profile — sits on the LEFT (bars extend RIGHT from x=0).
            Shares the chart's Y-axis (priceToY) so peaks line up with
            price levels. Rendered behind the candles so the price action
            paints on top of the structural mass backdrop. */}
        {/* Rolling-LIS overlays — LIS zone ONLY, no profile (final spec):
            flip zones of the standing next-5 (cyan) / next-3 (teal) books
            beyond today. Both on by default to A/B live; the Present white
            LIS already carries today's flip, so these answer "where does the
            book IN FRONT of today flip". */}
        {oiProfile?.rolling_lis?.next5 && showRoll5 && (
          <g>
            <LisBandLayer
              strikes={oiProfile.rows.map((r) => r.strike)}
              lo={oiProfile.rolling_lis.next5.halo_lo}
              hi={oiProfile.rolling_lis.next5.halo_hi}
              color={FUTURE_LIS_COLOR}
              dash="1 2.5" fillAlpha={0.03} edgeAlpha={0.25} edgeWidth={0.4}
              priceToY={priceToY}
            />
            <LisBandLayer
              strikes={oiProfile.rows.map((r) => r.strike)}
              lo={oiProfile.rolling_lis.next5.lo}
              hi={oiProfile.rolling_lis.next5.hi}
              color={FUTURE_LIS_COLOR}
              dash="1.4 1.4"
              priceToY={priceToY}
            />
          </g>
        )}
        {oiProfile?.rolling_lis?.next3 && showRoll3 && (
          <g>
            <LisBandLayer
              strikes={oiProfile.rows.map((r) => r.strike)}
              lo={oiProfile.rolling_lis.next3.halo_lo}
              hi={oiProfile.rolling_lis.next3.halo_hi}
              color={ROLL3_LIS_COLOR}
              dash="1 2.5" fillAlpha={0.03} edgeAlpha={0.25} edgeWidth={0.4}
              priceToY={priceToY}
            />
            <LisBandLayer
              strikes={oiProfile.rows.map((r) => r.strike)}
              lo={oiProfile.rolling_lis.next3.lo}
              hi={oiProfile.rolling_lis.next3.hi}
              color={ROLL3_LIS_COLOR}
              dash="0.7 0.9"
              priceToY={priceToY}
            />
          </g>
        )}
        {/* OI Profile (PRESENT 0DTE) — gated by showPresent; carries the present LIS. */}
        {oiProfile && showPresent && (
          <OIProfileLayer
            profile={oiProfile}
            priceToY={priceToY}
            barWidth={profileWidth}
            ratioScale={ratioScale}
            mode={oiMode}
            spot={spot}
            smoothRadius={oiSmooth}
          />
        )}
        {/* Flow — the ALWAYS-ON secondary profile paired with the 0DTE strip
            (final spec): bar length = churn (|Δc|+|Δp|), hue = Δnet (green
            call-building / red put-building / grey balanced), plus the amber
            flow LIS full-width. Gated only by data presence + showPresent's
            sibling toggle-lessness — no checkbox. */}
        {oiProfile?.delta && (
          <FlowProfileLayer
            gridStrikes={oiProfile.rows.map((r) => r.strike)}
            delta={oiProfile.delta}
            priceToY={priceToY}
            barWidth={profileWidth}
            ratioScale={ratioScale}
            spot={spot}
            baseX={profileWidth + 2}
            smoothRadius={flowSmooth}
          />
        )}
        {/* Flow LIS = the 0DTE's two-radius definition verbatim: r=6 HALO
            (wide, faint, sparse dash — like the white halo) nested under the
            r=3 CORE. Both amber (the overnight-Δ hue). */}
        {oiProfile?.delta && (
          <LisBandLayer
            strikes={oiProfile.rows.map((r) => r.strike)}
            lo={oiProfile.delta.lis_halo_lo}
            hi={oiProfile.delta.lis_halo_hi}
            color={SHORT_TERM_COLOR}
            dash="1 2.5"
            fillAlpha={0.04}
            edgeAlpha={0.35}
            edgeWidth={0.4}
            priceToY={priceToY}
          />
        )}
        {oiProfile?.delta && (
          <LisBandLayer
            strikes={oiProfile.rows.map((r) => r.strike)}
            lo={oiProfile.delta.lis_lo}
            hi={oiProfile.delta.lis_hi}
            color={SHORT_TERM_COLOR}
            fillAlpha={0.16}
            edgeAlpha={0.95}
            glow
            priceToY={priceToY}
          />
        )}
        {/* Gamma Profile — at the right edge of the data area. Single
            signal: net_gamma drives both shape AND color. */}
        {oiProfile && (
          <GammaProfileLayer
            profile={oiProfile}
            priceToY={priceToY}
            barWidth={profileWidth}
            ratioScale={ratioScale}
            smoothRadius={greekSmooth}
          />
        )}
        {/* Secondary Greek Profile — PINNED to the right lane
            (X_DATA_END..100): leg-split mirrors around the lane center,
            single-signal bars hug x=100 growing left. Width scales bar
            length only. Swappable via `secondaryGreek`: delta | charm |
            vanna. Single signal drives shape AND color. */}
        {oiProfile && (
          <SecondaryProfileLayer
            profile={oiProfile}
            priceToY={priceToY}
            barWidth={profileWidth}
            ratioScale={ratioScale}
            which={secondaryGreek}
            spot={spot}
            smoothRadius={greekSmooth}
          />
        )}
        {/* Charm/Vanna pivot REMOVED 2026-06-01 (roadmap P1.1). The charm
            zero-cross is structurally pinned to ATM (net charm ≈ 0 at-the-money),
            so the line just drew spot every session — not a real level. Drift
            DIRECTION now comes from the cumulative LHP/RHP charm integral
            imbalance (oiProfile.structure_read), not a per-strike zero-cross.
            See memory: charm-pivot-mislocation. */}

        {/* COTMC / COTMP — the GE definition, nothing else (Edwin 7/2: "just the
            GE definition for now"): one premarket-static dashed level per side,
            p50 of the OTM monetization sweep (self-computed, [[derive/cotm]]).
            Fan washes, concentration zones, and % progress chips all retired the
            same day — the data still ships (cotm*_fan, cotm_progress) for panels
            and research; the canvas draws only the two levels. */}
        {showCOTM && (() => {
          const level = (p: number | null | undefined, key: string) => {
            if (p == null) return null
            const yMid = priceToY(p)
            return (
              <g key={key}>
                <line x1={0} x2={100} y1={yMid} y2={yMid}
                      stroke={rgba(chartInk.scrim, 0.6)} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
                <line x1={0} x2={100} y1={yMid} y2={yMid}
                      stroke={rgba(chartInk.deltaTint, 0.95)} strokeWidth={0.85}
                      strokeDasharray="2.5 1.5" vectorEffect="non-scaling-stroke" />
              </g>
            )
          }
          return (
            <g>
              {level(data.cotmc, 'cotmc')}{level(data.cotmp, 'cotmp')}
            </g>
          )
        })()}

        {/* Candles */}
        <CandleLayer bars={data.bars} timeToX={timeToX} priceToY={priceToY} />

        {/* Daily RTH VWAP — single pink line. This is an options-structure
            view; VWAP is the one price-action reference we keep (the 5d/20d
            multi-anchor lines + the VWAP strip were dropped). Sourced from
            vwap_today (NQ today; QQQ/SPX once the chart goes index-native —
            same field either way). Toggleable since the violet tape VWAP
            landed (fut VWAP checkbox). */}
        {showSierraVwap && (
          <LinePath
            points={data.vwap_today}
            timeToX={timeToX}
            priceToY={priceToY}
            stroke="#f472b6"
            strokeWidth={0.9}
            opacity={0.95}
          />
        )}

        {/* GEXLayer + DSLayer removed in v2.7 — replaced by the KDE-derived
            OI / Gamma profiles on the chart's flanks. Trans zones and DS
            bounds are now expressed visually as gray bands + peak lines
            in those profiles rather than as overlays on the candle area. */}

        {/* Cascade bands — striped pattern, layered above the candles so
            the cluster zone visibly tints the price action through it. */}
        <CascadeLayer cascades={cascades} priceToY={priceToY} />

        {/* Charm transition lines (CharmLinesLayer) removed — replaced by the
            animated charm push layer (CharmPushLayer) above. */}

        {/* Centroid density bands — translucent density fan on top so
            volume mass is visible on top of the price action rather than
            being hidden behind it. */}
        <BandLayer bands={data.bands} timeToX={timeToX} priceToY={priceToY} />

        {/* Options tape VWAP + wings — theta-native volume read; the server
            sends bands/linregs empty when this is present (supersession). */}
        <TapeVwapLayer
          lis={(tapeLens === 'flow' ? data.tape_lis_flow : data.tape_lis) ?? []}
          zoneLo={(tapeLens === 'flow' ? data.tape_flis_zone_lo : data.tape_lis_zone_lo) ?? []}
          zoneHi={(tapeLens === 'flow' ? data.tape_flis_zone_hi : data.tape_lis_zone_hi) ?? []}
          bands={(tapeLens === 'flow' ? data.tape_bands_decayed : data.tape_bands) ?? []}
          timeToX={timeToX} priceToY={priceToY} />
        {/* OTM vwap — observation-only (checkbox, default off) */}
        {showOtmVwap && (
          <LinePath
            points={(tapeLens === 'flow' ? data.tape_vwap_otm_decayed : data.tape_vwap_otm) ?? []}
            timeToX={timeToX} priceToY={priceToY}
            stroke={TAPE_VWAP_COLOR} strokeWidth={1.0} opacity={0.6} dasharray="4 3" />
        )}

        {/* Our-stats dual ruler removed — the percentile fan (C10-C50/P10-P50) +
            median centerline is the single, consistent methodology; the MAD/excess
            pivots (balance + extreme) were a parallel stat that mixed approaches. */}

        {/* Cluster bands removed per design — the visual semantics now
            come from the layer-specific treatments (GEX chop hatch,
            DS rubber-band, cascade stripes, HC thick lines). Hover
            surfaces live on the pills themselves. */}

        {/* Level markers — HC lines (thick, no label) and anchor lines
            (thin dashed, label on the right). Trans levels skipped here
            since their own zone treatment (GEX chop / DS gradient)
            already provides the visual. */}
        {/* LevelLines removed in v2.8 — structural levels now live in
            the OI / Gamma / Delta profiles on the chart's flanks. */}

        {/* Dual linreg (session-OLS reference + bold EWMA with marching ants) */}
        <LinregLayer linregs={data.linregs} timeToX={timeToX} priceToY={priceToY} />

        {/* Time-axis baseline + tick marks */}
        <line
          x1={0}
          y1={94}
          x2={X_DATA_END}
          y2={94}
          stroke="var(--ace-line)"
          strokeWidth={0.6}
          opacity={0.55}
          vectorEffect="non-scaling-stroke"
        />
        {xTicks.map(({ epoch, label }) => {
          const x = timeToX(epoch)
          if (x < 0 || x > X_DATA_END) return null
          return (
            <line
              key={`tick-${label}`}
              x1={x}
              y1={94}
              x2={x}
              y2={95.6}
              stroke="var(--ace-line)"
              strokeWidth={0.5}
              opacity={0.7}
              vectorEffect="non-scaling-stroke"
            />
          )
        })}

        {/* Crosshair — vertical + horizontal lines following the cursor */}
        {cursor && (
          <g pointerEvents="none">
            <line
              x1={cursor.x}
              y1={Y_DATA_TOP}
              x2={cursor.x}
              y2={Y_DATA_BOTTOM}
              stroke="#ffffff"
              strokeWidth={0.3}
              opacity={0.45}
              strokeDasharray="0.5 0.5"
              vectorEffect="non-scaling-stroke"
            />
            <line
              x1={0}
              y1={cursor.y}
              x2={X_DATA_END}
              y2={cursor.y}
              stroke="#ffffff"
              strokeWidth={0.3}
              opacity={0.45}
              strokeDasharray="0.5 0.5"
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )}
      </svg>

      {/* Reset-zoom button — small chip at top-right of the data area.
          Visible only when the viewport differs from default OR y has
          been manually pinned. */}
      {(viewport.start !== defaultStart ||
        viewport.end !== defaultEnd ||
        viewport.yMin != null ||
        viewport.yMax != null) && (
        <button
          type="button"
          onClick={reset}
          className="absolute top-2 right-2 z-10 rounded border border-[var(--ace-line)] bg-[var(--ace-surface-card)] px-2 py-0.5 font-mono text-[10px] font-semibold tracking-wider text-[var(--ace-ink-muted)] hover:text-[var(--ace-ink)] hover:border-[var(--ace-ink)]"
          title="Reset zoom (x + y)"
        >
          RESET
        </button>
      )}

      {/* HTML overlay labels — positioned absolutely so they don't
          distort under preserveAspectRatio='none' */}
      <div className="pointer-events-none absolute inset-0">
        {/* Price labels on the left edge */}
        {yTicks.map(({ price, y }) => (
          <div
            key={`yl-${price}`}
            className="absolute font-mono text-[9px] font-semibold tracking-wider text-white opacity-90"
            style={{ left: 4, top: `${y}%`, transform: 'translateY(-50%)' }}
          >
            {Math.round(price).toLocaleString()}
          </div>
        ))}

        {/* (Structure-read badge moved to the Multi-Timeframe Stack — per-layer
            environment + pill lives there now, not in the chart corner. 2026-06-01) */}

        {/* Time labels on the bottom edge — dynamic from viewport */}
        {xTicks.map(({ epoch, label }) => {
          const x = timeToX(epoch)
          if (x < 0 || x > X_DATA_END) return null
          return (
            <div
              key={`tl-${label}`}
              className="absolute font-mono text-[9px] font-semibold tracking-wider text-white opacity-90"
              style={{ left: `${x}%`, bottom: '1.5%', transform: 'translateX(-50%)' }}
            >
              {label}
            </div>
          )
        })}

        {/* Cascade labels — left-edge greek list, anchored at the band.
            Quiet register (semibold not bold, lower opacity) so the
            label sits in the chart context rather than competing with
            price action. Razor clusters get a slightly stronger color
            since they're the more actionable signal. */}
        {cascades.map((c, i) => {
          const midY = (priceToY(c.top_price) + priceToY(c.bottom_price)) / 2
          const text = (c.razor ? 'CASCADE (razor) | ' : 'CASCADE | ')
            + c.greeks.map(capitalize).join(' + ')
          const color = rgb(c.razor ? chartInk.razor : chartInk.cascade)
          return (
            <div
              key={`cas-${i}`}
              className="absolute font-mono text-[8px] font-semibold uppercase tracking-wider"
              style={{
                left: 1,
                top: `${midY}%`,
                transform: 'translateY(-50%)',
                color,
                opacity: c.razor ? 0.75 : 0.55,
                whiteSpace: 'nowrap',
                textShadow: `0 0 2px ${rgba(chartInk.scrim, 0.7)}`,
              }}
            >
              {text}
            </div>
          )
        })}

        {/* Chart annotation labels — HTML overlay (avoids SVG-text distortion).
            Mirrors the 4 SVG <text> nodes removed from the layer components:
            charm labels, wall Δ tags, flow fulcrum, Greek VA marks. */}
        <ChartLabelsOverlay
          charmLines={[]}
          oiProfile={oiProfile ?? null}
          priceToY={priceToY}
        />

        {/* Crosshair tooltips — price chip at right edge, time chip at bottom */}
        {cursor && (
          <>
            <div
              className="absolute font-mono text-[10px] font-semibold rounded px-1.5 py-px"
              style={{
                left: `${X_DATA_END}%`,
                top: `${cursor.y}%`,
                transform: 'translateY(-50%)',
                color: rgb(chartInk.highlight),
                backgroundColor: rgba(chartInk.chipBg, 0.92),
                border: '0.5px solid #4b5563',
                whiteSpace: 'nowrap',
              }}
            >
              {yToPrice(cursor.y).toFixed(2)}
            </div>
            <div
              className="absolute font-mono text-[10px] font-semibold rounded px-1.5 py-px"
              style={{
                left: `${cursor.x}%`,
                bottom: '1%',
                transform: 'translateX(-50%)',
                color: rgb(chartInk.highlight),
                backgroundColor: rgba(chartInk.chipBg, 0.92),
                border: '0.5px solid #4b5563',
                whiteSpace: 'nowrap',
              }}
            >
              {xToPtLabel(cursor.x)} PT
            </div>
          </>
        )}

        {/* LeftPillTray + RightPillTray removed in v2.8 — Edwin: "delete
            the DS_upper, DEX_ptrans... labels." Structure now lives in
            the OI / Gamma / Delta profiles. */}

      </div>
    </div>
    </div>
  )
}

// ── Sub-layers ──────────────────────────────────────────────────────────────





/**
 * OIProfileLayer — Sierra-style VP-with-delta-coloring on the strike axis.
 *
 * Bars extend LEFTWARD from x=X_DATA_END (right edge of data area) toward
 * the candles. Y-axis is shared with the price chart via priceToY, so
 * peaks line up exactly with price levels.
 *
 * All visuals derived from SMOOTHED signals (not raw per-strike values),
 * so the bar envelope and color gradient both reflect KDE-clustered
 * structure rather than single-strike noise:
 *   - bar length = smoothed_total (Gaussian-smoothed total_oi)
 *   - color sign = sign(smoothed_net) → green call-dom / red put-dom
 *   - color sat  = |smoothed_net| / smoothed_total → how decisive
 *   - faint backdrop alpha (0.18-0.45) so candles read clearly on top
 *
 * Major-peak strikes get a thin white outline. Sign flips render as
 * dashed yellow horizontal lines.
 */
/** Helpers shared between the SVG layer and the HTML overlay so the
 * visual encoding stays consistent across primitives + labels. */
// Default bar length cap (viewBox 0..100 units). The parent may pass a
// custom value via the `profileWidth` prop on PriceChart to expand /
// contract the OI + Gamma profile strips.
const OI_BAR_WIDTH_DEFAULT = 18

// OI-profile normalization window: bar length + color σ scale against the max/
// spread of strikes within ±this fraction of spot, NOT the whole chain. A real
// but deep OI wall (e.g. a 580 put cluster ~20% below a 735 spot) would otherwise
// be the global max and crush every near-spot bar to a sliver. ±5% keeps the
// tradeable zone legible; off-window giants just clamp to full width. Tunable.
const OI_NORM_WINDOW_FRAC = 0.05

// Tanh-scaled color encoding, matching indicators/delta_profile/AT_final_profile3_v70.cpp:1035
//   scaledRatio[b] = tanh((smoothRatio[b] / effMaxR) * ratioScale)
//
// Why tanh-with-normalization: linear |net|/total mapping looks fine at
// raw bandwidth, but heavier smoothing shrinks the ratio across all bins,
// so everything collapses to the dim end of the alpha range. Normalizing
// by the strongest ratio in view + tanh expansion keeps the peak vivid
// and amplifies modest ratios so the gradient reads regardless of σ.
// tanh ratio_scale defaults to 3.0 (matches Sierra DP). Controllable by
// the parent via PriceChart's `ratioScale` prop and the UI dropdown.

/** Robust scale for color normalization — the Nth-percentile of |values|, not
 *  the literal max. Defeats the "one dominating bar" problem: a single freak
 *  net/gamma strike (JPM collar, quarterly pin) would otherwise inflate the
 *  denominator and grey out everything else. Outliers above the percentile just
 *  clamp to full saturation. Bar LENGTH still uses the true max (proportions
 *  preserved); only COLOR uses this. */
function robustScale(values: number[], pct = 0.90): number {
  const arr = values.map((v) => Math.abs(v)).filter((v) => v > 0).sort((a, b) => a - b)
  if (arr.length === 0) return 1
  const idx = Math.min(arr.length - 1, Math.max(0, Math.floor(pct * (arr.length - 1))))
  return Math.max(arr[idx], 1e-9)
}

// Coloring by sigmas from balance (zero) — SAT_SIGMA / SIGMA_STEP / the σ-tier
// magnitude live in chartMath (sigmaTierMag), shared with the Delta heatmap so
// both reads use one intensity law. `tierMag` kept as a local alias for the
// many call sites below.
const tierMag = sigmaTierMag

// tierHue, tierHueGamma, tierHueDelta REMOVED — hue decisions now come from
// server-computed per-row state fields (net_state, gamma_state, delta_state,
// charm_state, vanna_state). tierMag retained for brightness scaling.

// clusterPeaks (net cluster wall detection) was REMOVED here 2026-06-02 — the
// major/minor net-cluster walls are now computed ONCE server-side
// (ge_ds_kde.net_cluster_walls) and read from profile.net_clusters, so the
// chart, levels.txt, and the Sierra study share a single source. The Python
// port mirrors the old logic verbatim (Gaussian σ=r/3 at 6-bin major / 3-bin
// minor, |peak| among non-grey bars).

// Client-side exhaustionEdges was removed 2026-06-02; the server-side grey-edge
// successor was retired 2026-07-01 — data.cotmc/data.cotmp now carry ONLY the
// balance-construction COTM levels (derive/cotm.py) via the serve/state override.


/** Universal bar-length encoding for ALL profile layers (OI/Gamma/Delta/Charm/Vanna).
 *
 * Linear-normalized: bar length = |value| / max(|values|) * barWidth.
 * Peak hits exactly barWidth; every other bar is proportional to its share
 * of the profile's peak.
 *
 * Why linear and not tanh-compressed: ratio_scale is a COLOR-intensity knob,
 * not a length knob. Length needs to be a pure structural reading — the eye
 * should be able to compare "how big is the secondary peak vs the primary"
 * by looking at bar ratios, without that ratio shifting when the user tunes
 * color saturation. Mixing those two responsibilities (the bug here originally)
 * meant cranking ratio_scale to sharpen colors also squished bar lengths.
 *
 * Previous code mixed linear (OI, Delta) and sqrt (Gamma); now all five
 * profiles share the same linear normalization, so a 50%-width bar means
 * "50% of this profile's peak" on every layer.
 */
function profileBarLength(
  value: number,
  maxAbsValue: number,
  barWidth: number,
): number {
  if (maxAbsValue <= 0) return 0
  return Math.min(1, Math.abs(value) / maxAbsValue) * barWidth
}

// VA_COLOR_DELTA/CHARM/VANNA → imported from ./chartMath

// pivotCross REMOVED 2026-06-01 (roadmap P1.1) — it located the charm/vanna
// "pivot" at the net-charm zero-cross, which is structurally pinned to ATM, so
// the line just tracked spot. Drift direction is now the cumulative LHP/RHP
// charm integral (server-side structure_read), not a per-strike zero-cross.

function neutralBand(
  rows: ReadonlyArray<{ strike: number }>,
  signalOf: (i: number) => number,
  isGrey: (i: number) => boolean,
): { lo: number; hi: number } | null {
  const n = rows.length
  if (n === 0) return null
  const order = rows.map((_, i) => i).sort((a, b) => rows[a].strike - rows[b].strike)
  const sig = order.map((i) => signalOf(i))
  const grey = order.map((i) => isGrey(i))
  const strikes = order.map((i) => rows[i].strike)
  // Anchor on the dominant sign-flip (largest adjacent mass); else the weakest
  // point when the signal never crosses zero.
  let anchor = -1
  let bestMass = -1
  for (let i = 0; i < n - 1; i++) {
    if (sig[i] === 0 || sig[i] * sig[i + 1] < 0) {
      const mass = Math.abs(sig[i]) + Math.abs(sig[i + 1])
      if (mass > bestMass) { bestMass = mass; anchor = i }
    }
  }
  if (anchor < 0) {
    let m = Infinity
    for (let i = 0; i < n; i++) {
      if (Math.abs(sig[i]) < m) { m = Math.abs(sig[i]); anchor = i }
    }
  }
  // Seed on an actually-grey bar at/adjacent to the flip; else nearest grey bar.
  // The band is the contiguous run of GREY bars; its edges extend to the
  // grey↔COLORED boundary (half-strike to the first colored bar) — same rule as
  // the gamma control band. Those edges are the DEX transition levels: grey↔red
  // below = DEX NTrans, grey↔green above = DEX PTrans. No grey → no band.
  let seed = -1
  if (grey[anchor]) seed = anchor
  else if (anchor + 1 < n && grey[anchor + 1]) seed = anchor + 1
  else {
    for (let dd = 1; dd < n; dd++) {
      if (anchor - dd >= 0 && grey[anchor - dd]) { seed = anchor - dd; break }
      if (anchor + dd < n && grey[anchor + dd]) { seed = anchor + dd; break }
    }
  }
  if (seed < 0) return null
  let lo = seed
  let hi = seed
  while (lo - 1 >= 0 && grey[lo - 1]) lo--
  while (hi + 1 < n && grey[hi + 1]) hi++
  const loEdge = lo - 1 >= 0 ? (strikes[lo] + strikes[lo - 1]) / 2 : strikes[lo]
  const hiEdge = hi + 1 < n ? (strikes[hi] + strikes[hi + 1]) / 2 : strikes[hi]
  return { lo: Math.min(loEdge, hiEdge), hi: Math.max(loEdge, hiEdge) }
}

// OI bar brightness floor/ceiling — OI_ALPHA_FLOOR / OI_ALPHA_CEIL live in
// chartMath (shared with the Delta heatmap, which passes floor 0).

// 'green'/'red' = DIRECTIONAL axis (net OI call/put, delta exposure).
// 'pin'/'accel' = gamma REGIME axis (sign of signed net GEX): pin = positive GEX
// (dealers long → mean-revert, ORANGE), accel = negative GEX (dealers short →
// amplify, BLUE). This is the gamma condition itself, spatially resolved — NOT
// the call/put-OI dominance the four-case rule warns about. Zero-cross = gamma flip.
// 'delta' = net-delta MAGNITUDE hue (PURPLE). Delta is ~always positive (ITM-call
// delta dominates), so its sign is degenerate — color positive delta by magnitude
// (concentration/exhaustion) and let the RARE negative flare 'red' so it pops.
type OiHue = 'green' | 'red' | 'gray' | 'pin' | 'accel' | 'delta' | 'callOtm' | 'putOtm' | 'callItm' | 'putItm'

/** OI bar fill — HUE from net direction, BRIGHTNESS from the bar's own
 * magnitude (its share of the profile peak) raised to `contrast`.
 *
 * Brightness tracks the profile SHAPE (bar length), not net decisiveness, so a
 * tall node is always brighter than the gaps around it — the "peaks glow,
 * valleys recede" read. `contrast` is the ratio_scale knob acting as a gamma:
 * 1 = linear, >1 suppresses valleys harder so only the peaks stay bright.
 *
 * Replaces the old tanh-on-decisiveness encoding, which FLATTENED contrast —
 * tanh saturates mid/low magnitudes toward bright, so cranking the knob made
 * valleys nearly as bright as peaks (the bug being fixed here). */
function oiBarFill(mag01: number, hue: OiHue, contrast: number): string {
  // Shared law (chartMath.intensityAlpha) — OI bars floor at OI_ALPHA_FLOOR.
  const a = intensityAlpha(mag01, contrast, OI_ALPHA_FLOOR, OI_ALPHA_CEIL)
  if (hue === 'green') return rgba(chartInk.callDeep, a)
  if (hue === 'red') return rgba(tokenHues.down, a)
  if (hue === 'pin') return rgba(chartInk.orange, a)    // orange — positive gamma (PIN)
  if (hue === 'accel') return rgba(tokenHues.accel, a)  // blue — negative gamma (ACCEL)
  if (hue === 'delta') return rgba(tokenHues.delta, a) // purple — net-delta magnitude (legless fallback)
  // Leg-split delta moneyness pair: hue = class (green calls / red puts, the net-OI
  // convention), LIGHTNESS = moneyness — DEEP OTM (speculative fuel, the strong read),
  // the same hue LIGHTENED for ITM (winners/ballast) (Edwin 7/2: "OTM is the deeper
  // color...deep green and deep red..then light red and green").
  if (hue === 'callOtm') return rgba(chartInk.callDeep, a) // deep green — OTM calls (fuel)
  if (hue === 'putOtm') return rgba(tokenHues.down, a)     // deep red — OTM puts (fuel)
  if (hue === 'callItm') return rgba(chartInk.callTint, a)  // light green — ITM calls (winners)
  if (hue === 'putItm') return rgba(chartInk.putTint, a)   // light red — ITM puts (winners)
  return rgba(chartInk.inkDim, a)
}

/** UNIFORM bar height — every bar the same thickness, so the profile reads as
 * one consistent set of bars (like GE's grid). The ladder is non-uniform: $5
 * near spot, $10 a bit out, then $25–$200 in the far-OTM wings (now visible
 * after the full-chain scrape). Sizing each bar to its LOCAL gap made the $5
 * and $10 bars render at different thicknesses (and the old rows[0]/rows[1]
 * estimate — a far-OTM gap — drew them dozens of times too tall, smearing into
 * "layers"). Instead, size every bar to the DENSEST ($5) spacing: bars never
 * overlap, all share one width, and sparser wing strikes just sit farther
 * apart. Shared by all three profile layers (OI / Gamma / secondary). */
function localBarHeights(
  rows: ReadonlyArray<{ strike: number }>,
  priceToY: (p: number) => number,
): number[] {
  const ys = rows.map((r) => priceToY(r.strike))
  let minGap = Infinity
  for (let i = 1; i < ys.length; i++) {
    const g = Math.abs(ys[i] - ys[i - 1])
    if (g > 0.01) minGap = Math.min(minGap, g)
  }
  const h = Math.max(0.3, (Number.isFinite(minGap) ? minGap : 1) * 0.9)
  return ys.map(() => h)
}

/** FLOW PROFILE — the always-on overnight-change strip paired with the 0DTE
 * profile. Same visual law as the OI profile's total mode, applied to flow:
 * bar LENGTH = churn (|Δcall| + |Δput| — how much the book moved; a rotation
 * never cancels), HUE = Δnet sign (green call-building / red put-building /
 * grey sub-σ balanced). Geometry and fill law shared with the other profile
 * strips (localBarHeights + oiBarFill) so the two strips read as siblings. */
function FlowProfileLayer({
  gridStrikes,
  delta,
  priceToY,
  barWidth,
  ratioScale,
  spot = null,
  baseX = 0,
  smoothRadius = 3,
}: {
  /** The 0DTE profile's row grid — flow is BINNED onto it so the two strips
   *  align bar-for-bar (the raw union ladder is irregular/fractional). */
  gridStrikes: number[]
  delta: { strikes: number[]; d_net: number[]; churn?: number[] }
  priceToY: (p: number) => number
  barWidth: number
  ratioScale: number
  spot?: number | null
  baseX?: number
  /** Shape smoothing radius (bar length only) — the user knob. */
  smoothRadius?: number
}) {
  const cells = selectFlowProfile(
    gridStrikes ?? [], delta.strikes ?? [], delta.churn ?? [], delta.d_net ?? [], spot,
    { radiusLen: smoothRadius })
  if (!cells.length) return null
  const heights = localBarHeights(cells, priceToY)
  return (
    <g pointerEvents="none">
      {cells.map((c, i) => {
        const w = c.len01 * barWidth
        if (w < 0.05) return null
        const y = priceToY(c.strike)
        if (!isFinite(y)) return null
        const h = heights[i]
        // Fill = the HEATMAP law: hue from net sign, brightness from |Δnet|
        // σ-tiers (c.mag01) — NOT from bar length. A long dim bar = big fight,
        // no winner; long saturated = one-sided build (Edwin: "color is net").
        return (
          <rect key={c.strike} x={baseX} y={y - h / 2} width={Math.max(0.15, w)}
                height={h} fill={oiBarFill(c.mag01, c.hue, ratioScale)} stroke="none" />
        )
      })}
    </g>
  )
}

function OIProfileLayer({
  profile,
  priceToY,
  barWidth,
  ratioScale,
  mode = 'total',
  spot = null,
  baseX = 0,
  smoothRadius = null,
}: {
  profile: OIProfileView
  priceToY: (p: number) => number
  barWidth: number
  ratioScale: number
  mode?: OIProfileMode
  /** Index-scale spot. Centers the bar-length + color-σ normalization window so
   *  a deep off-window OI wall can't set the scale. null → whole-chain (legacy). */
  spot?: number | null
  /** viewBox x-origin for the profile BARS only (full-width bands stay at
   *  x=0 width=100 regardless). Default 0 = present profile, unaffected.
   *  Non-zero renders an adjacent strip (e.g. the Future horizon). */
  baseX?: number
  /** Display-only SHAPE re-smooth (the 0DTE smooth knob): null = the server's
   *  smoothed fields verbatim (radius_total=6); a number re-smooths bar LENGTH
   *  client-side from the RAW per-strike fields at that radius (rows are a
   *  uniform resampled grid, so index smoothing == price smoothing). Color,
   *  net_state, LIS, walls, peaks all stay server-pinned — shape only. */
  smoothRadius?: number | null
}) {
  if (profile.rows.length === 0) return null

  // Mode-specific bar length signal (hue + brightness handled below).
  //   total → smoothed_total length
  //   call  → smoothed_call length
  //   put   → smoothed_put length
  //   net   → |smoothed_net| length
  // 'change' (Δ) mode — the day-over-day net-OI FLOW. Bar length uses
  // |net_change| directly; hue/grey decision comes from server net_change_state.
  let lengthSignal = profile.rows.map((r) =>
    mode === 'change' ? Math.abs(r.net_change ?? 0)
      : mode === 'call' ? r.smoothed_call
      : mode === 'put' ? r.smoothed_put
      : mode === 'net' ? Math.abs(r.smoothed_net)
      : r.smoothed_total,
  )
  if (smoothRadius != null && mode !== 'change') {
    const rawSigned = profile.rows.map((r) =>
      mode === 'call' ? r.call_oi
        : mode === 'put' ? r.put_oi
        : mode === 'net' ? r.net_oi
        : r.total_oi)
    const sm = smoothRadius > 0
      ? convolveSame(rawSigned, gaussianKernel(smoothRadius))
      : rawSigned
    lengthSignal = mode === 'net' ? sm.map((v) => Math.abs(v)) : sm
  }
  // Normalization frame: bar length AND color σ scale against strikes within
  // ±OI_NORM_WINDOW_FRAC of spot, not the whole chain — so a real but deep OI
  // wall can't be the global max and crush the near-spot zone to slivers. One
  // window, fed to every scale below, so length and brightness always agree.
  // Falls back to the whole chain when spot is unknown / the window is sparse.
  const winIdx = spotWindowIndices(profile.rows.map((r) => r.strike), spot, OI_NORM_WINDOW_FRAC)
  const maxSmoothed = winIdx.reduce((m, i) => Math.max(m, lengthSignal[i]), 1)

  // COLOR signal — what drives hue + brightness, separate from bar length.
  //   total + net → |smoothed_net| (the net coloring): total keeps its full-mass
  //                 LENGTH but is painted by net structure, so balanced nodes go
  //                 dim/gray and one-sided nodes light up green/red.
  //   call / put  → single-side magnitude (same as length).
  const colorSignal = profile.rows.map((r) =>
    mode === 'call' ? r.smoothed_call
      : mode === 'put' ? r.smoothed_put
      : Math.abs(r.smoothed_net),
  )
  // Net-driven modes (total/net) color by robust-sigmas of net; single-side
  // modes (call/put) have no sign, so they use the P90 magnitude scale.
  // 'change' mode: magnitude from |net_change| σ-tiers.
  const netColored = mode !== 'call' && mode !== 'put'
  // σ = median-then-stdev of net (just the SCALE). Coloring is symmetric about
  // zero: intensity = |net| / σ, so +X (calls) and −X (puts) get the SAME
  // intensity — only the hue differs (green vs red). The median is used only to
  // compute the spread, NOT to shift the color center.
  const netSigma = netColored ? robustSigma(winIdx.map((i) => profile.rows[i].smoothed_net)) : 1
  const changeSigma = mode === 'change'
    ? robustSigma(winIdx.map((i) => profile.rows[i].net_change ?? 0))
    : 1
  const maxColor = netColored ? netSigma * SAT_SIGMA : robustScale(winIdx.map((i) => colorSignal[i]), 0.90)
  // Saturation per bar. Net modes: |net| in 0.5σ tiers (symmetric). Single-side
  // modes: smooth P90 magnitude. Change mode: |net_change| σ-tiers.
  const colorMag = profile.rows.map((r, i) => {
    if (mode === 'change') return sigmaTierMag(r.net_change ?? 0, changeSigma)
    if (!netColored) return colorSignal[i] / maxColor
    return sigmaTierMag(r.smoothed_net, netSigma)
  })

  // Per-bar HUE (direction). NET OI is the single coloring mechanism, normalized
  // to the BIGGEST net bar (|net| / max|net|) — the same scheme gamma/delta/etc.
  // use (signal / its own peak). This reflects net OI's structural meaning: its
  // ABSOLUTE directional magnitude (dealer hedging weight), not the per-strike
  // purity. A big mildly-skewed wall (large net) lights up; a tiny one-sided
  // OTM strike (small net) stays grey. Identical color in total + net modes —
  // only bar LENGTH differs by mode. (call/put modes → forced single-side.)
  const hues: OiHue[] = profile.rows.map((r) => {
    if (mode === 'change') {
      // HUE DECISION = SERVER DOCTRINE. net_change_state is computed server-side
      // (same flip_zone/greyMask as net_state but on smoothed net_change).
      // null rows → warming (no prior snapshot, flow is fabricated) → grey.
      const cs = r.net_change_state
      if (cs == null || cs === 'grey') return 'gray'
      return cs === 'call' ? 'green' : 'red'
    }
    if (mode === 'call') return 'green'
    if (mode === 'put') return 'red'
    // NET hue DECISION (total + net modes) = SERVER DOCTRINE. The grey/call/put
    // verdict is r.net_state, computed ONCE server-side from the combined
    // colored-test (smoothed_net r3, grey_sigma 0.5, rel_floor 0.05) — the SAME
    // test that places the LIS band — so a bar can never be painted a color the
    // band treats as grey (or vice versa). Pixels = doctrine.
    if (r.net_state === 'grey') return 'gray'
    return r.net_state === 'call' ? 'green' : 'red'
  })

  const barHeights = localBarHeights(profile.rows, priceToY)

  // ── Half-spacing for full-bar fill padding (doctrine 2026-06-10) ─────────
  // Band levels are quoted at whole-dollar strikes (e.g. LIS 707–713). Drawing
  // the rectangle at exact quoted values clips each edge bar in half. We pad
  // both sides by half the median adjacent-strike gap so the fill covers the
  // complete edge bars. Quoted values in the API / levels.txt stay unchanged —
  // this is render-only.
  const _halfSpacing = medianStrikeGap(profile.rows) / 2

  // ── LIS core + halo — server-computed on the raw $1-strike grid (matches
  // levels.txt and Sierra exactly). Radius-3 core, radius-6 halo.
  // Client no longer re-derives these from the resampled display bins.
  const lisCore = (profile.lis_lo != null && profile.lis_hi != null)
    ? padBand(profile.lis_lo, profile.lis_hi, _halfSpacing)
    : null
  const lisHalo = (profile.lis_halo_lo != null && profile.lis_halo_hi != null)
    ? padBand(profile.lis_halo_lo, profile.lis_halo_hi, _halfSpacing)
    : null
  // Net cluster walls — SERVER-COMPUTED (ge_ds_kde.net_cluster_walls), the
  // single source shared with levels.txt + the Sierra study. LIS core/halo also
  // server-computed (flip_zone on $1-strike grid — see lisCore/lisHalo above).
  // NOT gated on `warming`: walls come from net_oi (the standing book), valid
  // from the first capture. Only the FLOW overlay (the short-term lens) is fabricated while
  // warming. Gating walls here hid them on 0DTE days (always warming, since a
  // same-expiry prior never exists before today) — matching Sierra, which draws
  // them unconditionally from levels.txt.
  const walls = (profile.net_clusters ?? []).map((c) => ({
    strike: c.strike,
    major: c.magnitude === 'major',
    side: c.side,
  }))

  // DS Upper / Lower — the FIRST net-OI wall away from the LIS on each side
  // (= the derive's DS_UPPER / DS_LOWER). Drawn thicker than the other walls.
  const dsUp = lisHalo
    ? walls.filter((w) => w.strike > lisHalo.hi).sort((a, b) => a.strike - b.strike)[0]?.strike ?? null
    : null
  const dsDn = lisHalo
    ? walls.filter((w) => w.strike < lisHalo.lo).sort((a, b) => b.strike - a.strike)[0]?.strike ?? null
    : null

  // Peak strikes — sets for membership tests on outline.
  return (
    <g pointerEvents="none">
      {/* LIS flip zone — wide halo (6-bin) + tight core (3-bin), overlapped, full
          width. Distinct edges so the nesting reads at a glance: the core (sharp
          3-bin flip) gets SOLID bright white edges; the halo (broad 6-bin balance)
          gets DASHED faint white edges. Where they agree = sharp flip. */}
      {lisHalo && (() => {
        const yTop = priceToY(lisHalo.hi)
        const yBot = priceToY(lisHalo.lo)
        const haloFill = rgba(chartInk.ink, 0.04)
        const haloEdge = rgba(chartInk.highlight, 0.30)
        return (
          <g>
            <rect x={0} y={yTop} width={100} height={Math.max(0.4, yBot - yTop)}
                  fill={haloFill} stroke="none" />
            <line x1={0} x2={100} y1={yTop} y2={yTop}
                  stroke={haloEdge} strokeWidth={0.4}
                  strokeDasharray="1 2.5" vectorEffect="non-scaling-stroke" />
            <line x1={0} x2={100} y1={yBot} y2={yBot}
                  stroke={haloEdge} strokeWidth={0.4}
                  strokeDasharray="1 2.5" vectorEffect="non-scaling-stroke" />
          </g>
        )
      })()}
      {lisCore && (() => {
        const yTop = priceToY(lisCore.hi)
        const yBot = priceToY(lisCore.lo)
        const h = Math.max(0.4, yBot - yTop)
        const coreFill = rgba(chartInk.inkBright, 0.16)
        const coreEdge = rgba(chartInk.highlight, 0.78)
        return (
          <g>
            <rect x={0} y={yTop} width={100} height={h}
                  fill={coreFill} stroke="none" />
            <line x1={0} x2={100} y1={yTop} y2={yTop}
                  stroke={coreEdge} strokeWidth={0.6}
                  vectorEffect="non-scaling-stroke" />
            <line x1={0} x2={100} y1={yBot} y2={yBot}
                  stroke={coreEdge} strokeWidth={0.6}
                  vectorEffect="non-scaling-stroke" />
          </g>
        )
      })()}
      {/* Delta-LIS — the DELTA-profile sign-flip zone at FIXED radius 3. Blue
          transparent band (matching Sierra study slots 46-47 color). Labeled
          "Δ LIS". Only rendered when both fields are non-null (bifocal delta
          day with foci bracketing spot). Mirrors DELTA_LIS_LO/HI in levels.txt
          and sierra/levels.py. trans == transition zone; delta trans = Δ LIS.
          Padded by _halfSpacing so fill covers full edge bars (render only). */}
      {(profile.delta_lis_lo != null && profile.delta_lis_hi != null) && (() => {
        const { lo: _dlisLo, hi: _dlisHi } = padBand(profile.delta_lis_lo!, profile.delta_lis_hi!, _halfSpacing)
        const yTop = priceToY(_dlisHi)
        const yBot = priceToY(_dlisLo)
        const h = Math.max(0.4, yBot - yTop)
        return (
          <g>
            <rect x={0} y={yTop} width={100} height={h}
                  fill={rgba(tokenHues.gamma, 0.10)} stroke="none" />
            <line x1={0} x2={100} y1={yTop} y2={yTop}
                  stroke={rgba(tokenHues.gamma, 0.60)} strokeWidth={0.5}
                  strokeDasharray="1.2 1" vectorEffect="non-scaling-stroke" />
            <line x1={0} x2={100} y1={yBot} y2={yBot}
                  stroke={rgba(tokenHues.gamma, 0.60)} strokeWidth={0.5}
                  strokeDasharray="1.2 1" vectorEffect="non-scaling-stroke" />
          </g>
        )
      })()}
      {/* Balance zones — secondary net-OI shelves OUTSIDE the LIS, drawn from the
          SERVER's balance_zones (detect_balance_zones: volume mass gate + |net|/σ
          + net rel-floor). SINGLE SOURCE: the exact same BAL_n Sierra reads from
          levels.txt, so the two surfaces are identical and the volume gate keeps
          zones off the distribution tails. (Previously regrouped client-side from
          grey bars — no volume gate, drifted from Sierra.) Server zones already
          exclude the LIS. */}
      {(profile.balance_zones ?? []).map((z, i) => {
        const { lo: bLo, hi: bHi } = padBand(z.lo, z.hi, _halfSpacing)
        const yTop = priceToY(bHi)
        const yBot = priceToY(bLo)
        const h = Math.max(0.4, yBot - yTop)
        return (
          <g key={`bal-${i}`}>
            <rect x={0} y={yTop} width={100} height={h}
                  fill={rgba(chartInk.gold, 0.11)} stroke="none" />
            <line x1={0} x2={100} y1={yTop} y2={yTop} stroke={rgba(chartInk.gold, 0.6)}
                  strokeWidth={0.45} strokeDasharray="2 1.5" vectorEffect="non-scaling-stroke" />
            <line x1={0} x2={100} y1={yBot} y2={yBot} stroke={rgba(chartInk.gold, 0.6)}
                  strokeWidth={0.45} strokeDasharray="2 1.5" vectorEffect="non-scaling-stroke" />
          </g>
        )
      })}

      {/* Per-strike horizontal bars. Length is mode-specific; HUE is the net
          direction (green call-dom / red put-dom / gray balanced) and
          BRIGHTNESS scales with each bar's magnitude so peaks glow and valleys
          recede (ratio_scale = the gamma/contrast knob). */}
      {profile.rows.map((r, i) => {
        const y = priceToY(r.strike)
        const len = profileBarLength(lengthSignal[i], maxSmoothed, barWidth)
        return (
          <rect
            key={`oi-${r.strike}`}
            x={baseX}
            y={y - barHeights[i] / 2}
            width={len}
            height={barHeights[i]}
            fill={oiBarFill(colorMag[i], hues[i], ratioScale)}
            stroke="none"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}

      {/* Net cluster walls — FULL-WIDTH lines across the window (like the charm
          pivot), always on. Major (6-bin survivor) = thick + bright; minor
          (3-bin only) = thin + faint. Side-colored (green call / red put). */}
      {walls.map((w) => {
        const y = priceToY(w.strike)
        const color = w.side === 'call' ? rgba(tokenHues.call, 1) : rgba(tokenHues.put, 1)
        const isDS = w.strike === dsUp || w.strike === dsDn
        // DS = first wall past the LIS each side → thicker than the rest.
        return (
          <g key={`wall-${w.strike}-${w.major ? 'M' : 'm'}`}>
            <line
              x1={0} x2={100} y1={y} y2={y}
              stroke={color}
              strokeWidth={isDS ? 1.2 : w.major ? 0.55 : 0.28}
              opacity={isDS ? 1 : w.major ? 0.85 : 0.4}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )
      })}
    </g>
  )
}


/**
 * GammaProfileLayer — mirror of OIProfileLayer, applied to net_gamma.
 *
 * Sits on the RIGHT side of the chart (bars extend LEFTWARD from
 * x=X_DATA_END). Bar length = |smoothed_gamma| (gamma concentration);
 * bar color = sign(smoothed_gamma) green=call-gamma, red=put-gamma;
 * tanh-normalized saturation.
 *
 * Operationally: shows where dealer hedging accelerates (the +GEX /
 * -GEX structure). The gamma_peaks lines mark the local extrema —
 * candidate +GEX / -GEX strikes that aren't necessarily where the OI
 * mass concentrates.
 */
/** Display-only greek re-smooth: null → the server's smoothed field verbatim
 * (radius 3); a number re-smooths from the RAW per-strike greek on the
 * uniform row grid. Shape/brightness only — server states (grey verdicts),
 * peaks, and VAs stay doctrine-pinned. */
function resmoothGreek(raw: number[], serverSmoothed: number[],
                       radius: number | null | undefined): number[] {
  if (radius == null) return serverSmoothed
  return radius > 0 ? convolveSame(raw, gaussianKernel(radius)) : raw
}

function GammaProfileLayer({
  profile,
  priceToY,
  barWidth,
  ratioScale,
  smoothRadius = null,
}: {
  profile: OIProfileView
  priceToY: (p: number) => number
  barWidth: number
  ratioScale: number
  /** Greek shape-smoothing knob (null = server r=3). */
  smoothRadius?: number | null
}) {
  if (profile.rows.length === 0) return null

  // Length still normalized to true max (proportions); COLOR uses the shared
  // σ-tier logic for brightness; HUE DECISION comes from server-computed gamma_state.
  const gammaVals = resmoothGreek(
    profile.rows.map((r) => r.net_gamma ?? 0),
    profile.rows.map((r) => r.smoothed_gamma),
    smoothRadius)
  const maxAbsGamma = Math.max(1, ...gammaVals.map((v) => Math.abs(v)))
  const gammaSigma = robustSigma(gammaVals)

  const barHeights = localBarHeights(profile.rows, priceToY)

  return (
    <g pointerEvents="none">
      {/* Bars extend LEFTWARD from x=X_DATA_END. SHAPE = linear-normalized
          |smoothed_gamma| / max; HUE DECISION = server doctrine gamma_state
          (r.gamma_state: 'grey'|'pos'|'neg') — the r_greek σ dropdown no longer
          decides grey verdicts; it only scales brightness/length. BRIGHTNESS
          scales with |gamma| / max so peaks glow (same grammar as the OI strip). */}
      {profile.rows.map((r, i) => {
        const y = priceToY(r.strike)
        const len = profileBarLength(gammaVals[i], maxAbsGamma, barWidth)
        // Gamma hue DECISION from server state: grey→gray, pos→pin, neg→accel.
        // Brightness still client-σ-tier (same visual grammar, doctrine-aligned).
        const gammaHue: OiHue =
          (r.gamma_state ?? 'grey') === 'grey' ? 'gray'
          : r.gamma_state === 'pos' ? 'pin'
          : 'accel'
        return (
          <rect
            key={`gp-${r.strike}`}
            x={X_DATA_END - len}
            y={y - barHeights[i] / 2}
            width={len}
            height={barHeights[i]}
            fill={oiBarFill(tierMag(gammaVals[i], gammaSigma), gammaHue, ratioScale)}
            stroke="none"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}

      {/* ±GEX peaks — full-width YELLOW line, thick (same weight as a major
          6-bin wall). No dot/symbol. */}
      {profile.gamma_peaks.map((gp) => {
        const y = priceToY(gp.strike)
        return (
          <line key={`gp-line-${gp.strike}-${gp.side}`}
                x1={0} x2={100} y1={y} y2={y}
                stroke={rgba(chartInk.goldBright, 0.95)} strokeWidth={0.55}
                vectorEffect="non-scaling-stroke" />
        )
      })}
      {/* Gamma transition zone — NOT a value area. Gamma is a field, not a mass
          distribution; its structural feature is the NEUTRAL band — where the
          smoothed gamma goes grey (|gamma|/peak below the balance threshold).
          Mixed book → central band at the pin↔accel flip. All-green → the band
          sits at the tail, marking where call-gamma control fades. Rendered in
          the right strip so it reads as the gamma strip's own transition. */}
      {(() => {
        // GEX transition — CONDITIONAL. Only exists when net gamma actually
        // crosses sign (call-gamma control above ↔ put-gamma control below).
        // All-green (one sign only) → no transition in view ("out of range"),
        // render nothing. Not a pin zone — pin/accel is regime, not a level.
        // Grey test uses server doctrine gamma_state so the transition band
        // edges align with the server's computed lobe boundaries.
        const gray = (i: number) => (profile.rows[i].gamma_state ?? 'grey') === 'grey'
        const hasCall = profile.rows.some((r, i) => !gray(i) && r.smoothed_gamma > 0)
        const hasPut = profile.rows.some((r, i) => !gray(i) && r.smoothed_gamma < 0)
        if (!hasCall || !hasPut) return null   // all one sign → out of range
        const tz = neutralBand(profile.rows, (i) => profile.rows[i].smoothed_gamma, gray)
        if (!tz) return null
        const yTop = priceToY(tz.hi)
        const yBot = priceToY(tz.lo)
        const xL = X_DATA_END - barWidth - 2
        return (
          <g>
            {/* Gamma transition = edge LINES only (no fill). Per the chart rule:
                only the LIS net-OI balance zone is a filled band; every other
                structural feature is a line. */}
            <line x1={xL} x2={X_DATA_END} y1={yTop} y2={yTop}
                  stroke={rgba(chartInk.ink, 0.55)} strokeWidth={0.35}
                  strokeDasharray="1.2 1" vectorEffect="non-scaling-stroke" />
            <line x1={xL} x2={X_DATA_END} y1={yBot} y2={yBot}
                  stroke={rgba(chartInk.ink, 0.55)} strokeWidth={0.35}
                  strokeDasharray="1.2 1" vectorEffect="non-scaling-stroke" />
          </g>
        )
      })()}
    </g>
  )
}


/** SecondaryGreek — which initiator profile renders in the far-right strip. */
export type SecondaryGreek = 'delta' | 'charm' | 'vanna'

/**
 * SecondaryProfileLayer — far-right strip showing ONE of Delta / Charm / Vanna.
 *
 * Sits at x = X_DATA_END..X_DATA_END+barWidth, leaning inward toward candles
 * (mirrors GammaProfileLayer). Which Greek renders is controlled by `which`:
 *
 *   delta → DEX exposure across the chain; gentle multimodal shape
 *   charm → time-decay forcing; dominates after 2pm ET (Paul's framework)
 *   vanna → IV-flow sensitivity; bidirectional initiator
 *
 * Why one component for three Greeks: identical math, identical visual
 * grammar (tanh length, per-peak VAs, sign-by-color). Avoids three near-
 * identical components and lets the App-level dropdown swap profiles with
 * zero allocation churn.
 *
 *   bar length = |smoothed_X| / max(|smoothed_X|) * barWidth — linear-normalized
 *   bar color  = sign(smoothed_X), saturation = tanh-scaled by ratio_scale
 *   peak lines = local |smoothed_X| maxima, side-tagged
 *   POC + VA   = strip-confined (Edwin: secondary signal stays on its strip)
 */
function SecondaryProfileLayer({
  profile,
  priceToY,
  barWidth,
  ratioScale,
  which,
  spot = null,
  smoothRadius = null,
}: {
  profile: OIProfileView
  priceToY: (p: number) => number
  barWidth: number
  ratioScale: number
  which: SecondaryGreek
  /** Index-scale spot — the moneyness seam for the delta leg-split (a call leg is
   *  ITM below spot, a put leg ITM above). null → leg-split disabled (net fallback). */
  spot?: number | null
  /** Greek shape-smoothing knob (null = server r=3). Covers the single-signal
   *  path AND the delta LEG-SPLIT mirror (raw legs ship; each leg re-smooths
   *  independently, so the seam stays exact). */
  smoothRadius?: number | null
}) {
  if (profile.rows.length === 0) return null

  // Pick the right signal + peaks + VAs + color based on `which`.
  // Defensive fallbacks (`|| []`, `|| 0`) handle the case where the API
  // payload predates the Charm/Vanna fields — without them, switching the
  // dropdown to charm/vanna crashes the render on `.map()` of undefined.
  // Safe to keep even after the backend always populates these fields.
  const cfg = (() => {
    switch (which) {
      case 'charm':
        return {
          values: resmoothGreek(
            profile.rows.map((r) => r.net_charm ?? 0),
            profile.rows.map((r) => r.smoothed_charm ?? 0), smoothRadius),
          peaks: profile.charm_peaks ?? [],
          vas: profile.va_charm_peaks ?? [],
          color: VA_COLOR_CHARM,
          keyPrefix: 'cp',
        }
      case 'vanna':
        return {
          values: resmoothGreek(
            profile.rows.map((r) => r.net_vanna ?? 0),
            profile.rows.map((r) => r.smoothed_vanna ?? 0), smoothRadius),
          peaks: profile.vanna_peaks ?? [],
          vas: profile.va_vanna_peaks ?? [],
          color: VA_COLOR_VANNA,
          keyPrefix: 'vp',
        }
      case 'delta':
      default:
        return {
          values: resmoothGreek(
            profile.rows.map((r) => r.net_delta ?? 0),
            profile.rows.map((r) => r.smoothed_delta ?? 0), smoothRadius),
          peaks: profile.delta_peaks ?? [],
          vas: profile.va_delta_peaks ?? [],
          color: VA_COLOR_DELTA,
          keyPrefix: 'dp',
        }
    }
  })()

  // Length normalized to true max; BRIGHTNESS via shared σ-tier logic.
  // HUE DECISION comes from server-computed per-row state (delta_state,
  // charm_state, vanna_state) — the r_greek σ dropdown no longer decides
  // grey verdicts; it only scales brightness. Delta uses the magnitude hue
  // (purple + red-for-rare-negative) since its sign is degenerate; charm/vanna
  // keep directional hue. All state fields: 'grey'|'pos'|'neg'.
  const maxAbs = Math.max(1, ...cfg.values.map((v) => Math.abs(v)))
  const secSigma = robustSigma(cfg.values)

  // Map server state → OiHue per greek type.
  const stateToHue = (state: string | undefined): OiHue => {
    const s = state ?? 'grey'
    if (s === 'grey') return 'gray'
    if (which === 'delta') {
      // Delta: positive mass = purple (magnitude/exhaustion), negative = red (rare bearish-DEX)
      return s === 'pos' ? 'delta' : 'red'
    }
    // Charm / Vanna: directional — pos = green, neg = red
    return s === 'pos' ? 'green' : 'red'
  }

  const barHeights = localBarHeights(profile.rows, priceToY)

  // ── Delta LEG-SPLIT — both legs at every strike, moneyness-colored ──
  // call leg (δc·C ≥ 0) grows RIGHT from a center axis, put leg ((δc−1)·P ≤ 0)
  // grows LEFT. Hue = class (green calls / red puts), lightness = moneyness:
  // deep OTM (speculative fuel), light ITM (winners/ballast).
  // Moneyness is a render-time fact — leg class + side of LIVE spot — so bars
  // re-classify as spot moves and the color seam always sits at the spot line.
  // Locked horns (light green below / light red above) and fuel-vs-winners read
  // as SHAPES.
  // Legs are the parity decomposition (sum exactly to smoothed_delta); absent
  // (null) on notional-unit books → falls through to the net bar below.
  const hasLegs = which === 'delta' && spot != null && profile.rows.some(
    (r) => r.smoothed_call_delta != null && r.smoothed_put_delta != null)
  if (hasLegs) {
    // Greek-smooth knob covers the legs too: re-smooth each leg from its raw
    // series when the payload ships them (each leg independently — Gaussian is
    // linear, so call+put still reconstructs the re-smoothed net exactly).
    // Older payloads without raw legs keep the server-smoothed legs.
    const hasRawLegs = profile.rows.some(
      (r) => r.raw_call_delta != null && r.raw_put_delta != null)
    const calls = hasRawLegs
      ? resmoothGreek(
          profile.rows.map((r) => r.raw_call_delta ?? 0),
          profile.rows.map((r) => r.smoothed_call_delta ?? 0), smoothRadius)
      : profile.rows.map((r) => r.smoothed_call_delta ?? 0)
    const puts = hasRawLegs
      ? resmoothGreek(
          profile.rows.map((r) => r.raw_put_delta ?? 0),
          profile.rows.map((r) => r.smoothed_put_delta ?? 0), smoothRadius)
      : profile.rows.map((r) => r.smoothed_put_delta ?? 0)
    const maxLeg = Math.max(1e-9, ...calls.map(Math.abs), ...puts.map(Math.abs))
    const legSigma = robustSigma([...calls, ...puts])
    // Axis PINNED at the center of the right lane (Edwin 2026-07-09: "width
    // = size, not position"). The knob scales leg LENGTH symmetrically around
    // the fixed axis, saturating at the lane so call legs never slide off
    // the canvas (the old axis = X_DATA_END + barWidth/2 moved with the knob).
    const lane = 100 - X_DATA_END
    const axisX = X_DATA_END + lane / 2
    const halfW = Math.min(barWidth, lane) / 2
    const ys = profile.rows.map((r) => priceToY(r.strike))
    return (
      <g pointerEvents="none">
        <line
          x1={axisX} y1={Math.min(...ys)} x2={axisX} y2={Math.max(...ys)}
          stroke={rgba(chartInk.inkDim, 0.25)} strokeWidth={0.5}
          vectorEffect="non-scaling-stroke"
        />
        {profile.rows.map((r, i) => {
          const y = priceToY(r.strike)
          const grey = (r.delta_state ?? 'grey') === 'grey'
          const callHue: OiHue = grey ? 'gray' : r.strike < spot ? 'callItm' : 'callOtm'
          const putHue: OiHue = grey ? 'gray' : r.strike > spot ? 'putItm' : 'putOtm'
          const lenC = profileBarLength(calls[i], maxLeg, halfW)
          const lenP = profileBarLength(puts[i], maxLeg, halfW)
          return (
            <g key={`dl-${r.strike}`}>
              {lenC > 0 && (
                <rect
                  x={axisX} y={y - barHeights[i] / 2} width={lenC} height={barHeights[i]}
                  fill={oiBarFill(tierMag(calls[i], legSigma), callHue, ratioScale)}
                  stroke="none" vectorEffect="non-scaling-stroke"
                />
              )}
              {lenP > 0 && (
                <rect
                  x={axisX - lenP} y={y - barHeights[i] / 2} width={lenP} height={barHeights[i]}
                  fill={oiBarFill(tierMag(puts[i], legSigma), putHue, ratioScale)}
                  stroke="none" vectorEffect="non-scaling-stroke"
                />
              )}
            </g>
          )
        })}
      </g>
    )
  }

  return (
    <g pointerEvents="none">
      {/* Bars PINNED to the viewBox right edge (x=100), growing LEFTWARD
          toward the candles — mirrors the Gamma layer (both right-side
          profiles "lean inward"). The width knob scales LENGTH only,
          saturating at the lane (Edwin 2026-07-09: size, not position —
          the old anchor X_DATA_END + barWidth slid with the knob). */}
      {profile.rows.map((r, i) => {
        const y = priceToY(r.strike)
        const len = profileBarLength(cfg.values[i], maxAbs, Math.min(barWidth, 100 - X_DATA_END))
        // HUE DECISION from server doctrine state for the selected greek.
        // Brightness (tierMag/secSigma) remains client-side.
        const rowState = which === 'delta' ? r.delta_state
          : which === 'charm' ? r.charm_state
          : r.vanna_state
        return (
          <rect
            key={`${cfg.keyPrefix}-${r.strike}`}
            x={100 - len}
            y={y - barHeights[i] / 2}
            width={len}
            height={barHeights[i]}
            fill={oiBarFill(tierMag(cfg.values[i], secSigma), stateToHue(rowState), ratioScale)}
            stroke="none"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}
      {/* No pivot line — the charm/vanna pivot was removed (it was ATM-pinned;
          see memory charm-pivot-mislocation). Drift direction now lives in the
          Multi-Timeframe Stack (structure_read). The strip is just the bars. */}
    </g>
  )
}


function CascadeLayer({
  cascades,
  priceToY,
}: {
  cascades: CascadeBand[]
  priceToY: (p: number) => number
}) {
  if (cascades.length === 0) return null
  return (
    <g>
      {cascades.map((c, i) => {
        const yTop = priceToY(c.top_price)
        const yBot = priceToY(c.bottom_price)
        // Ensure top is actually visually top (smaller y).
        const y = Math.min(yTop, yBot)
        const h = Math.max(0.4, Math.abs(yBot - yTop))
        const fillId = c.razor ? 'cascade-stripes-razor' : 'cascade-stripes'
        const outlineColor = rgb(c.razor ? chartInk.razor : chartInk.cascade)
        return (
          <g key={`cas-${i}`}>
            <rect
              x={0}
              y={y}
              width={X_DATA_END}
              height={h}
              fill={`url(#${fillId})`}
              stroke={outlineColor}
              strokeWidth={0.2}
              opacity={c.razor ? 0.55 : 0.4}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )
      })}
    </g>
  )
}

function capitalize(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1)
}

function BandLayer({
  bands,
  timeToX,
  priceToY,
}: {
  bands: CentroidBand[]
  timeToX: (t: number) => number
  priceToY: (p: number) => number
}) {
  // Group by side + percentile so we can pair adjacent bands.
  const byCall: Record<number, CentroidBand> = {}
  const byPut: Record<number, CentroidBand> = {}
  for (const b of bands) {
    if (b.side === 'call') byCall[b.percentile] = b
    else if (b.side === 'put') byPut[b.percentile] = b
  }

  const polygonPoints = (lo: CentroidBand, hi: CentroidBand): string => {
    const pts: string[] = []
    for (const p of lo.points) {
      pts.push(`${timeToX(p.time).toFixed(2)},${priceToY(p.value).toFixed(2)}`)
    }
    for (let i = hi.points.length - 1; i >= 0; i--) {
      const p = hi.points[i]
      pts.push(`${timeToX(p.time).toFixed(2)},${priceToY(p.value).toFixed(2)}`)
    }
    return pts.join(' ')
  }

  const pairs: Array<[number, number]> = [
    [10, 20], [20, 30], [30, 40], [40, 50],
  ]

  return (
    <>
      {pairs.map(([lo, hi]) => {
        const opac = BAND_FILL_OPAC[`${lo}-${hi}`] ?? 0.1
        const out: React.ReactNode[] = []
        if (byCall[lo] && byCall[hi]) {
          out.push(
            <polygon
              key={`bc-${lo}-${hi}`}
              points={polygonPoints(byCall[lo], byCall[hi])}
              fill="#34d399"
              fillOpacity={opac}
              stroke="none"
              vectorEffect="non-scaling-stroke"
            />,
          )
        }
        if (byPut[lo] && byPut[hi]) {
          out.push(
            <polygon
              key={`bp-${lo}-${hi}`}
              points={polygonPoints(byPut[lo], byPut[hi])}
              fill="#f87171"
              fillOpacity={opac}
              stroke="none"
              vectorEffect="non-scaling-stroke"
            />,
          )
        }
        return <g key={`pair-${lo}-${hi}`}>{out}</g>
      })}
    </>
  )
}

/** Options tape VWAP + OTM percentile wings (theta view). The c50/p50 edges
 *  are drawn as SOLID LINES — the successors of the retired per-side linregs:
 *  running medians of OTM traded volume, order statistics that cannot leave
 *  their own distribution. Violet center = the tape LIS. */
function TapeVwapLayer({
  lis,
  zoneLo,
  zoneHi,
  bands,
  timeToX,
  priceToY,
}: {
  /** the control point line (anchored flip, or glided flow flip per lens) */
  lis: LinePoint[]
  /** flip ZONE bounds — the "grey spot" where net premium changes sign */
  zoneLo: LinePoint[]
  zoneHi: LinePoint[]
  bands: CentroidBand[]
  timeToX: (t: number) => number
  priceToY: (p: number) => number
}) {
  const byCall: Record<number, CentroidBand> = {}
  const byPut: Record<number, CentroidBand> = {}
  for (const b of bands) {
    if (b.side === 'call') byCall[b.percentile] = b
    else if (b.side === 'put') byPut[b.percentile] = b
  }

  const polygonPoints = (lo: CentroidBand, hi: CentroidBand): string => {
    const pts: string[] = []
    for (const p of lo.points) {
      pts.push(`${timeToX(p.time).toFixed(2)},${priceToY(p.value).toFixed(2)}`)
    }
    for (let i = hi.points.length - 1; i >= 0; i--) {
      const p = hi.points[i]
      pts.push(`${timeToX(p.time).toFixed(2)},${priceToY(p.value).toFixed(2)}`)
    }
    return pts.join(' ')
  }

  const pairs: Array<[number, number]> = [[50, 75], [75, 90], [90, 95]]

  return (
    <g>
      {pairs.map(([lo, hi]) => {
        const opac = TAPE_FILL_OPAC[`${lo}-${hi}`] ?? 0.06
        const out: React.ReactNode[] = []
        if (byCall[lo] && byCall[hi]) {
          out.push(
            <polygon
              key={`twc-${lo}-${hi}`}
              points={polygonPoints(byCall[lo], byCall[hi])}
              fill="#34d399"
              fillOpacity={opac}
              stroke="none"
            />,
          )
        }
        if (byPut[lo] && byPut[hi]) {
          out.push(
            <polygon
              key={`twp-${lo}-${hi}`}
              points={polygonPoints(byPut[lo], byPut[hi])}
              fill="#f87171"
              fillOpacity={opac}
              stroke="none"
            />,
          )
        }
        return <g key={`tw-${lo}-${hi}`}>{out}</g>
      })}
      {/* c50 / p50 — the per-side median lines (linreg successors) */}
      {byCall[50] && (
        <LinePath points={byCall[50].points} timeToX={timeToX} priceToY={priceToY}
          stroke="#34d399" strokeWidth={1.1} opacity={0.9} />
      )}
      {byPut[50] && (
        <LinePath points={byPut[50].points} timeToX={timeToX} priceToY={priceToY}
          stroke="#f87171" strokeWidth={1.1} opacity={0.9} />
      )}
      {/* TAPE FLIP ZONE — the "grey spot" where net OTM premium changes
          ownership (call$ − put$ sign flip, gaussian-smoothed, same grammar
          as the white net-OI LIS). Zone = bracketing strikes; wide zone =
          ambivalent tape, one strike = decisive. Line = the control point:
          above it call-owned (pullbacks to it are entries), lost = bias flip. */}
      {zoneLo.length >= 2 && zoneHi.length >= 2 && (
        <polygon
          points={[
            ...zoneLo.map((p) => `${timeToX(p.time).toFixed(2)},${priceToY(p.value).toFixed(2)}`),
            ...zoneHi.slice().reverse().map((p) => `${timeToX(p.time).toFixed(2)},${priceToY(p.value).toFixed(2)}`),
          ].join(' ')}
          fill={TAPE_VWAP_COLOR}
          fillOpacity={0.10}
          stroke="none"
        />
      )}
      <LinePath points={lis} timeToX={timeToX} priceToY={priceToY}
        stroke={TAPE_VWAP_COLOR} strokeWidth={1.5} opacity={0.95} />
    </g>
  )
}

function LinePath({
  points,
  timeToX,
  priceToY,
  stroke,
  strokeWidth,
  opacity,
  dasharray,
}: {
  points: LinePoint[]
  timeToX: (t: number) => number
  priceToY: (p: number) => number
  stroke: string
  strokeWidth: number
  opacity: number
  dasharray?: string
}) {
  if (points.length < 2) return null
  // Dedupe + sort defensively (Sierra writes the occasional duplicate timestamp).
  const map = new Map<number, LinePoint>()
  for (const p of points) map.set(p.time, p)
  const sorted = Array.from(map.values()).sort((a, b) => a.time - b.time)
  const d = sorted
    .map((p, i) => {
      const x = timeToX(p.time).toFixed(2)
      const y = priceToY(p.value).toFixed(2)
      return `${i === 0 ? 'M' : 'L'}${x},${y}`
    })
    .join(' ')
  return (
    <path
      d={d}
      fill="none"
      stroke={stroke}
      strokeWidth={strokeWidth}
      opacity={opacity}
      strokeLinejoin="round"
      strokeLinecap="round"
      strokeDasharray={dasharray}
      vectorEffect="non-scaling-stroke"
    />
  )
}

function CandleLayer({
  bars,
  timeToX,
  priceToY,
}: {
  bars: CandlePoint[]
  timeToX: (t: number) => number
  priceToY: (p: number) => number
}) {
  if (bars.length === 0) return null
  // Dedupe + sort.
  const map = new Map<number, CandlePoint>()
  for (const b of bars) map.set(b.time, b)
  const sorted = Array.from(map.values()).sort((a, b) => a.time - b.time)

  // Bar width: derive from typical spacing. We don't draw individual
  // candles past the volume threshold — overlap would be visually noisy.
  // For 1000+ bars in 6.5h, candle bodies should be ~0.06 viewBox units wide.
  const spacingPct = X_DATA_END / Math.max(60, sorted.length)
  const bodyWidth = Math.max(0.04, Math.min(0.3, spacingPct * 0.7))

  return (
    <g>
      {sorted.map((b) => {
        const x = timeToX(b.time)
        const yO = priceToY(b.open)
        const yC = priceToY(b.close)
        const yH = priceToY(b.high)
        const yL = priceToY(b.low)
        const isUp = b.close >= b.open
        const color = rgb(isUp ? tokenHues.up : tokenHues.down)
        const top = Math.min(yO, yC)
        const bot = Math.max(yO, yC)
        return (
          <g key={`c-${b.time}`}>
            {/* Wick */}
            <line
              x1={x}
              y1={yH}
              x2={x}
              y2={yL}
              stroke={color}
              strokeWidth={0.4}
              vectorEffect="non-scaling-stroke"
            />
            {/* Body */}
            <rect
              x={x - bodyWidth / 2}
              y={top}
              width={bodyWidth}
              height={Math.max(0.04, bot - top)}
              fill={color}
              stroke="none"
            />
          </g>
        )
      })}
    </g>
  )
}


function LinregLayer({
  linregs,
  timeToX,
  priceToY,
}: {
  linregs: LinregLine[]
  timeToX: (t: number) => number
  priceToY: (p: number) => number
}) {
  return (
    <g>
      {linregs.map((L, i) => {
        const x0 = timeToX(L.open_time)
        const y0 = priceToY(L.open_value)
        const x1 = timeToX(L.close_time)
        const y1 = priceToY(L.close_value)
        const color = rgb(L.side === 'call' ? chartInk.linregCall : chartInk.linregPut)

        if (L.method === 'session_ols') {
          return (
            <line
              key={`lr-${i}`}
              x1={x0}
              y1={y0}
              x2={x1}
              y2={y1}
              stroke={color}
              strokeWidth={0.5}
              opacity={0.32}
              strokeDasharray="0.5 0.7"
              vectorEffect="non-scaling-stroke"
            />
          )
        }
        // EWMA — three visual layers: translucent ribbon, glow, dashed line w/ marching ants
        return (
          <g key={`lr-${i}`}>
            <line
              x1={x0}
              y1={y0}
              x2={x1}
              y2={y1}
              stroke={color}
              strokeWidth={3.5}
              opacity={0.16}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
            <line
              className="linreg-ants"
              x1={x0}
              y1={y0}
              x2={x1}
              y2={y1}
              stroke={color}
              strokeWidth={0.8}
              opacity={0.92}
              strokeDasharray="1.2 0.6"
              strokeLinecap="round"
              filter={`drop-shadow(0 0 0.4px ${color}) drop-shadow(0 0 0.9px ${color})`}
              vectorEffect="non-scaling-stroke"
            />
          </g>
        )
      })}
    </g>
  )
}

// ── Pure utility functions ─────────────────────────────────────────────────

/**
 * Y-axis auto-fit: pick min/max from data whose timestamps fall inside
 * the current viewport. Time-less data (levels) is always included so
 * the user can see structural lines even when zoomed far in. Trading
 * convention — y follows x.
 */
function computePriceRange(data: ChartData, viewport?: Viewport): { yMin: number; yMax: number } {
  const inVP = viewport
    ? (t: number) => t >= viewport.start && t <= viewport.end
    : () => true

  let lo = Infinity
  let hi = -Infinity

  for (const b of data.bars) {
    if (!inVP(b.time)) continue
    if (b.low < lo) lo = b.low
    if (b.high > hi) hi = b.high
  }
  for (const p of [...data.vwap_today, ...data.vwap_5d, ...data.vwap_20d]) {
    if (!inVP(p.time)) continue
    if (p.value < lo) lo = p.value
    if (p.value > hi) hi = p.value
  }
  // Levels: include always — they're horizontal reference lines that
  // should stay visible at any zoom.
  for (const L of data.levels) {
    if (L.price_contract < lo) lo = L.price_contract
    if (L.price_contract > hi) hi = L.price_contract
  }
  // Bands + linregs: include their values that intersect the viewport.
  for (const b of data.bands) {
    for (const p of b.points) {
      if (!inVP(p.time)) continue
      if (p.value < lo) lo = p.value
      if (p.value > hi) hi = p.value
    }
  }
  for (const b of data.tape_bands ?? []) {
    for (const p of b.points) {
      if (!inVP(p.time)) continue
      if (p.value < lo) lo = p.value
      if (p.value > hi) hi = p.value
    }
  }
  for (const p of [...(data.tape_lis ?? []), ...(data.tape_lis_flow ?? [])]) {
    if (!inVP(p.time)) continue
    if (p.value < lo) lo = p.value
    if (p.value > hi) hi = p.value
  }
  for (const L of data.linregs) {
    // Linreg endpoints span the whole session — only filter if endpoints
    // are inside viewport, else interpolate at viewport edges.
    if (inVP(L.open_time)) {
      if (L.open_value < lo) lo = L.open_value
      if (L.open_value > hi) hi = L.open_value
    }
    if (inVP(L.close_time)) {
      if (L.close_value < lo) lo = L.close_value
      if (L.close_value > hi) hi = L.close_value
    }
  }

  if (!isFinite(lo) || !isFinite(hi)) return { yMin: 0, yMax: 1 }
  const range = hi - lo || hi * 0.005 || 1
  return { yMin: lo - range * 0.04, yMax: hi + range * 0.04 }
}

function computeYTicks(
  yMin: number,
  yMax: number,
): Array<{ price: number; y: number }> {
  const range = yMax - yMin
  if (!isFinite(range) || range <= 0) return []
  // Aim for ~6 ticks at round numbers.
  const targetTicks = 6
  const rawStep = range / targetTicks
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const niceMultipliers = [1, 2, 2.5, 5, 10]
  const step =
    niceMultipliers
      .map((m) => m * magnitude)
      .reduce((best, candidate) =>
        Math.abs(candidate - rawStep) < Math.abs(best - rawStep) ? candidate : best,
      )
  const start = Math.ceil(yMin / step) * step
  const ticks: Array<{ price: number; y: number }> = []
  for (let p = start; p <= yMax && ticks.length < 14; p += step) {
    const frac = (yMax - p) / range
    ticks.push({ price: p, y: Y_DATA_TOP + frac * Y_DATA_HEIGHT })
  }
  return ticks
}


