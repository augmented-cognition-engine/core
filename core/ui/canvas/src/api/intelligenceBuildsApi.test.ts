import { beforeEach, describe, expect, test, vi } from 'vitest'

import { getToken } from './auth'
import {
  createIntelligenceBuildPlanPrepareInput,
  prepareIntelligenceBuild,
  startIntelligenceBuild,
} from './intelligenceBuildsApi'

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

describe('prepareIntelligenceBuild', () => {
  const selection = {
    profile_id: 'onboarding_profile:world-ai',
    profile_digest: `sha256:${'b'.repeat(64)}`,
    subject: 'Keep me ahead of material AI changes.',
    outcome_id: 'decision-readiness',
    source_group_ids: ['official-records'],
    cadence_id: 'daily',
  }

  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('posts the exact reusable prepare input and returns server review material', async () => {
    const input = createIntelligenceBuildPlanPrepareInput(selection)
    const plan = {
      contract: 'ace.application.intelligence-build-plan/v1alpha2',
      request: {
        ...input,
        contract: 'ace.application.intelligence-build-plan-request/v1alpha2',
        product_id: 'product:local',
        actor_ref: 'principal:local-owner',
        request_id: 'intelligence_build_plan_request:test',
        request_digest: `sha256:${'c'.repeat(64)}`,
      },
      recorded_source_selection_refs: [],
      review_projection: {
        contract: 'ace.application.intelligence-build-review-projection/v1alpha1',
        request_id: 'intelligence_build_plan_request:test',
        request_digest: `sha256:${'c'.repeat(64)}`,
        profile_id: selection.profile_id,
        profile_digest: selection.profile_digest,
        subject: selection.subject,
        outcome_id: selection.outcome_id,
        outcome_label: 'Decision readiness',
        sources: [],
        concepts: [],
        watches: [],
        cadence_id: selection.cadence_id,
        cadence_label: 'Daily',
        cadence_description: 'Once a day.',
        effects: [],
        projection_id: 'intelligence_build_review:test',
        projection_digest: `sha256:${'d'.repeat(64)}`,
      },
      plan_id: 'intelligence_build_plan:test',
      plan_digest: `sha256:${'e'.repeat(64)}`,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(plan), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })))

    await expect(prepareIntelligenceBuild(input)).resolves.toMatchObject({
      plan_id: 'intelligence_build_plan:test',
      review_projection: { projection_id: 'intelligence_build_review:test' },
    })
    const [path, options] = vi.mocked(fetch).mock.calls[0] ?? []
    expect(path).toBe('/v1/intelligence/builds/prepare')
    expect(JSON.parse(String(options?.body))).toEqual(input)
    expect(options?.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer personal-token' }))
  })

  test.each([404, 409, 503])('preserves the exact degraded status %s', async (status) => {
    const input = createIntelligenceBuildPlanPrepareInput(selection)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: `bounded failure ${status}` }),
      { status, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(prepareIntelligenceBuild(input)).rejects.toMatchObject({
      status,
      message: `bounded failure ${status}`,
    })
  })

  test('rejects a successful response that has no exact review projection', async () => {
    const input = createIntelligenceBuildPlanPrepareInput(selection)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      contract: 'ace.application.intelligence-build-plan/v1alpha2',
      review_projection: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    await expect(prepareIntelligenceBuild(input)).rejects.toMatchObject({ status: 409 })
  })
})
