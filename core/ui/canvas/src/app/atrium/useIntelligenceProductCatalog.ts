import { useEffect, useState } from 'react'

import {
  queryInstalledDomainPackCatalog,
  queryIntelligenceConsumerCatalog,
  type InstalledDomainPackPreview,
  type IntelligenceConsumerCatalog,
} from '@/api/intelligenceCatalogApi'

interface IntelligenceProductCatalogState {
  readonly packs: readonly InstalledDomainPackPreview[]
  readonly consumers: IntelligenceConsumerCatalog | null
}

const EMPTY_STATE: IntelligenceProductCatalogState = { packs: [], consumers: null }

export function useIntelligenceProductCatalog(): IntelligenceProductCatalogState {
  const [catalog, setCatalog] = useState<IntelligenceProductCatalogState>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false
    void Promise.allSettled([
      queryInstalledDomainPackCatalog(),
      queryIntelligenceConsumerCatalog(),
    ]).then(([packsResult, consumersResult]) => {
      if (cancelled) return
      setCatalog({
        packs: packsResult.status === 'fulfilled' ? packsResult.value.packs : [],
        consumers: consumersResult.status === 'fulfilled' ? consumersResult.value : null,
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  return catalog
}
