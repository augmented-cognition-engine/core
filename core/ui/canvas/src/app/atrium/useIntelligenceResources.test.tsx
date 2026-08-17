import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { IntelligenceResourcePage } from '@/api/intelligenceResourcesApi'

import { useIntelligenceResources } from './useIntelligenceResources'

const api = vi.hoisted(() => ({
  query: vi.fn(),
}))

vi.mock('@/api/intelligenceResourcesApi', () => ({
  queryIntelligenceResources: api.query,
}))

function page(id: string, evaluatedAt: string): IntelligenceResourcePage {
  return {
    contract: 'ace.intelligence.resource-plane-page/v1alpha1',
    query_id: `resource_query:${id}`,
    query_digest: `sha256:${id.padEnd(64, 'a').slice(0, 64)}`,
    product_id: 'product:world-intelligence',
    actor_ref: 'principal:test',
    as_of: evaluatedAt,
    available_at: evaluatedAt,
    evaluated_at: evaluatedAt,
    state: 'complete',
    items: [],
    next_cursor: null,
    degraded_reason_refs: [],
    page_id: `resource_page:${id}`,
    page_digest: `sha256:${id.padEnd(64, 'b').slice(0, 64)}`,
  }
}

beforeEach(() => {
  api.query.mockReset()
})

describe('useIntelligenceResources recovery', () => {
  it('distinguishes an unavailable first load and recovers on retry', async () => {
    const recovered = page('recovered', '2026-08-14T18:05:00.000Z')
    api.query.mockRejectedValueOnce(new Error('Resource plane unavailable.'))
    const { result } = renderHook(() => useIntelligenceResources())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.page).toBeNull()
    expect(result.current.error?.message).toBe('Resource plane unavailable.')

    api.query.mockResolvedValueOnce(recovered)
    act(() => result.current.refresh())

    await waitFor(() => expect(result.current.page).toBe(recovered))
    expect(result.current.error).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('retains the last loaded page across a failed refresh and replaces it after recovery', async () => {
    const first = page('first', '2026-08-14T18:00:00.000Z')
    const recovered = page('second', '2026-08-14T18:10:00.000Z')
    api.query.mockResolvedValueOnce(first)
    const { result } = renderHook(() => useIntelligenceResources())

    await waitFor(() => expect(result.current.page).toBe(first))

    api.query.mockRejectedValueOnce(new Error('Refresh unavailable.'))
    act(() => result.current.refresh())
    await waitFor(() => expect(result.current.error?.message).toBe('Refresh unavailable.'))
    expect(result.current.page).toBe(first)

    api.query.mockResolvedValueOnce(recovered)
    act(() => result.current.refresh())
    await waitFor(() => expect(result.current.page).toBe(recovered))
    expect(result.current.error).toBeNull()
  })
})
