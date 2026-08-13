import { useCallback, useEffect, useState } from 'react'

import {
  queryIntelligenceResources,
  type IntelligenceResourcePage,
} from '@/api/intelligenceResourcesApi'

interface IntelligenceResourcesState {
  readonly page: IntelligenceResourcePage | null
  readonly loading: boolean
  readonly error: Error | null
  readonly refresh: () => void
  readonly adoptPage: (page: IntelligenceResourcePage) => void
}

export function useIntelligenceResources(): IntelligenceResourcesState {
  const [page, setPage] = useState<IntelligenceResourcePage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [revision, setRevision] = useState(0)

  const refresh = useCallback(() => setRevision((value) => value + 1), [])
  const adoptPage = useCallback((nextPage: IntelligenceResourcePage) => {
    setPage(nextPage)
    setError(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    queryIntelligenceResources()
      .then((nextPage) => {
        if (!cancelled) setPage(nextPage)
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason : new Error('Intelligence is unavailable.'))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [revision])

  return { page, loading, error, refresh, adoptPage }
}
