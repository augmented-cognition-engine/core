// core/ui/canvas/src/design/viz/types.ts
//
// The price-chart primitive's DATA CONTRACT.
//
// Lifted from a consuming extension's state payload, but deliberately owned here:
// a design-system primitive must not import types from any application, or the
// kernel would depend on an extension (which noExtensionLeakage forbids, rightly).
// Any producer that can emit these shapes can drive the chart — the primitive knows
// nothing about where the numbers came from.
//
// Prices are in SOURCE units (the index/ETF scale, e.g. QQQ), never contract units.

export type CandlePoint = {
  time: number    // UTC epoch seconds (Lightweight Charts native)
  open: number
  high: number
  low: number
  close: number
}

export type LinePoint = {
  time: number
  value: number
}

export type LevelMarker = {
  key: string                  // "HC_1" / "COTMC" / "GEX_PTRANS" / ...
  price_contract: number       // contract-scale price (NQ or ES)
  role: 'hc' | 'target' | 'entry' | 'exhaustion' | 'pivot' | string
  role_label: string
  cluster_id: string           // references Cluster.id in ChartData.clusters
}

export type Cluster = {
  id: string                   // "zone_1" / "zone_2" / ...
  members: string[]            // level keys in this cluster
  lo_qqq: number
  hi_qqq: number
  lo_price: number             // contract-scale lower bound
  hi_price: number             // contract-scale upper bound
  dominant_role: string
  role_summary: string
  greeks: string[]             // Greek-transition labels active in zone
  dealers: string              // 1-2 sentences on participant/dealer behavior
  what_to_watch: string        // the live tell
  if_above: string
  if_below: string
}

export type CentroidBand = {
  percentile: 10 | 20 | 30 | 40 | 50 | number
  side: 'call' | 'put' | string
  points: LinePoint[]          // time + contract-scale value
}

export type LinregLine = {
  side: 'call' | 'put' | string
  method: 'session_ols' | 'ewma' | string
  open_time: number            // UTC epoch sec (session start)
  open_value: number           // contract-scale
  close_time: number           // UTC epoch sec (session close 16:00 ET)
  close_value: number          // contract-scale projection
}

export type CascadeBand = {
  top_price: number            // contract-scale upper bound
  bottom_price: number         // contract-scale lower bound
  side: 'upside' | 'downside' | string
  greeks: string[]             // constituent Greeks (lowercase)
  width_pct: number            // band width as % of spot
  razor: boolean               // tight cluster (width_pct < 0.15)
}

export type CharmLine = {
  price_contract: number
  side: 'hi' | 'lo'
  label: string
}

export type ZoneBand = {
  bias: 'long' | 'short' | 'skip' | string
  bias_authored: boolean
  lo_price: number             // contract-scale lower bound
  hi_price: number             // contract-scale upper bound
  active: boolean
  description: string
}

export type OIProfileNetPeak = {
  strike: number
  smoothed_net: number     // signed magnitude
  side: 'call' | 'put' | string
}

export type OIProfileValueArea = {
  poc_strike: number | null
  vah: number | null
  val: number | null
  area_fraction: number
  total_magnitude: number
}

export type OIProfileRow = {
  strike: number
  call_oi: number
  put_oi: number
  net_oi: number
  net_change: number        // day-over-day Δ net_oi (flow): >0 built, <0 drained
  call_change?: number      // day-over-day Δ call_oi
  put_change?: number       // day-over-day Δ put_oi
  total_change?: number     // day-over-day Δ total_oi
  total_oi: number
  net_gamma: number         // raw net_gamma per strike
  net_delta: number         // raw net_delta per strike (DEX exposure)
  net_charm: number         // raw net_charm per strike (charm decay flow)
  net_vanna: number         // raw net_vanna per strike (vanna IV flow)
  smoothed_total: number    // Gaussian-smoothed total_oi (envelope value)
  smoothed_net: number      // Gaussian-smoothed net_oi (signed)
  smoothed_call: number     // Gaussian-smoothed call_oi (single-side)
  smoothed_put: number      // Gaussian-smoothed put_oi (single-side)
  smoothed_gamma: number    // Gaussian-smoothed net_gamma (signed)
  smoothed_delta: number    // Gaussian-smoothed net_delta (signed)
  // Per-leg delta (parity decomposition: call leg ≥ 0, put leg ≤ 0; legs sum to
  // smoothed_delta). null on books where the legs can't be recovered (notional GE
  // units) — the delta strip then falls back to the single net bar.
  smoothed_call_delta?: number | null
  smoothed_put_delta?: number | null
  // Raw (unsmoothed) legs — feed the client greek-smooth knob so the delta
  // leg-split re-smooths like the single-signal greeks. Same null contract.
  raw_call_delta?: number | null
  raw_put_delta?: number | null
  smoothed_charm: number    // Gaussian-smoothed net_charm (signed)
  smoothed_vanna: number    // Gaussian-smoothed net_vanna (signed)
  // Server doctrine net-OI verdict: 'grey' | 'call' | 'put'. Computed ONCE
  // server-side from the combined colored-test (smoothed_net r3, grey_sigma 0.5,
  // rel_floor 0.05). The UI consumes this for the NET hue DECISION so bar colors
  // can never disagree with the LIS band. Brightness/σ knobs still scale
  // intensity client-side, but NEVER override this grey/call/put verdict.
  net_state: 'grey' | 'call' | 'put'
  // Per-greek doctrine verdicts — same combined-test as detect_foci:
  // grey_sigma=1.0 (GREY_SIGMA_GREEK), rel_floor=0.05, on the r3-smoothed series.
  // Resampled rows inherit from nearest source strike. The UI uses these for the
  // grey-vs-color DECISION on gamma/delta/charm/vanna profiles. The r_greek σ
  // dropdown no longer decides grey verdicts — only brightness/length scaling.
  // 'grey' | 'pos' | 'neg'
  gamma_state: 'grey' | 'pos' | 'neg'
  delta_state: 'grey' | 'pos' | 'neg'
  charm_state: 'grey' | 'pos' | 'neg'
  vanna_state: 'grey' | 'pos' | 'neg'
  // Change-LIS hue: server doctrine on net_change direction at this strike.
  // null while oi_flow_warming (no prior same-expiry snapshot). Same
  // greyMask/flip logic as net_state but applied to the smoothed net_change.
  // 'grey' | 'call' | 'put' | null
  net_change_state: 'grey' | 'call' | 'put' | null
}

export type OIProfileView = {
  rows: OIProfileRow[]
  peaks_upper: OIProfileNetPeak[]
  peaks_lower: OIProfileNetPeak[]
  net_peaks: OIProfileNetPeak[]
  net_clusters: OIProfileNetCluster[]
  gamma_peaks: OIProfileNetPeak[]
  delta_peaks: OIProfileNetPeak[]
  charm_peaks: OIProfileNetPeak[]
  vanna_peaks: OIProfileNetPeak[]
  dex_zone: OIProfileTransZone | null
  gex_zone: OIProfileTransZone | null
  va_oi_peaks: OIProfileValueArea[]
  va_gamma_peaks: OIProfileValueArea[]
  va_delta_peaks: OIProfileValueArea[]
  va_charm_peaks: OIProfileValueArea[]
  va_vanna_peaks: OIProfileValueArea[]
  va_call_peaks: OIProfileValueArea[]  // per-peak call-OI VAs (peak + 70%)
  va_put_peaks: OIProfileValueArea[]   // per-peak put-OI VAs
  va_net_peaks: OIProfileValueArea[]   // per-peak |net-OI| VAs
  va_call: OIProfileValueArea | null   // POC=COI, VAH=COTMC
  va_put: OIProfileValueArea | null    // POC=POI, VAL=COTMP
  sign_flips: OIProfileSignFlip[]
  radius_total: number       // bandwidth for the mass / bar-length signal
  radius_net: number         // bandwidth for the direction / color signal
  radius_gamma: number       // bandwidth for the gamma signal
  radius_delta: number       // bandwidth for the delta signal
  radius_charm: number       // bandwidth for the charm signal
  radius_vanna: number       // bandwidth for the vanna signal
  sigma_total: number        // = radius_total / 3
  sigma_net: number          // = radius_net / 3
  sigma_gamma: number        // = radius_gamma / 3
  sigma_delta: number        // = radius_delta / 3
  sigma_charm: number        // = radius_charm / 3
  sigma_vanna: number        // = radius_vanna / 3
  dex_ptrans: number | null
  dex_ntrans: number | null
  spot_contract: number | null
  contract_label: string
  expiry: string | null            // 0DTE expiry actually pulled (YYYY-MM-DD)
  oi_flow_warming?: boolean        // F1/OIR3: no prior same-expiry snapshot yet
                                   // (cold-start) → net_change/flow is fabricated;
                                   // walls + flow-pull suppressed, posture only.
  structure_read?: OIStructureRead | null  // cumulative gamma-condition + charm-drift
  // Canonical LIS from server flip_zone on $1-strike grid — matches levels.txt/Sierra.
  // Core = r=3 smoothed net (min_run=3 guard). Halo retired 2026-06-10 (always null).
  lis_lo?: number | null
  lis_hi?: number | null
  lis_halo_lo?: number | null   // retired — always null
  lis_halo_hi?: number | null   // retired — always null
  // Delta-LIS band — directional-exposure sign-flip zone at FIXED radius 3.
  // Mirrors DELTA_LIS_LO/HI in levels.txt. Null on unifocal-delta days or
  // when the two foci don't bracket spot.
  delta_lis_lo?: number | null
  delta_lis_hi?: number | null
  // Change-LIS band — flip zone of day-over-day net_change (the flow fulcrum).
  // Computed server-side (same flip_zone on smoothed net_change at r=3).
  // null while oi_flow_warming (no prior same-expiry snapshot).
  change_lis_lo?: number | null
  change_lis_hi?: number | null
  // Previous session's net-OI LIS — yesterday's flip_zone lo/hi. Enables
  // the overnight equilibrium-shift read (past→present LIS offset). Null
  // when the prior session's snapshot is unavailable.
  prev_lis_lo?: number | null
  prev_lis_hi?: number | null
  // (future_lis_lo/hi + forward types deleted 2026-07-09 — the future strip
  // retired; the server may still ship them from the artifact until the
  // artifact-side cleanup lands. rolling_lis replaced the read.)
  // Delta — the two-layer flow instrument over the union {0-4 DTE} ∪ {UQ}
  // overnight change. LIS (lis_lo/lis_hi) = server flip_zone on r=3-smoothed
  // d_net — the balance/handover line; null on one-sided nights. activity =
  // Δ(call+put) per strike, legs same-signed — the direction-blind "where
  // the work happened" heat (empty on pre-field maps). Absent when the
  // corridor map lacks the lens.
  delta?: {
    asof: string
    strikes: number[]
    d_net: number[]
    // churn = |Δcall|+|Δput| — the flow strip's bar height (never cancels;
    // a rotation is the longest bar). activity = Δ(call+put) diagnostic.
    churn?: number[]
    activity?: number[]
    // Two-radius flow LIS (the 0DTE definition verbatim): core = flip_zone
    // on r=3-smoothed d_net, halo = flip_zone on r=6.
    lis_lo?: number | null
    lis_hi?: number | null
    lis_halo_lo?: number | null
    lis_halo_hi?: number | null
  } | null
  // Rolling-LIS overlays — flip zones of the standing aggregate net-OI of the
  // next 5 / 3 expiries BEYOND today (LIS only, no profile; today's flip is
  // the Present LIS). Same shared two-radius routine as the flow LIS: core
  // (lo/hi, r=3) + halo (halo_lo/hi, r=6), spot-windowed election. A window
  // is null when its book is one-sided or absent.
  rolling_lis?: {
    asof?: string
    next5?: { lo: number; hi: number; halo_lo?: number | null; halo_hi?: number | null } | null
    next3?: { lo: number; hi: number; halo_lo?: number | null; halo_hi?: number | null } | null
  } | null
  // (future_profile type deleted 2026-07-09 with the future strip.)
  // Secondary net-OI balance zones (grey shelves, NOT the true LIS), server-detected
  // and ordered from the LIS out (BAL_1 nearest). Identical to Sierra's BAL_n keys.
  balance_zones?: BalanceZone[]
  // Shape-aware read — per-layer archetypes + role hierarchy + playbook (Spec 2).
  // {} / undefined when unavailable. Rendering type refined by the chip slice.
  shape_read?: ShapeRead
  charm_centroid?: {
    centroid?: number | null
    intensity?: number | null
    push?: number | null
  }
}

export type WindSide = {
  bias: 'up' | 'down' | null
  kind?: string                 // tailwind | headwind | sword | asleep | pinned
  conviction: WindConviction
  ratio: number | null          // display-only; null when a side is empty
  /** True when one side is near-totally dominant (|imbalance| >= 0.95): the weak side is a tiny
   *  fraction, so the heavy/light ratio is noise — show "one-sided", not a number. */
  extreme?: boolean
  heavy: 'left' | 'right' | null
  strength: number
  active: boolean
  imbalance: number
  left: number
  right: number
  dvol?: number
  // v1.5 (vanna only): the two vol branches, repriced from the live book via
  // the unified-delta engine — flow = |Δ_agg(σ±bump) − Δ_agg(σ)|, direction =
  // the doctrine blades; favored = the term-structure prior (null = no prior).
  branches?: {
    bump_pts: number
    expansion: { bias: 'down'; flow: number }
    compression: { bias: 'up'; flow: number }
    favored: 'expansion' | 'compression' | null
  } | null
  // v1.5 (charm only): into-close cumulative decay repricing at quarters of
  // the remaining session — the ramp bars' computed magnitudes.
  ramp?: { fracs: number[]; flows: number[]; total: number } | null
}

export type WindRead = {
  positioning: WindPositioning   // delta lean
  regime: WindRegime             // gamma: pin (long) vs amplify (short)
  charm: WindSide
  vanna: WindSide
  net: WindNet
  // gamma peaks = MAGNETS (the pull), one each side of spot. NOT walls — walls are
  // net-OI clusters, a separate layer. Drawn-to in pin; break-and-run in amplify.
  gamma_magnets: {
    upper: number | null         // peak above spot
    lower: number | null         // peak below spot
  }
  // State trajectory (2026-07-10): the delta STATE repriced to the close,
  // ceteris paribus (price/vol frozen, time runs out) — hemisphere-split,
  // SIGNED sibling of charm.ramp. Describes the BOOK's one-sidedness evolving,
  // never price direction. Absent on GE view / cold / degenerate builds.
  trajectory?: {
    now: { lhp: number; rhp: number; net: number; gross: number; strength: number; structure: string }
    close: { lhp: number; rhp: number; net: number; gross: number; strength: number; structure: string }
    direction: 'flipping' | 'strengthening' | 'eroding' | 'stable'
  } | null
}

export type ChartData = {
  bars: CandlePoint[]
  vwap_today: LinePoint[]
  vwap_5d: LinePoint[]
  vwap_20d: LinePoint[]
  levels: LevelMarker[]
  clusters: Cluster[]
  bands: CentroidBand[]
  linregs: LinregLine[]
  tape_vwap?: LinePoint[]      // options tape VWAP (theta view) — violet running LIS
  tape_vwap_flow?: LinePoint[] // flow lens: decayed full-chain vwap (solid line, lens=flow)
  tape_vwap_otm?: LinePoint[]  // OTM-only sibling (at-print speculation pool) — dashed violet
  tape_vwap_otm_decayed?: LinePoint[]  // flow lens decayed OTM center (undrawn — research)
  tape_lis_zone_lo?: LinePoint[]       // flip ZONE (the grey spot) — bracketing strikes
  tape_lis_zone_hi?: LinePoint[]
  tape_flis_zone_lo?: LinePoint[]
  tape_flis_zone_hi?: LinePoint[]
  tape_bands_decayed?: CentroidBand[]  // flow lens wings (fc50/fp50 = momentum lines)
  tape_lis?: LinePoint[]               // CONTROL POINT (violet): net-premium flip — fair value
  tape_lis_flow?: LinePoint[]          // flow control point — the live front line
  tape_monet?: {
    call_pct: number | null; put_pct: number | null
    call_depth_x?: number | null; put_depth_x?: number | null  // P&L multiple if held
  } | null
  tape_flow_alpha?: number | null  // flow mass vs session peak — fades thin flow
  tape_otm_flow?: {            // the AMOUNT tell (premium $): calls adding faster than puts?
    call_day: number; put_day: number; cp_day: number | null
    call_30m: number; put_30m: number; cp_30m: number | null
  } | null
  tape_bands?: CentroidBand[]  // OTM wing percentiles 50/75/90/95 per side
  cascades: CascadeBand[]
  zones: ZoneBand[]
  charm_lines: CharmLine[]
  cotmc: number | null   // upside monetization target (theta: derive.cotm OTM-delta balance; else delta grey-edge)
  cotmp: number | null   // downside monetization target (theta: derive.cotm; else delta grey-edge)
  cotmc_zone?: number[] | null   // [lo, hi] — the concentration core (densest-half window) around COTMC (theta only); null otherwise
  cotmp_zone?: number[] | null   // [lo, hi] — the concentration core (densest-half window) around COTMP (theta only); null otherwise
  cotmc_fan?: Record<string, number> | null   // p10..p90 monetization percentiles (premarket-static; theta only)
  cotmp_fan?: Record<string, number> | null
  cotm_progress?: { call: number | null; put: number | null; basis: string | null } | null
  // self-computed per-greek transition-price gate ladder (theta only): where each greek's
  // side flips ITM↔OTM (from→to = the Expected Transition). cascade_id groups stacked
  // crossings (a small move trips a chain → acceleration); null for an isolated rung.
  // v2 (2026-07-10): FULL re-evaluation rungs. kind='near' = the plane-flip
  // crossing nearest spot per greek/side; kind='terminal' (delta, below spot)
  // = the durable put-zone boundary ("the floor is structurally gone"), with
  // its zone_width as a stability metric. Terminal never joins cascades.
  transition_ladder?: {
    price: number; pct: number; greek: string; side: string
    from: string; to: string; cascade: boolean; cascade_id: number | null
    kind?: 'near' | 'terminal'; zone_width?: number
  }[]
  // Book's median strike gap (theta only) — the strike-native unit for the
  // cascade grammar (razor = flips stacked within ~one strike).
  strike_spacing?: number | null
  // Unified Delta shape (theta only; null otherwise): Δ(S;t,σ)=Σδ×OI as a curve, its
  // delta-flat (the zero — the neutral point), the deterministic charm+vanna projected
  // flat ("where it's headed"), the drift between them, and the dealer net-gamma regime.
  unified_shape?: UnifiedShape | null
}

export type BalanceZone = {
  lo: number     // lower strike bound (QQQ/SPX scale)
  hi: number     // upper strike bound
  width: number  // hi - lo (0 for a single-strike balance)
}

export type OIProfileNetCluster = {
  strike: number
  magnitude: 'major' | 'minor' | string
  side: 'call' | 'put' | string
}

export type OIProfileSignFlip = {
  strike: number
  direction: 'up' | 'down' | string
}

export type OIProfileTransZone = {
  lo: number | null
  hi: number | null
  ntrans: number | null
  ptrans: number | null
  width_strikes: number
  threshold: number
}

export type OIStructureRead = {
  gamma_condition: 'pin' | 'accel' | string
  gamma_force: number
  gamma_conviction: number          // |Σnet_gamma| / Σ|net_gamma|
  delta_force: number               // Σ net_delta (DEX lean)
  delta_conviction: number          // |Σnet_delta| / Σ|net_delta|
  coiled_spring: boolean            // delta offset/coiled — no clean directional structure
  dex_negative?: boolean            // rare bearish-DEX pocket (net delta went negative)
  dex_negative_strike?: number | null
  drift_bias: 'up' | 'down' | 'flat' | string
  drift_conviction: number          // active driver's conviction
  drift_driver: 'charm' | 'vanna' | string
  charm_force: number               // Σ net_charm (signed)
  charm_lhp: number
  charm_rhp: number
  vanna_lhp: number
  vanna_rhp: number
  vanna_rally: boolean
  vol_source: 'VXN' | 'VIX' | string | null  // NQ→VXN, ES→VIX
  vol_last: number | null
  vol_level: string | null          // compressed | normal | elevated | stress
  vol_velocity: string | null       // dropping_hard | rising | spiking | ... (context only)
  vol_position: string | null       // daily VWAP σ-band: in_range | above_2sd | below_2sd | ...
  vol_position_5d: string | null    // 5-day VWAP band position
  vol_vs_vwap: 'above' | 'below' | string | null
  vol_vwap_slope: 'rising' | 'falling' | 'flat' | string | null     // vol-index VWAP trend (regime)
  vol_vwap_slope_5d: 'rising' | 'falling' | 'flat' | string | null
  vol_regime: 'building' | 'compressing' | 'stable' | string | null  // early lean from VWAP slope
  vol_divergence?: boolean          // tail event but VWAP slope opposes (fading)
  term_structure?: TermStructure | null  // VIX index-family contango/backwardation (live, last-based)
}

export interface ShapeRead {
  layers?: Record<string, ShapeLayer>
  hierarchy?: Array<{ role: string; layer?: string; archetype?: string | null; sets?: string }>
  composed?: string[]
  playbook?: { meaning?: string; if_then?: Array<Record<string, unknown>>; kill?: string[] }
}

export type UnifiedShape = {
  curve: { price: number; delta: number }[]
  flat: number | null
  forward_flat: number | null
  drift: number | null
  net_gamma: number | null
  regime: 'pin' | 'accel' | null
}

export type WindConviction = {
  band: 'coin-toss' | 'mild' | 'strong' | 'entrenched' | string
  score: number
  directional: boolean
  chop_likely: boolean
}

export type WindNet = {
  bias: 'up' | 'down' | null
  driver: 'charm' | 'vanna' | 'both' | null
  aligned: boolean | null
  strength: number
}

export type WindPositioning = { bias: 'up' | 'down' | null; force: number; conviction: number }
export type WindRegime = { condition: 'pin' | 'amplify' | string; force: number; conviction: number }

export type TermStructure = {
  regime_ratio: number | null       // VIX/VIX3M  (30d÷90d)
  near_ratio: number | null         // VIX9D/VIX  (9d÷30d, the 0DTE front)
  wide_ratio: number | null         // VIX9D/VIX3M
  regime_flag: 'contango' | 'backwardation' | 'flat' | 'unknown'
  near_flag: 'contango' | 'backwardation' | 'flat' | 'unknown'
  quadrant: 'calm' | 'fear' | 'front_stress' | 'fear_rolling_off'
  bull_permission: boolean          // false under a backwardation regime
}


export interface ShapeLayer {
  greek?: string
  shape?: string
  archetype?: string | null
  zeropoint?: { lo: number; hi: number } | null
  value_area?: { lo: number; hi: number } | null   // total_oi only (sign-less mass envelope)
  delta_lis?: { lo: number; hi: number } | null
  foci?: Array<{ side: string; sign: string; strength: number; lo: number; hi: number }>
}
