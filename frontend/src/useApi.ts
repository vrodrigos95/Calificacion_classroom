import { useEffect, useState } from 'react'
import { ApiError } from './api'

interface State<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
}

/** Carga datos de la API; si la sesión expiró (401) manda a /login. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })

  // deps las define quien llama (p. ej. [courseId]); load cambia en cada render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    let alive = true
    setState({ data: null, error: null, loading: true })
    load()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((err: unknown) => {
        if (!alive) return
        const error = err instanceof ApiError ? err : new ApiError(0, String(err))
        if (error.status === 401) {
          window.location.assign('/login')
          return
        }
        setState({ data: null, error, loading: false })
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
