import { beforeEach, describe, expect, test, vi } from 'vitest'

import { getToken } from './auth'
import { startIntelligenceBuild } from './intelligenceBuildsApi'

vi.mock('./auth', () => ({ clearToken: vi.fn(), getToken: vi.fn() }))

const result = {
  contract: 'ace.http.intelligence-build-result/v1alpha1',
  build_id: 'intelligence_build:test',
  request_digest: `sha256:${'a'.repeat(64)}`,
  product_id: 'product:test',
  actor_ref: 'principal:test',
  accepted_at: '2026-08-13T00:00:00Z',
  authority_use: {},
  resource_page: { items: [], state: 'complete' },
}

describe('startIntelligenceBuild', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(result), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))
  })

  test('submits the reviewed Atrium plan to the governed build boundary', async () => {
    const response = await startIntelligenceBuild({
      profile_id: 'profile:world-ai',
      subject: 'Keep me ahead of meaningful AI changes.',
      outcome_id: 'outcome:decision-readiness',
      source_group_ids: ['sources:official', 'sources:independent'],
      cadence_id: 'cadence:daily',
    })

    expect(response.build_id).toBe('intelligence_build:test')
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/start')
    expect(options?.method).toBe('POST')
    expect(options?.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer personal-token' }))
    const body = JSON.parse(String(options?.body)) as Record<string, unknown>
    expect(body).toEqual(expect.objectContaining({
      profile_id: 'profile:world-ai',
      subject: 'Keep me ahead of meaningful AI changes.',
      outcome_id: 'outcome:decision-readiness',
      source_group_ids: ['sources:official', 'sources:independent'],
      cadence_id: 'cadence:daily',
      resource_authority_grant_ref: 'authority_grant:atrium-observe-read',
      approved_effects: [
        'connect_sources',
        'map_concepts',
        'activate_watch',
        'create_first_brief',
      ],
    }))
    expect(body.client_request_id).toMatch(/^atrium-request:/)
    expect(body.requested_at).toEqual(expect.any(String))
  })

  test('fails visibly when the host has no Intelligence build executor', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'no Intelligence build executor is registered' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(startIntelligenceBuild({
      profile_id: 'profile:custom',
      subject: 'Track the decisions and changes that matter to me.',
      outcome_id: 'outcome:custom',
      source_group_ids: [],
      cadence_id: 'cadence:weekly',
    })).rejects.toMatchObject({
      status: 503,
      message: 'no Intelligence build executor is registered',
    })
  })
})
