import type { WindSide } from './types'

export type ParticleDrive = { intensity: number; direction: 'up' | 'down' | 'none' }

const clamp01 = (x: number): number => (x < 0 ? 0 : x > 1 ? 1 : x)

/**
 * Map a self-computed WindSide (charm or vanna) to particle drive.
 * Gated on `active`: an asleep wind — vanna when vol is flat, or a balanced charm —
 * returns 'none' so the chart renders nothing. intensity = conviction.score (0..1).
 */
export function windToParticles(side: WindSide | null | undefined): ParticleDrive {
  if (!side || !side.active || !side.bias) return { intensity: 0, direction: 'none' }
  return { intensity: clamp01(side.conviction?.score ?? 0), direction: side.bias }
}
