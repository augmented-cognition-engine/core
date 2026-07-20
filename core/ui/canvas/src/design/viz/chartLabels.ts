// Pure label-descriptor helpers for chart annotation labels.
// Mirror the inline derivations in PriceChart.tsx so a future HTML overlay
// can render these as positioned divs (avoiding SVG-text distortion).
// No rendering, no side effects — pure functions only.

import { robustSigma } from './chartMath'
import type { OIProfileView } from './types'

// oiFlowLabel (the flow-fulcrum label) + its strikeStep helper DELETED
// 2026-07-09 — exported and tested but never mounted (orphaned when the Past
// lens was removed 7/08); the flow-fulcrum read now lives in the amber flow
// LIS band.

// ── Wall Δ tags ───────────────────────────────────────────────────────────────
// Mirrors PriceChart lines ~1090-1094 (walls map) + ~1181-1189 (tag text).
// Emits descriptors only for MAJOR clusters whose net_change clears this
// profile's OWN noise floor: k·robustSigma(net_change). OI counts are
// scale-symmetric across complexes, so the floor is derived per-profile (no
// fixed magic count, no cross-complex divisor). `built` = true when
// net_change ≥ 0 (wall hardening); false = draining.

const WALL_FLOOR_K = 1.0   // floor at 1σ of this profile's net_change spread.

export function wallLabels(
  profile: OIProfileView,
): { strike: number; text: string; built: boolean }[] {
  // Cold-start (F1/OIR3): net_change is a full-book Δ vs no prior snapshot, so
  // every wall reads as freshly "built" — fabricated forward structure. Suppress
  // wall build/drain tags while warming (the walls themselves are net-OI peaks,
  // which the peak/VA layer still shows; only the Δ tag is dishonest here).
  if (profile.oi_flow_warming) return []
  const rows = profile.rows ?? []
  const walls = (profile.net_clusters ?? []).filter((c) => c.magnitude === 'major')
  const floor = WALL_FLOOR_K * robustSigma(rows.map((r) => r.net_change ?? 0))
  const out: { strike: number; text: string; built: boolean }[] = []
  for (const w of walls) {
    const near = rows.length
      ? rows.reduce((b, r) =>
          Math.abs(r.strike - w.strike) < Math.abs(b.strike - w.strike) ? r : b,
        )
      : null
    const chg = near?.net_change ?? 0
    if (Math.abs(chg) <= floor) continue
    const built = chg >= 0
    const mag = (Math.abs(chg) / 1000).toFixed(Math.abs(chg) >= 10000 ? 0 : 1)
    out.push({ strike: w.strike, built, text: `${built ? '▲' : '▼'} ${built ? '+' : '−'}${mag}k` })
  }
  return out
}

