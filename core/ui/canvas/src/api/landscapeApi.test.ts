import { beforeEach, describe, expect, test, vi } from 'vitest'

import { authGet } from './canvasApi'
import { landscapeApi, LIVING_PRODUCT_PROJECTION_VERSION } from './landscapeApi'

vi.mock('./canvasApi', () => ({ authGet: vi.fn() }))

describe('landscapeApi', () => {
  beforeEach(() => {
    vi.mocked(authGet).mockReset()
  })

  test('uses the authenticated GET seam and pins the supported projection version', async () => {
    vi.mocked(authGet).mockResolvedValue({})
    await landscapeApi.get()
    expect(authGet).toHaveBeenCalledWith(
      `/product/landscape?projection_version=${encodeURIComponent(LIVING_PRODUCT_PROJECTION_VERSION)}`,
    )
  })

  test('encodes an explicit projection request without adding a write request', async () => {
    vi.mocked(authGet).mockResolvedValue({})
    await landscapeApi.get({ projectionVersion: 'ace.living-product-projection.g1.v2 candidate' })
    const path = vi.mocked(authGet).mock.calls[0]?.[0]
    expect(path).toBe('/product/landscape?projection_version=ace.living-product-projection.g1.v2+candidate')
    expect(path).not.toContain('product=')
  })
})
