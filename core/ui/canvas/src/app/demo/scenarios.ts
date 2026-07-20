// core/ui/canvas/src/app/demo/scenarios.ts
//
// Demo scenario registry + URL resolution. A scenario is an ordered list
// of timed beats whose payload type matches the target surface's own
// event/action type. Content modules call registerScenario() at import
// time (see scenarios/room-default.ts; extension surfaces register
// theirs the same way).
import type { DemoStep } from './useScriptedTimeline'

export type DemoSurface = 'brief-composer' | 'room'

export interface DemoScenario<P = unknown> {
  id: string
  surface: DemoSurface
  /** Optional topic/title shown by the surface (the room uses this to
   *  activate its session hook). */
  topic?: string
  /** When set, `?demo=1` on this surface resolves to this scenario. */
  defaultFor?: DemoSurface
  steps: DemoStep<P>[]
}

const REGISTRY = new Map<string, DemoScenario>()

export function registerScenario<P>(scenario: DemoScenario<P>): void {
  REGISTRY.set(scenario.id, scenario as DemoScenario)
}

/** Test-only — empties the registry between cases. */
export function __clearRegistryForTest(): void {
  REGISTRY.clear()
}

function readDemoParam(): string | null {
  const params = new URLSearchParams(window.location.search)
  const v = params.get('demo')
  return v === null || v.length === 0 ? null : v
}

export function resolveDemoScenario<P = unknown>(surface: DemoSurface): DemoScenario<P> | null {
  const param = readDemoParam()
  if (param === null) return null

  if (param === '1') {
    for (const s of REGISTRY.values()) {
      if (s.defaultFor === surface) return s as DemoScenario<P>
    }
    return null
  }

  const found = REGISTRY.get(param)
  if (found === undefined || found.surface !== surface) return null
  return found as DemoScenario<P>
}
