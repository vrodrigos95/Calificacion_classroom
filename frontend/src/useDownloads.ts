import { useEffect, useState } from 'react'
import { api, ApiError, type DownloadStatus } from './api'

const POLL_MS = 2000

function handle(err: unknown, setError: (m: string) => void) {
  if (err instanceof ApiError && err.status === 401) window.location.assign('/login')
  else setError(err instanceof Error ? err.message : String(err))
}

/** Estado de descarga y marcas de una tarea; consulta cada 2 s mientras hay un lote en curso. */
export function useDownloads(courseId: string, cwId: string) {
  const [status, setStatus] = useState<DownloadStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0) // fuerza una recarga

  useEffect(() => {
    let alive = true
    const polling = status !== null && (status.running || status.marks_running)
    const delay = status === null || tick > 0 ? 0 : polling ? POLL_MS : null
    if (delay === null) return
    const t = window.setTimeout(() => {
      api
        .downloadStatus(courseId, cwId)
        .then((s) => {
          if (!alive) return
          setTick(0)
          setStatus(s)
        })
        .catch((err) => alive && handle(err, setError))
    }, delay)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [status, tick, courseId, cwId])

  const run = async (action: () => Promise<unknown>, reload = true) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      if (reload) setTick((n) => n + 1)
    } catch (err) {
      handle(err, setError)
    } finally {
      setBusy(false)
    }
  }

  return {
    status,
    error,
    busy,
    startDownload: () => run(async () => setStatus(await api.startDownload(courseId, cwId)), false),
    detectMarks: () => run(() => api.detectMarks(courseId, cwId)),
    setModule: (enabled: boolean) => run(() => api.setMarkModule(courseId, cwId, enabled)),
    decide: (sid: string, confirmed: boolean | null) =>
      run(() => api.markDecision(courseId, cwId, sid, confirmed)),
    confirmAll: () => run(() => api.confirmAllMarks(courseId, cwId)),
  }
}
