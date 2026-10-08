import { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet } from '../services/api'

// Fetch `path` with `params`; re-fetches when params change and aborts stale requests.
export function useApi(path, params = {}, { enabled = true } = {}) {
  const key = JSON.stringify(params)
  const [state, setState] = useState({ data: null, error: null, loading: enabled })
  const [nonce, setNonce] = useState(0)
  const ctrl = useRef(null)

  useEffect(() => {
    if (!enabled || !path) return undefined
    ctrl.current?.abort()
    const c = new AbortController()
    ctrl.current = c
    setState((s) => ({ ...s, loading: true, error: null }))
    apiGet(path, JSON.parse(key), { signal: c.signal })
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => {
        if (error.name !== 'AbortError') setState({ data: null, error, loading: false })
      })
    return () => c.abort()
  }, [path, key, enabled, nonce])

  const retry = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, retry }
}
