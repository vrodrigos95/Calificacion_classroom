import { Fragment, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, type Submission, type SubmissionStatus } from './api'
import { DownloadBar, DownloadCell, PageStrip } from './downloads'
import { GradeCell, GradeDetail, KeyBanner } from './grading'
import { CommentEditor, FilterChips, ProcessBar, ScoreEditor, StatusBadge, type Filter } from './panel'
import { MarkCell, MarkCrops, MarksToolbar } from './marks'
import { useDownloads } from './useDownloads'
import { useApi } from './useApi'

const LOGIN_ERRORS: Record<string, string> = {
  acceso_denegado: 'Cancelaste el inicio de sesión con Google.',
  estado_invalido: 'La solicitud de inicio de sesión expiró. Intenta de nuevo.',
  oauth: 'Google no pudo completar el inicio de sesión. Intenta de nuevo.',
  permisos:
    'Faltan permisos. En la pantalla de Google marca todas las casillas; la app solo lee, nunca escribe en Classroom.',
}

export function LoginPage() {
  const [params] = useSearchParams()
  const error = params.get('error')
  const faltan = params.get('faltan')
  return (
    <main className="login">
      <h1>Revisor de tareas</h1>
      <p>Califica tareas manuscritas de matemáticas entregadas en Google Classroom.</p>
      {error && (
        <div className="alert" role="alert">
          {LOGIN_ERRORS[error] ?? 'No se pudo iniciar sesión.'}
          {faltan && (
            <ul>
              {faltan.split(' ').map((s) => (
                <li key={s}>
                  <code>{s}</code>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <a className="button" href="/api/auth/login">
        Iniciar sesión con Google
      </a>
    </main>
  )
}

function Loading() {
  return <p className="muted">Cargando…</p>
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="alert" role="alert">
      {message}
    </div>
  )
}

export function CoursesPage() {
  const { data, error, loading } = useApi(api.courses, [])
  return (
    <section>
      <h2>Mis cursos</h2>
      {loading && <Loading />}
      {error && <ErrorBox message={error.message} />}
      {data && data.length === 0 && <p className="muted">No tienes cursos activos como docente.</p>}
      <ul className="cards">
        {data?.map((c) => (
          <li key={c.id}>
            <Link to={`/cursos/${c.id}`}>
              <strong>{c.name}</strong>
              {c.section && <span className="muted"> · {c.section}</span>}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function CourseWorkPage() {
  const { courseId = '' } = useParams()
  const { data, error, loading } = useApi(() => api.coursework(courseId), [courseId])
  return (
    <section>
      <p>
        <Link to="/">← Cursos</Link>
      </p>
      <h2>Tareas</h2>
      {loading && <Loading />}
      {error && <ErrorBox message={error.message} />}
      {data && data.length === 0 && <p className="muted">Este curso no tiene tareas.</p>}
      <ul className="cards">
        {data?.map((cw) => (
          <li key={cw.id}>
            <Link to={`/cursos/${courseId}/tareas/${cw.id}`}>
              <strong>{cw.title}</strong>
              <span className="muted">
                {cw.due_date ? ` · entrega ${cw.due_date}` : ' · sin fecha'}
                {cw.state === 'DRAFT' ? ' · borrador' : ''}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

const STATUS_LABEL: Record<SubmissionStatus, string> = {
  entregada: 'Entregada',
  entregada_sin_archivos: 'Entregada sin archivos',
  sin_entrega: 'Sin entrega',
}

function AttachmentList({ s }: { s: Submission }) {
  if (s.attachments.length === 0 && s.other_attachments === 0) return <span className="muted">—</span>
  return (
    <>
      {s.attachments.map((a) => (
        <div key={a.file_id}>
          <a href={a.alternate_link} target="_blank" rel="noreferrer">
            {a.title || 'archivo'}
          </a>
        </div>
      ))}
      {s.other_attachments > 0 && (
        <div className="muted">{s.other_attachments} adjunto(s) que no son archivo</div>
      )}
    </>
  )
}

export function SubmissionsPage() {
  const { courseId = '', cwId = '' } = useParams()
  const { data, error, loading } = useApi(() => api.submissions(courseId, cwId), [courseId, cwId])
  const downloads = useDownloads(courseId, cwId)
  const [openRow, setOpenRow] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('todas')
  const [hideCaptured, setHideCaptured] = useState(false)
  const [showSteps, setShowSteps] = useState(false)

  const statusOf = (id: string) => downloads.status?.submissions[id]
  const rows = (data?.submissions ?? []).filter((s) => {
    const d = statusOf(s.id)
    if (hideCaptured && d?.captured) return false
    if (filter === 'todas') return true
    return (d?.panel_status ?? (s.status === 'sin_entrega' ? 'sin_entrega' : 'pendiente')) === filter
  })
  const allStatuses = Object.values(downloads.status?.submissions ?? {})

  return (
    <section className="panel">
      <p>
        <Link to={`/cursos/${courseId}`}>← Tareas</Link>
      </p>
      {loading && <Loading />}
      {error && <ErrorBox message={error.message} />}
      {data && (
        <>
          <h2>
            {data.coursework.title}{' '}
            <a className="small" href={data.coursework.alternate_link} target="_blank" rel="noreferrer">
              abrir en Classroom
            </a>
          </h2>
          <p className="summary">
            {data.summary.entregadas} entregadas · {data.summary.sin_archivos} sin archivos ·{' '}
            {data.summary.sin_entrega} sin entrega · {data.summary.total} alumnos
          </p>
          <KeyBanner status={downloads.status} courseId={courseId} cwId={cwId} />
          <ProcessBar status={downloads.status} busy={downloads.busy} onProcess={() => void downloads.process()} />
          {downloads.error && <ErrorBox message={downloads.error} />}

          <button className="link small" onClick={() => setShowSteps((v) => !v)}>
            {showSteps ? '▲ Ocultar pasos por separado' : '▼ Pasos por separado (descargar, marcas)'}
          </button>
          {showSteps && (
            <div className="steps">
              <DownloadBar
                status={downloads.status}
                starting={downloads.busy}
                error={null}
                onStart={() => void downloads.startDownload()}
              />
              <MarksToolbar
                status={downloads.status}
                busy={downloads.busy}
                onToggle={(enabled) => void downloads.setModule(enabled)}
                onDetect={() => void downloads.detectMarks()}
                onConfirmAll={() => void downloads.confirmAll()}
              />
            </div>
          )}

          {allStatuses.length > 0 && (
            <FilterChips
              subs={allStatuses}
              filter={filter}
              onFilter={setFilter}
              hideCaptured={hideCaptured}
              onHideCaptured={setHideCaptured}
            />
          )}

          <table className="panel-table">
            <thead>
              <tr>
                <th>Alumno</th>
                <th>Estado</th>
                <th>Calificación</th>
                <th>Comentario privado</th>
                <th>Classroom</th>
                <th title="Ya lo capturé en Classroom">Capturado</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => {
                const d = statusOf(s.id)
                const open = openRow === s.id
                return (
                  <Fragment key={s.id}>
                    <tr className={`row-${d?.panel_status ?? s.status} ${d?.captured ? 'row-captured' : ''}`}>
                      <td>
                        <div className="student">
                          <button className="link student-name" onClick={() => setOpenRow(open ? null : s.id)}>
                            {open ? '▲' : '▼'} {s.student_name}
                          </button>
                          <MarkCrops d={d} />
                        </div>
                        {s.late && s.status !== 'sin_entrega' && <span className="badge badge-late">Tarde</span>}
                      </td>
                      <td>
                        {d ? <StatusBadge d={d} /> : <span className="muted">{STATUS_LABEL[s.status]}</span>}
                      </td>
                      <td>
                        {d && (
                          <ScoreEditor
                            key={`${s.id}-${d.final_score}-${d.score_override}`}
                            d={d}
                            onSave={(p) => void downloads.review(s.id, p)}
                          />
                        )}
                      </td>
                      <td>
                        {d && (
                          <CommentEditor
                            key={`${s.id}-${d.final_comment}-${d.comment_override === null}`}
                            d={d}
                            onSave={(p) => void downloads.review(s.id, p)}
                          />
                        )}
                      </td>
                      <td>
                        <a href={s.alternate_link} target="_blank" rel="noreferrer">
                          Abrir entrega
                        </a>
                      </td>
                      <td className="center">
                        {d && s.status !== 'sin_entrega' && (
                          <input
                            type="checkbox"
                            aria-label="Capturado"
                            checked={d.captured}
                            disabled={downloads.busy}
                            onChange={(e) => void downloads.review(s.id, { captured: e.target.checked })}
                          />
                        )}
                      </td>
                    </tr>
                    {open && (
                      <tr className="pages-row">
                        <td colSpan={6}>
                          <div className="detail-grid">
                            <div>
                              <div className="muted small">Archivos</div>
                              <AttachmentList s={s} />
                              <div className="muted small">Imágenes</div>
                              <DownloadCell d={d} open onToggle={() => setOpenRow(null)} />
                            </div>
                            <div>
                              <div className="muted small">Marca</div>
                              <MarkCell d={d} busy={downloads.busy} onDecide={(c) => void downloads.decide(s.id, c)} />
                            </div>
                            <div>
                              <div className="muted small">Calificación</div>
                              <GradeCell
                                d={d}
                                keyState={downloads.status?.key_state ?? 'sin_clave'}
                                busy={downloads.busy}
                                onGrade={() => void downloads.grade(s.id)}
                                onOpen={() => undefined}
                              />
                            </div>
                          </div>
                          {d && <GradeDetail d={d} />}
                          {d && d.status === 'lista' && <PageStrip d={d} />}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
          {rows.length === 0 && <p className="muted">No hay alumnos con ese filtro.</p>}
        </>
      )}
    </section>
  )
}
