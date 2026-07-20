// core/ui/canvas/src/app/useAceCoreState.ts
//
// The single hook every chrome component reads from. Components don't
// know whether the state came from a fixture or a live subscription —
// they just render against the contract in `state.ts`.
//
// Today: returns the multiplayer fixture so first render is populated
// (the partner is already mid-thought, per the partner-never-asks
// memory).
//
// Later: this hook becomes a real subscription — useWebSocket /
// useContext over a session-scoped store. Components don't change.
import { useState } from 'react'

import { multiplayerFixture } from './fixtures/multiplayer'
import type { AceCoreState } from './state'

export function useAceCoreState(): AceCoreState {
  // Fixture for now. Wired here as state so the next iteration can
  // mutate it from event handlers without changing component contracts.
  const [state] = useState<AceCoreState>(multiplayerFixture)
  return state
}
