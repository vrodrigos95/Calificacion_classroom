import { useState } from 'react'
import type { DownloadStatus, PanelStatus, ReviewPatch, SubmissionDownload } from './api'

const PANEL_LABEL: Record<PanelStatus, string> = {
  revisar_a_mano: 'Revisar a mano',
  con_marca: 'Con marca',
  revisada: 'Revisada',
  error: 'Error',
  pendiente: 'Pendiente',
  procesando: 'Procesando…',
  sin_entrega: 'Sin entrega',
}

const PHASE: Record<string, string> = {
  descargando: 'Descargando entregas…',
  marcas: 'Buscando tu marca…',
  calificando: 'Calificando…',
}

export function ProcessBar({
  status,
  busy,
  onProcess,
}: {
  status: DownloadStatus | null
  busy: boolean
  onProcess: () => void
}) {
  const running = !!status?.batch_running
  const processed = status && Object.keys(status.submissions).length > 0
  return (
    <div className="process-bar">
      <button className="primary big" disabled={busy || running} onClick={onProcess}>
        {running ? PHASE[status?.batch_phase ?? ''] ?? 'Procesando…' : processed ? 'Procesar de nuevo' : 'Procesar tarea'}
      </button>
      <span className="muted small">
        Descarga las entregas, busca tu marca y califica las demás con la clave validada. Lo que ya está listo no se
        repite.
      </span>
      {!running && status?.batch_phase === 'error' && <div className="alert">{status.batch_note}</div>}
      {!running && status?.batch_phase === 'listo' && status.batch_note && (
        <div className="warn-box small">{status.batch_note}</div>
      )}
    </div>
  )
}

export type Filter = PanelStatus | 'todas'

export function FilterChips({
  subs,
  filter,
  onFilter,
  hideCaptured,
  onHideCaptured,
}: {
  subs: SubmissionDownload[]
  filter: Filter
  onFilter: (f: Filter) => void
  hideCaptured: boolean
  onHideCaptured: (v: boolean) => void
}) {
  const count = (s: PanelStatus) => subs.filter((x) => x.panel_status === s).length
  const captured = subs.filter((x) => x.captured).length
  const order: PanelStatus[] = ['revisar_a_mano', 'error', 'con_marca', 'revisada', 'pendiente', 'sin_entrega']
  return (
    <div className="chips">
      <button className={`chip ${filter === 'todas' ? 'on' : ''}`} onClick={() => onFilter('todas')}>
        Todas ({subs.length})
      </button>
      {order.map((s) =>
        count(s) ? (
          <button key={s} className={`chip chip-${s} ${filter === s ? 'on' : ''}`} onClick={() => onFilter(s)}>
            {PANEL_LABEL[s]} ({count(s)})
          </button>
        ) : null,
      )}
      <label className="toggle small">
        <input type="checkbox" checked={hideCaptured} onChange={(e) => onHideCaptured(e.target.checked)} /> Ocultar
        capturadas ({captured})
      </label>
    </div>
  )
}

export function StatusBadge({ d }: { d: SubmissionDownload | undefined }) {
  if (!d) return <span className="muted">—</span>
  return (
    <div>
      <span className={`pbadge pbadge-${d.panel_status}`}>{PANEL_LABEL[d.panel_status]}</span>
      {d.panel_note && <div className="panel-note">{d.panel_note}</div>}
    </div>
  )
}

function copy(text: string, done: () => void) {
  void navigator.clipboard.writeText(text).then(done)
}

export function ScoreEditor({
  d,
  onSave,
}: {
  d: SubmissionDownload
  onSave: (patch: ReviewPatch) => void
}) {
  const [value, setValue] = useState(d.final_score === null ? '' : String(d.final_score))
  const [copied, setCopied] = useState(false)
  if (d.final_score === null && d.score_override === null) return <span className="muted">—</span>
  const commit = () => {
    const n = value.trim() === '' ? null : Number(value)
    if (n !== null && (Number.isNaN(n) || n < 0 || n > 100)) {
      setValue(d.final_score === null ? '' : String(d.final_score))
      return
    }
    if (n === d.final_score) return
    onSave({ score_override: n === d.suggested_score ? null : n })
  }
  return (
    <div className="score-editor">
      <input
        className="score-input"
        inputMode="decimal"
        value={value}
        aria-label="Calificación"
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
      />
      <span className="muted">/100</span>
      <button
        className="icon-btn"
        title="Copiar calificación"
        onClick={() => copy(value, () => { setCopied(true); window.setTimeout(() => setCopied(false), 1200) })}
      >
        {copied ? '✓' : '📋'}
      </button>
      {d.score_override !== null && d.suggested_score !== null && (
        <div className="muted small">
          sugerida {d.suggested_score}{' '}
          <button className="link small" onClick={() => onSave({ score_override: null })}>
            restaurar
          </button>
        </div>
      )}
    </div>
  )
}

export function CommentEditor({
  d,
  onSave,
}: {
  d: SubmissionDownload
  onSave: (patch: ReviewPatch) => void
}) {
  const [value, setValue] = useState(d.final_comment)
  const [copied, setCopied] = useState(false)
  const nothingYet = !d.grade && d.comment_override === null && d.panel_status !== 'con_marca'
  if (d.panel_status === 'sin_entrega' || nothingYet) return <span className="muted">—</span>
  const suggested = d.grade && !d.grade.stale ? d.grade.comment ?? '' : ''
  const commit = () => {
    if (value === d.final_comment) return
    onSave({ comment_override: value === suggested ? null : value })
  }
  return (
    <div className="comment-editor">
      <textarea
        rows={3}
        value={value}
        placeholder={d.panel_status === 'con_marca' ? '(sin comentario)' : ''}
        aria-label="Comentario privado"
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
      />
      <div className="comment-actions">
        <button
          className="small-btn"
          disabled={!value}
          onClick={() => copy(value, () => { setCopied(true); window.setTimeout(() => setCopied(false), 1200) })}
        >
          {copied ? 'Copiado ✓' : 'Copiar comentario'}
        </button>
        {d.comment_override !== null && (
          <button className="link small" onClick={() => { setValue(suggested); onSave({ comment_override: null }) }}>
            restaurar sugerido
          </button>
        )}
      </div>
    </div>
  )
}
