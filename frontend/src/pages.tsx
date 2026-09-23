import { Fragment, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, type Submission, type SubmissionStatus } from './api'
import { DownloadBar, DownloadCell, PageStrip } from './downloads'
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
  return (
    <section>
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
          {data.coursework.description && <p className="description">{data.coursework.description}</p>}
          <p className="summary">
            {data.summary.entregadas} entregadas · {data.summary.sin_archivos} sin archivos ·{' '}
            {data.summary.sin_entrega} sin entrega · {data.summary.total} alumnos
          </p>
          <DownloadBar
            status={downloads.status}
            starting={downloads.starting}
            error={downloads.error}
            onStart={() => void downloads.start()}
          />
          <table>
            <thead>
              <tr>
                <th>Alumno</th>
                <th>Estado</th>
                <th>Archivos</th>
                <th>Imágenes</th>
                <th>Classroom</th>
              </tr>
            </thead>
            <tbody>
              {data.submissions.map((s) => {
                const d = downloads.status?.submissions[s.id]
                const open = openRow === s.id && d?.status === 'lista'
                return (
                <Fragment key={s.id}>
                <tr className={`row-${s.status}`}>
                  <td>{s.student_name}</td>
                  <td>
                    <span className={`badge badge-${s.status}`}>{STATUS_LABEL[s.status]}</span>
                    {/* Classroom marca "late" también a quien no entregó y ya venció; ahí no aporta. */}
                    {s.late && s.status !== 'sin_entrega' && <span className="badge badge-late">Tarde</span>}
                  </td>
                  <td>
                    <AttachmentList s={s} />
                  </td>
                  <td>
                    <DownloadCell d={d} open={open} onToggle={() => setOpenRow(open ? null : s.id)} />
                  </td>
                  <td>
                    <a href={s.alternate_link} target="_blank" rel="noreferrer">
                      Ver entrega
                    </a>
                  </td>
                </tr>
                {open && d && (
                  <tr className="pages-row">
                    <td colSpan={5}>
                      <PageStrip d={d} />
                    </td>
                  </tr>
                )}
                </Fragment>
                )
              })}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
