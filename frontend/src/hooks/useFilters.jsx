import { createContext, useCallback, useContext, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

// Global dashboard filters live in the URL, so every view is shareable and survives reloads.
export const FILTER_KEYS = ['start', 'end', 'language', 'country', 'sentiment', 'topic', 'hashtag', 'q',
  'min_engagement', 'exclude_retweets', 'user']

const FiltersContext = createContext(null)

export function FiltersProvider({ children }) {
  const [params, setParams] = useSearchParams()

  const filters = useMemo(() => {
    const f = {}
    for (const k of FILTER_KEYS) {
      const v = params.get(k)
      if (v !== null && v !== '') f[k] = v
    }
    return f
  }, [params])

  const setFilter = useCallback((key, value) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (value === undefined || value === null || value === '' || value === false) next.delete(key)
      else next.set(key, String(value))
      return next
    }, { replace: true })
  }, [setParams])

  const setMany = useCallback((obj) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      for (const [k, v] of Object.entries(obj)) {
        if (v === undefined || v === null || v === '') next.delete(k)
        else next.set(k, String(v))
      }
      return next
    }, { replace: true })
  }, [setParams])

  const clear = useCallback(() => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      FILTER_KEYS.forEach((k) => next.delete(k))
      return next
    }, { replace: true })
  }, [setParams])

  const value = useMemo(() => ({ filters, setFilter, setMany, clear, active: Object.keys(filters).length }),
    [filters, setFilter, setMany, clear])
  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>
}

export function useFilters() {
  const ctx = useContext(FiltersContext)
  if (!ctx) throw new Error('useFilters must be used inside FiltersProvider')
  return ctx
}
