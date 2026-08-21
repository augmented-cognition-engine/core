import { beforeEach, describe, expect, test, vi } from 'vitest'

import { clearToken, getToken } from './auth'
import {
  approveConnectBuilderSourceScope,
  approveBuilderConceptModel,
  approveBuilderIntelligenceModel,
  authorizeLocalSourceConnect,
  prepareBuilderFirstBrief,
  previewLocalSourceConnect,
  proposeBuilderConceptModel,
  proposeBuilderIntelligenceModel,
  proposeBuilderSourceScope,
  PersonalJourneyApiError,
} from './personalJourneyApi'

vi.mock('./auth', () => ({ clearToken: vi.fn(), getToken: vi.fn() }))

const preview = {
  contract: 'ace.application.local-source-connect-preview/v1alpha1',
  preview_id: 'local_source_connect_preview:abc',
  acquisition_mode: 'local',
  read_only: true,
  network_capture_performed: false,
  write_access_requested: false,
  mapping_scopes: [],
}

function ok(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

beforeEach(() => {
  vi.mocked(getToken).mockResolvedValue('token')
  vi.mocked(clearToken).mockClear()
  vi.stubGlobal('fetch', vi.fn())
})

describe('the Connect surface shows exact scope before any read', () => {
  test('preview posts the owner-named scope and returns the read-only disclosure', async () => {
    vi.mocked(fetch).mockResolvedValue(ok(preview))

    const result = await previewLocalSourceConnect({
      profile_id: 'intelligence_onboarding_profile:personal',
      profile_digest: `sha256:${'a'.repeat(64)}`,
      source_group_id: 'personal_local_sources',
      authorized_root: '/Users/owner/notes',
      mapping_scopes: [{ mapping_id: 'local_markdown_note', include: ['notes/*.md'] }],
      exclude: [],
    })

    expect(result.read_only).toBe(true)
    const [url, init] = vi.mocked(fetch).mock.calls[0]
    expect(url).toContain('/v1/intelligence/builds/connect/preview')
    expect(JSON.parse(String((init as RequestInit).body)).authorized_root).toBe('/Users/owner/notes')
  })

  test('authorize refuses to send anything but an explicit consent', async () => {
    vi.mocked(fetch).mockResolvedValue(ok({ captures: [] }))

    await authorizeLocalSourceConnect({ preview, authorized: true, authorized_at: '2026-08-21T12:00:00Z' })

    const body = JSON.parse(String((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body))
    expect(body.authorized).toBe(true)
    expect(body.preview.preview_id).toBe(preview.preview_id)
  })
})

describe('the Builder progression surfaces', () => {
  const routes: Array<[string, () => Promise<unknown>]> = [
    ['/builder/source/propose', () =>
      proposeBuilderSourceScope({ connect_request: {}, connect_result: {}, current: {}, occurred_at: 'now' })],
    ['/builder/source/approve-connect', () =>
      approveConnectBuilderSourceScope({ connect_request: {}, connect_result: {}, approval: {} })],
    ['/builder/concept/propose', () =>
      proposeBuilderConceptModel({ current: {}, source_profile: {}, user_intent: 'x', proposed_at: 'now' })],
    ['/builder/concept/approve', () =>
      approveBuilderConceptModel({ decision: 'approve', current: {}, proposal: {}, approved_at: 'now' })],
    ['/builder/intelligence/propose', () =>
      proposeBuilderIntelligenceModel({ current: {}, connect_request: {}, connect_result: {}, proposed_at: 'now' })],
    ['/builder/intelligence/approve', () =>
      approveBuilderIntelligenceModel({ decision: 'approve', current: {}, proposal: {}, approved_at: 'now' })],
    ['/builder/first-brief/prepare', () =>
      prepareBuilderFirstBrief({ current: {}, observations: {}, generated_at: 'now' })],
  ]

  test.each(routes)('%s posts to its exact route', async (path, call) => {
    vi.mocked(fetch).mockResolvedValue(ok({ contract: 'ok' }))

    await call()

    expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain(`/v1/intelligence/builds${path}`)
  })

  test('a stale revision surfaces the server’s own exact reason, not a generic failure', async () => {
    vi.mocked(fetch).mockResolvedValue(ok({ detail: 'Builder session revision is stale' }, 409))

    await expect(
      proposeBuilderConceptModel({ current: {}, source_profile: {}, user_intent: 'x', proposed_at: 'now' }),
    ).rejects.toMatchObject({ status: 409, message: 'Builder session revision is stale' })
  })

  test('an expired token is refreshed once and the call retried', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(ok({}, 401))
      .mockResolvedValueOnce(ok({ contract: 'ok' }))

    await prepareBuilderFirstBrief({ current: {}, observations: {}, generated_at: 'now' })

    expect(clearToken).toHaveBeenCalledTimes(1)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2)
  })

  test('a non-JSON failure still raises a bounded typed error', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => {
        throw new Error('not json')
      },
    } as unknown as Response)

    const error = await proposeBuilderSourceScope({
      connect_request: {},
      connect_result: {},
      current: {},
      occurred_at: 'now',
    }).catch((caught) => caught)

    expect(error).toBeInstanceOf(PersonalJourneyApiError)
    expect((error as PersonalJourneyApiError).status).toBe(503)
  })
})
