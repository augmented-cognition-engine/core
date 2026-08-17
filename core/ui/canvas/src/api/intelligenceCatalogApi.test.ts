import { beforeEach, describe, expect, test, vi } from 'vitest'

import { clearToken, getToken } from './auth'
import {
  IntelligenceCatalogApiError,
  queryDomainPackActivationHistory,
  queryInstalledDomainPackCatalog,
  queryInstalledIntelligenceCatalog,
  queryIntelligenceConsumerCatalog,
} from './intelligenceCatalogApi'

vi.mock('./auth', () => ({ clearToken: vi.fn(), getToken: vi.fn() }))

function activationHistoryBody(activationKey: string) {
  return {
    contract: 'ace.http.domain-pack-activation-history/v1alpha1',
    authority_stage: 'historical_reference',
    live_authority: false,
    product_id: 'product:acme',
    activation_key: activationKey,
    activation_id: 'activation:acme-world',
    current: {
      revision: 2,
      revision_id: 'revision:2',
      revision_digest: 'sha256:aaaa',
      action: 'upgrade',
      state: 'active',
      pack: { pack_id: 'world', pack_version: '1.1.0', compiled_pack_id: 'pack_ir:aaaa', pack_digest: 'sha256:aaaa' },
      overlay: {
        contract: 'ace.intelligence.compiled-overlay/v1alpha1',
        overlay_id: 'overlay:world',
        version: '1',
        pack_id: 'world',
        pack_version: '1.1.0',
        pack_digest: 'sha256:aaaa',
        values: [{ slot_id: 'tone', value_json: '"formal"' }],
        compiled_overlay_id: 'overlay_ir:aaaa',
        overlay_digest: 'sha256:aaaa',
      },
      plan_id: 'plan:2',
      plan_digest: 'sha256:plan2',
      approval_receipt_ref: 'receipt:approval2',
      approval_receipt_digest: 'sha256:approval2',
      actor_ref: 'actor:owner',
      occurred_at: '2026-08-01T00:00:00Z',
      commit_receipt_id: 'receipt:commit2',
      commit_receipt_digest: 'sha256:commit2',
      committed_at: '2026-08-01T00:00:01Z',
    },
    history: [],
  }
}

describe('queryInstalledIntelligenceCatalog', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
  })

  test('reads installed profiles through the authenticated domain-neutral catalog', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      contract: 'ace.http.installed-intelligence-catalog/v1alpha1',
      profiles: [{ distribution: 'pack', distribution_version: '1.0.0', resource_path: 'domain_packs/x/onboarding_profile.json', profile: {} }],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    const result = await queryInstalledIntelligenceCatalog()

    expect(result.profiles).toHaveLength(1)
    expect(fetch).toHaveBeenCalledWith('/v1/intelligence/catalog/profiles', {
      headers: { Authorization: 'Bearer personal-token' },
    })
  })

  test('reads Pack previews and consumer boundaries from their authenticated catalogs', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        contract: 'ace.http.installed-domain-pack-catalog/v1alpha1',
        packs: [{ distribution: 'pack', distribution_version: '1.0.0', manifest: { metadata: { pack_id: 'world', version: '1.0.0' } } }],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        contract: 'ace.http.intelligence-consumer-catalog/v1alpha1',
        interfaces: [{ interface_id: 'intelligence_resource_http', availability: 'available' }],
        unresolved_dependencies: ['outbound delivery'],
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    const packs = await queryInstalledDomainPackCatalog()
    const consumers = await queryIntelligenceConsumerCatalog()

    expect(packs.packs[0]?.manifest.metadata.pack_id).toBe('world')
    expect(consumers.interfaces[0]?.availability).toBe('available')
    expect(fetch).toHaveBeenNthCalledWith(1, '/v1/intelligence/catalog/packs', {
      headers: { Authorization: 'Bearer personal-token' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/v1/intelligence/catalog/consumers', {
      headers: { Authorization: 'Bearer personal-token' },
    })
  })
})

describe('queryDomainPackActivationHistory', () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReset()
    vi.mocked(getToken).mockResolvedValue('personal-token')
    vi.mocked(clearToken).mockReset()
  })

  test('reads the exact activation by the exact supplied activation key, URL-encoded', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify(activationHistoryBody('world/ai team')),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )))

    const result = await queryDomainPackActivationHistory('world/ai team')

    expect(result.activation_key).toBe('world/ai team')
    expect(result.live_authority).toBe(false)
    expect(fetch).toHaveBeenCalledWith(
      '/v1/intelligence/catalog/packs/activations/world%2Fai%20team',
      { headers: { Authorization: 'Bearer personal-token' } },
    )
  })

  test('retries once with a fresh token after a 401, then succeeds', async () => {
    vi.mocked(getToken).mockResolvedValueOnce('stale-token').mockResolvedValueOnce('fresh-token')
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify(activationHistoryBody('world-ai')),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )))

    const result = await queryDomainPackActivationHistory('world-ai')

    expect(result.activation_key).toBe('world-ai')
    expect(clearToken).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenNthCalledWith(1, '/v1/intelligence/catalog/packs/activations/world-ai', {
      headers: { Authorization: 'Bearer stale-token' },
    })
    expect(fetch).toHaveBeenNthCalledWith(2, '/v1/intelligence/catalog/packs/activations/world-ai', {
      headers: { Authorization: 'Bearer fresh-token' },
    })
  })

  test('surfaces a 401 that survives the retry as a typed error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'verified token lacks exact product scope' }),
      { status: 401, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(queryDomainPackActivationHistory('world-ai')).rejects.toMatchObject({
      name: 'IntelligenceCatalogApiError',
      status: 401,
      message: 'verified token lacks exact product scope',
    })
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  test('surfaces a 403 denial as a typed error without retrying', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'Pack activation history requires administer_lifecycle authority' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(queryDomainPackActivationHistory('world-ai')).rejects.toMatchObject({
      name: 'IntelligenceCatalogApiError',
      status: 403,
    })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  test('surfaces a 404 for an unknown activation key', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'no activation exists for the exact activation key' }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(queryDomainPackActivationHistory('unknown-key')).rejects.toMatchObject({
      name: 'IntelligenceCatalogApiError',
      status: 404,
    })
  })

  test('surfaces a 503 when persisted activation history is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: 'exact Pack activation history is unavailable' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    )))

    await expect(queryDomainPackActivationHistory('world-ai')).rejects.toBeInstanceOf(IntelligenceCatalogApiError)
    await expect(queryDomainPackActivationHistory('world-ai')).rejects.toMatchObject({ status: 503 })
  })

  test('falls back to a bounded status-only message for a non-JSON failure body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not json', { status: 500 })))

    await expect(queryDomainPackActivationHistory('world-ai')).rejects.toMatchObject({
      status: 500,
      message: 'Pack activation history is unavailable (500).',
    })
  })
})
