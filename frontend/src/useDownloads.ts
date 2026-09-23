import { useEffect, useState } from 'react'
import { api, ApiError, type DownloadStatus } from './api'

const POLL_MS = 2000

function handle(err: unknown, setError: (m: string) => void) {
  if (err instanceof ApiError && err.status === 401) window.location.assign('/login')
  else setError(err instanceof Error ? err.message : String(err))
}

/** Estado de descarga de una tarea; consulta cada 2 s mientras hay un lote en curso. */
export function useDownloads(courseId: string, cwId: string) {
  const [status, setStatus] = useState<DownloadStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  // Carga inicial y sondeo mientras running = true.
  useEffect(() => {
    let alive = true
    const delay = status === null ? 0 : status.running ? POLL_MS : null
    if (delay === null) return
    const t = window.setTimeout(() => {
      api
        .downloadStatus(courseId, cwId)
        .then((s) => alive && setStatus(s))
        .catch((err) => alive && handle(err, setError))
    }, delay)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [status, courseId, cwId])

  const start = async () => {
    setStarting(true)
    setError(null)
    try {
      setStatus(await api.startDownload(courseId, cwId))
    } catch (err) {
      handle(err, setError)
    } finally {
      setStarting(false)
    }
  }

  return { status, error, starting, start }
}
