import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clearToken } from './auth'
import {
  type IntelligenceResourceReference,
  submitIntelligenceResourceFeedback,
} from './intelligenceResourcesApi'

const target: IntelligenceResourceReference = {
  contract: 'ace.intelligence.resource-plane-reference/v1alpha1',
  product_id: 'product:world-intelligence',
  resource_kind: 'shift',
  resource_id: 'shift:material-change',
  resource_digest: `sha256:${'a'.repeat(64)}`,
  resource_contract: 'ace.intelligence.shift/v1alpha1',
  revision: 2,
  as_of: '2026-08-14T18:00:00.000Z',
  available_at: '2026-08-15T18:00:00.000Z',
}

describe('Intelligence resource feedback API', () => {
  beforeEach(() => {
    clearToken()
    vi.restoreAllMocks()
    vi.stubGlobal('AbortSignal', {
      ...AbortSignal,
      timeout: vi.fn(() => undefined),
    })
  })

  it('serializes the exact target, intent, note, and evidence under bearer auth', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ token: 'token:test' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        contract: 'ace.intelligence.resource-feedback-admission/v1alpha1',
        feedback: {
          receipt_id: 'resource_feedback_receipt:recorded',
          disposition: 'recorded_proposal_only',
        },
      }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    await submitIntelligenceResourceFeedback({
      requestKey: 'feedback-request:client-1',
      target,
      correctionIntent: 'missing_source',
      note: 'The filing is absent.',
      evidence: [],
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/v1/intelligence/resources/feedback')
    const request = fetchMock.mock.calls[1]?.[1] as RequestInit
    expect(request.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer token:test' }))
    expect(JSON.parse(String(request.body))).toEqual({
      authority_grant_ref: 'authority_grant:atrium-resource-feedback',
      request_key: 'feedback-request:client-1',
      target,
      correction_intent: 'missing_source',
      note: 'The filing is absent.',
      evidence: [],
    })
  })
})
