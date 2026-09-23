import { cropUrl, type DownloadStatus, type MarkStatus, type SubmissionDownload } from './api'

const MARK_LABEL: Record<MarkStatus, string> = {
  con_marca: 'Con marca',
  dudosa: '¿Es tu marca?',
  sin_marca: 'Sin marca',
  error: 'Revisar a mano',
  desactivado: 'Módulo desactivado',
  sin_config: 'Configura tu marca',
  no_revisable: 'Sin imágenes',
}

/** Recortes de la marca, para ponerlos junto al nombre del alumno. */
export function MarkCrops({ d }: { d: SubmissionDownload | undefined }) {
  if (!d || d.detections.length === 0 || d.mark_status === 'desactivado') return null
  return (
    <span className="mark-crops">
      {d.detections.map((det) => (
        <a key={det.id} href={cropUrl(det.id)} target="_blank" rel="noreferrer" title={`${det.mark_name}: ${det.reason}`}>
          <img src={cropUrl(det.id)} alt={`Recorte de ${det.mark_name}`} loading="lazy" />
        </a>
      ))}
    </span>
  )
}

export function MarkCell({
  d,
  onDecide,
  busy,
}: {
  d: SubmissionDownload | undefined
  onDecide: (confirmed: boolean | null) => void
  busy: boolean
}) {
  if (!d || d.mark_status === null) return <span className="muted">—</span>
  const status = d.mark_status
  const decided = d.mark_confirmed !== null
  const canDecide = d.detections.length > 0 && !decided && (status === 'dudosa' || status === 'error')
  const informative = d.detections.filter((x) => x.meaning === 'informativa')
  return (
    <div className={`mark mark-${status}`}>
      <span className="mark-label">
        {MARK_LABEL[status]}
        {d.suggested_score !== null && <strong> · {d.suggested_score}</strong>}
      </span>
      {decided && (
        <span className="muted small">
          {' '}
          (lo decidiste tú ·{' '}
          <button className="link" disabled={busy} onClick={() => onDecide(null)}>
            deshacer
          </button>
          )
        </span>
      )}
      {!decided && d.mark_detail && <div className="mark-detail">{d.mark_detail}</div>}
      {informative.length > 0 && (
        <div className="mark-detail">Marca informativa: {informative.map((x) => x.mark_name).join(', ')}</div>
      )}
      {canDecide && (
        <div className="mark-actions">
          <button disabled={busy} onClick={() => onDecide(true)}>
            ✓ Sí, es mi marca
          </button>
          <button disabled={busy} onClick={() => onDecide(false)}>
            ✗ No
          </button>
        </div>
      )}
      {status === 'con_marca' && !decided && (
        <button className="link small" disabled={busy} onClick={() => onDecide(false)}>
          No es mi marca
        </button>
      )}
    </div>
  )
}

export function MarksToolbar({
  status,
  busy,
  onToggle,
  onDetect,
  onConfirmAll,
}: {
  status: DownloadStatus | null
  busy: boolean
  onToggle: (enabled: boolean) => void
  onDetect: () => void
  onConfirmAll: () => void
}) {
  if (!status) return null
  const subs = Object.values(status.submissions)
  const ready = (status.counts.lista ?? 0) > 0
  const count = (s: MarkStatus) => subs.filter((x) => x.mark_status === s).length
  const pending = subs.filter(
    (x) => x.mark_confirmed === null && (x.mark_status === 'dudosa' || x.mark_status === 'error') && x.detections.length > 0,
  ).length
  const reviewed = subs.some((x) => x.mark_status !== null)
  return (
    <div className="download-bar">
      <label className="toggle">
        <input
          type="checkbox"
          checked={status.mark_module_enabled}
          disabled={busy}
          onChange={(e) => onToggle(e.target.checked)}
        />{' '}
        Buscar mi marca en esta tarea
      </label>
      <button onClick={onDetect} disabled={busy || status.marks_running || !ready}>
        {status.marks_running ? 'Revisando marcas…' : reviewed ? 'Volver a revisar marcas' : 'Revisar marcas'}
      </button>
      {reviewed && status.mark_module_enabled && (
        <span className="muted">
          {count('con_marca')} con marca · {pending} por confirmar · {count('sin_marca')} sin marca
        </span>
      )}
      {pending > 0 && !status.marks_running && (
        <button onClick={onConfirmAll} disabled={busy} title="Solo después de ver los recortes">
          Confirmar las {pending} por confirmar
        </button>
      )}
    </div>
  )
}
