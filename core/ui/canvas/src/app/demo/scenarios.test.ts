// core/ui/canvas/src/app/demo/scenarios.test.ts
import { afterEach, describe, expect, test } from 'vitest'

import { __clearRegistryForTest, registerScenario, resolveDemoScenario } from './scenarios'

function setSearch(search: string) {
  // happy-dom only reflects location.search when href is assigned.
  window.location.href = `http://localhost/${search}`
}

afterEach(() => {
  __clearRegistryForTest()
  setSearch('')
})

describe('resolveDemoScenario', () => {
  test('no ?demo param → null', () => {
    setSearch('')
    expect(resolveDemoScenario('brief-composer')).toBeNull()
  })

  test('unknown id → null', () => {
    setSearch('?demo=does-not-exist')
    expect(resolveDemoScenario('brief-composer')).toBeNull()
  })

  test('explicit id resolves to the matching scenario', () => {
    registerScenario({ id: 'sample', surface: 'brief-composer', defaultFor: 'brief-composer', steps: [] })
    setSearch('?demo=sample')
    expect(resolveDemoScenario('brief-composer')?.id).toBe('sample')
  })

  test('?demo=1 resolves the surface default', () => {
    registerScenario({ id: 'sample', surface: 'brief-composer', defaultFor: 'brief-composer', steps: [] })
    setSearch('?demo=1')
    expect(resolveDemoScenario('brief-composer')?.id).toBe('sample')
  })

  test('a scenario for another surface is not returned', () => {
    registerScenario({ id: 'sample', surface: 'brief-composer', defaultFor: 'brief-composer', steps: [] })
    setSearch('?demo=sample')
    expect(resolveDemoScenario('room')).toBeNull()
  })
})
