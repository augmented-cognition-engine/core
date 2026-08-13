import { useEffect, useState } from 'react'

import {
  queryInstalledIntelligenceCatalog,
  type InstalledIntelligenceProfile,
} from '@/api/intelligenceCatalogApi'

export function useInstalledIntelligenceCatalog(): readonly InstalledIntelligenceProfile[] {
  const [profiles, setProfiles] = useState<readonly InstalledIntelligenceProfile[]>([])

  useEffect(() => {
    let cancelled = false
    queryInstalledIntelligenceCatalog()
      .then((catalog) => {
        if (!cancelled) setProfiles(catalog.profiles)
      })
      .catch(() => {
        // Installed profiles enhance first use. Current admitted product
        // profiles and Core's Custom starting point remain usable if the
        // local catalog cannot be read.
      })
    return () => {
      cancelled = true
    }
  }, [])

  return profiles
}
