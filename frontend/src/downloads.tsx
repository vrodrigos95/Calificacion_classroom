import { pageImageUrl, type DownloadState, type DownloadStatus, type SubmissionDownload } from './api'

export function DownloadBar({
  status,
  starting,
  error,
  onStart,
}: {
  status: DownloadStatus | null
  starting: boolean
  error: string | null
  onStart: () => void
}) {
  const c = status?.counts ?? {}
  const done = (c.lista ?? 0) + (c.error ?? 0)
  const toDo = done + (c.pendiente ?? 0) + (c.descargando ?? 0)
  const started = status && Object.keys(status.submissions).length > 0
  const busy = starting || status?.running
  return (
    <div className="download-bar">
      <button onClick={onStart} disabled={!!busy}>
        {busy ? 'Descargando…' : started ? 'Actualizar y reintentar errores' : 'Descargar entregas'}
      </button>
      {started && (
        <span className="muted">
          {busy && toDo > 0 ? `${done} de ${toDo} procesadas · ` : ''}
          {c.lista ?? 0} listas · {c.error ?? 0} con error
          {c.expirada ? ` · ${c.expirada} borradas por retención` : ''}
        </span>
      )}
      {error && <span className="alert-inline">{error}</span>}
    </div>
  )
}

const LABEL: Record<DownloadState, string> = {
  sin_entrega: '—',
  pendiente: 'En cola',
  descargando: 'Descargando…',
  lista: 'Lista',
  error: 'Error',
  expirada: 'Borrada (retención)',
}

export function DownloadCell({
  d,
  open,
  onToggle,
}: {
  d: SubmissionDownload | undefined
  open: boolean
  onToggle: () => void
}) {
  if (!d) return <span className="muted">—</span>
  if (d.status === 'sin_entrega') return <span className="muted">—</span>
  if (d.status === 'lista')
    return (
      <button className="link" onClick={onToggle} aria-expanded={open}>
        {d.pages.length} {d.pages.length === 1 ? 'página' : 'páginas'} {open ? '▲' : '▼'}
      </button>
    )
  return (
    <span className={`dl dl-${d.status}`} title={d.error ?? undefined}>
      {LABEL[d.status]}
      {d.error && <div className="dl-error">{d.error}</div>}
    </span>
  )
}

export function PageStrip({ d }: { d: SubmissionDownload }) {
  return (
    <div className="page-strip">
      {d.pages.map((p) => (
        <a key={p.id} href={pageImageUrl(p.id)} target="_blank" rel="noreferrer" title={`Página ${p.index + 1}`}>
          <img src={pageImageUrl(p.id)} alt={`Página ${p.index + 1}`} loading="lazy" />
          <span>Pág. {p.index + 1}</span>
        </a>
      ))}
    </div>
  )
}
