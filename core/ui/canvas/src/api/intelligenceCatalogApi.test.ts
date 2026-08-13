import { beforeEach, describe, expect, test, vi } from 'vitest'

import { getToken } from './auth'
import { queryInstalledIntelligenceCatalog } from './intelligenceCatalogApi'

vi.mock('./auth', () => ({ clearToken: vi.fn(), getToken: vi.fn() }))

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
})
