import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { DownloadStatus, ExerciseResult, KeyState, SubmissionDownload } from './api'

const ESTADO: Record<string, string> = {
  correcto: 'Correcto',
  error_menor: 'Error menor',
  incorrecto: 'Incorrecto',
  incompleto: 'Incompleto',
  no_contestado: 'No contestado',
  ilegible: 'Ilegible',
  por_revisar: 'Por revisar',
  no_evaluado: 'No evaluado',
}

const KEY_LABEL: Record<KeyState, string> = {
  sin_clave: 'Sin clave de respuestas',
  generando: 'Generando la clave…',
  error: 'No se pudo generar la clave',
  sin_validar: 'Clave sin validar',
  validada: 'Clave validada ✓',
}

export function KeyBanner({ status, courseId, cwId }: { status: DownloadStatus | null; courseId: string; cwId: string }) {
  const state = status?.key_state ?? 'sin_clave'
  return (
    <div className={`download-bar key-banner key-${state}`}>
      <strong>{KEY_LABEL[state]}</strong>
      <Link to={`/cursos/${courseId}/tareas/${cwId}/clave`}>
        {state === 'validada' ? 'Ver o editar la clave' : 'Preparar la clave de respuestas →'}
      </Link>
      {state !== 'validada' && (
        <span className="muted small">Solo se califica con una clave validada (las firmas no la necesitan).</span>
      )}
    </div>
  )
}

export function GradeCell({
  d,
  keyState,
  busy,
  onGrade,
  onOpen,
}: {
  d: SubmissionDownload | undefined
  keyState: KeyState
  busy: boolean
  onGrade: () => void
  onOpen: () => void
}) {
  if (!d || d.status !== 'lista') return <span className="muted">—</span>
  const g = d.grade
  const signed = d.mark_status === 'con_marca'
  const canGrade = signed || keyState === 'validada'
  if (g?.status === 'calificando') return <span className="muted">Calificando…</span>
  return (
    <div className="grade">
      {d.suggested_score !== null && (
        <button className="link grade-score" onClick={onOpen} title="Ver detalle">
          {formatScore(d.suggested_score)}
        </button>
      )}
      {g && g.status === 'revisada' && !g.stale && <span className="grade-ok"> Revisada</span>}
      {g && g.status === 'revisar_a_mano' && !g.stale && (
        <span className="grade-warn" title={g.review_reasons.join('\n')}>
          {' '}
          Revisar a mano
        </span>
      )}
      {signed && <span className="grade-ok"> Con marca</span>}
      {g?.status === 'error' && <div className="dl-error">{g.error}</div>}
      {g?.stale && <div className="muted small">Se calificó con otra versión de la clave</div>}
      {!signed && (
        <div>
          <button className="small-btn" disabled={busy || !canGrade} onClick={onGrade}>
            {g && g.status !== 'error' ? 'Volver a calificar' : 'Calificar'}
          </button>
        </div>
      )}
    </div>
  )
}

function formatScore(n: number) {
  return Number.isInteger(n) ? `${n}` : n.toFixed(1)
}

function ExerciseRow({ e }: { e: ExerciseResult }) {
  return (
    <tr className={`ex ex-${e.estado}`}>
      <td>{e.numero}</td>
      <td>
        <span className={`badge ex-badge-${e.estado}`}>{ESTADO[e.estado] ?? e.estado}</span>
        {e.motivo_revision && <div className="grade-warn small">{e.motivo_revision}</div>}
      </td>
      <td>
        {formatScore(e.puntos)} / {formatScore(e.valor)}
      </td>
      <td>
        {e.transcripcion_resultado && <div>Escribió: «{e.transcripcion_resultado}»</div>}
        {e.descripcion_error && <div className="muted small">{e.descripcion_error}</div>}
      </td>
    </tr>
  )
}

export function GradeDetail({ d }: { d: SubmissionDownload }) {
  const g = d.grade
  const [copied, setCopied] = useState(false)
  if (!g || g.status === 'calificando') return null
  const copy = async () => {
    await navigator.clipboard.writeText(g.comment ?? '')
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="grade-detail">
      {g.review_reasons.length > 0 && (
        <div className="warn-box small">
          <strong>Revisa a mano:</strong>
          <ul>
            {g.review_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {g.exercises.length > 0 && (
        <table className="ex-table">
          <thead>
            <tr>
              <th>Ej.</th>
              <th>Estado</th>
              <th>Puntos</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {g.exercises.map((e) => (
              <ExerciseRow key={e.numero} e={e} />
            ))}
          </tbody>
        </table>
      )}
      {g.comment && (
        <div className="comment-box">
          <div className="muted small">Comentario sugerido para el alumno</div>
          <p>{g.comment}</p>
          <button className="small-btn" onClick={() => void copy()}>
            {copied ? 'Copiado ✓' : 'Copiar comentario'}
          </button>
        </div>
      )}
    </div>
  )
}
