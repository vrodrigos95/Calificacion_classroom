import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, type AnswerKey, type KeyExercise } from './api'

const EMPTY: KeyExercise = { numero: '', enunciado: '', respuesta_final: '', procedimiento_clave: '', criterios_notacion: [] }

const FACTORS = [
  { v: 0, label: '0 (error menor no vale)' },
  { v: 0.25, label: '¼ del valor' },
  { v: 0.5, label: '½ del valor' },
  { v: 0.75, label: '¾ del valor' },
]

function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err)
}

export function KeyPage() {
  const { courseId = '', cwId = '' } = useParams()
  const [key, setKey] = useState<AnswerKey | null>(null)
  const [rows, setRows] = useState<KeyExercise[]>([])
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])

  const apply = (k: AnswerKey) => {
    setKey(k)
    if (k.state !== 'generando') {
      setRows(k.exercises.length ? k.exercises : [{ ...EMPTY, numero: '1' }])
      setDirty(false)
    }
  }

  // Carga inicial y sondeo mientras se genera la clave.
  useEffect(() => {
    let alive = true
    const delay = key === null ? 0 : key.state === 'generando' ? 2000 : null
    if (delay === null) return
    const t = window.setTimeout(() => {
      api
        .key(courseId, cwId)
        .then((k) => alive && apply(k))
        .catch((err) => {
          if (err instanceof ApiError && err.status === 401) window.location.assign('/login')
          else if (alive) setError(errorText(err))
        })
    }, delay)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [key, courseId, cwId])

  const run = async (action: () => Promise<AnswerKey>) => {
    setBusy(true)
    setError(null)
    try {
      apply(await action())
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const edit = (i: number, patch: Partial<KeyExercise>) => {
    setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)))
    setDirty(true)
  }

  const cleaned = () => rows.map((r) => ({ ...r, criterios_notacion: r.criterios_notacion.filter(Boolean) }))
  const save = () => run(() => api.saveKey(courseId, cwId, cleaned()))
  const validate = () =>
    run(async () => {
      if (dirty) await api.saveKey(courseId, cwId, cleaned())
      return api.validateKey(courseId, cwId)
    })
  const fromTeacher = () => {
    const form = new FormData()
    form.append('text', text)
    for (const f of files) form.append('files', f)
    return run(() => api.keyFromTeacher(courseId, cwId, form))
  }

  if (!key) return <p className="muted">{error ?? 'Cargando…'}</p>
  const generating = key.state === 'generando'

  return (
    <section>
      <p>
        <Link to={`/cursos/${courseId}/tareas/${cwId}`}>← Entregas</Link>
      </p>
      <h2>Clave de respuestas</h2>

      <div className={key.state === 'validada' ? 'info' : 'warn-box'}>
        {key.state === 'validada' && `Validada ✓ (versión ${key.version}). Si la cambias, tendrás que validarla otra vez.`}
        {key.state === 'sin_validar' && 'Revisa y corrige la clave, y luego da clic en «Validar clave». Nunca se califica con una clave sin validar.'}
        {key.state === 'sin_clave' && 'Captura la clave abajo, súbela, o pide a Claude que resuelva los ejercicios.'}
        {key.state === 'generando' && 'Generando la clave con Claude… puede tardar un minuto.'}
        {key.state === 'error' && `No se pudo generar la clave: ${key.job_error}`}
      </div>
      {key.warning && <div className="warn-box">{key.warning}</div>}
      {key.job_error && key.state !== 'error' && <div className="alert">Último intento: {key.job_error}</div>}
      {error && <div className="alert">{error}</div>}

      <div className="key-modes">
        <div className="mark-card">
          <div className="mark-form">
            <strong>A. Subir mi clave</strong>
            <span className="muted small">Escríbela o sube una foto o PDF. Claude la ordena en la tabla para que la revises.</span>
            <textarea
              rows={3}
              placeholder="Ej.: 1) 33%  2) 15.38%  3) 40%  4) P(A ∪ B) = 70%"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <input type="file" accept="image/*,application/pdf" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            <button disabled={busy || generating || !key.model_available || (!text.trim() && !files.length)} onClick={() => void fromTeacher()}>
              Leer mi clave con Claude
            </button>
          </div>
        </div>
        <div className="mark-card">
          <div className="mark-form">
            <strong>B. Que Claude resuelva los ejercicios</strong>
            <span className="muted small">
              Busca el enunciado en la descripción y adjuntos de la tarea; si no está, en las hojas de los alumnos
              (descárgalas primero). Si distintos alumnos muestran enunciados diferentes, te avisa.
            </span>
            <button disabled={busy || generating || !key.model_available} onClick={() => void run(() => api.solveKey(courseId, cwId))}>
              Resolver con Claude
            </button>
          </div>
        </div>
      </div>
      {!key.model_available && (
        <p className="muted small">
          Las opciones A y B necesitan la clave de la API de Claude (ANTHROPIC_API_KEY). Sin ella, captura la clave en la
          tabla.
        </p>
      )}

      <h3>Ejercicios {key.source === 'resuelta_por_modelo' && <span className="muted small">(resueltos por Claude: revísalos)</span>}</h3>
      <table className="key-table">
        <thead>
          <tr>
            <th>Núm.</th>
            <th>Enunciado</th>
            <th>Respuesta correcta</th>
            <th>Procedimiento esperado</th>
            <th>Notación exigida (separa con ;)</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>
                <input className="num" value={r.numero} disabled={generating} onChange={(e) => edit(i, { numero: e.target.value })} />
              </td>
              <td>
                <textarea rows={2} value={r.enunciado} disabled={generating} onChange={(e) => edit(i, { enunciado: e.target.value })} />
              </td>
              <td>
                <textarea rows={2} value={r.respuesta_final} disabled={generating} onChange={(e) => edit(i, { respuesta_final: e.target.value })} />
              </td>
              <td>
                <textarea rows={2} value={r.procedimiento_clave} disabled={generating} onChange={(e) => edit(i, { procedimiento_clave: e.target.value })} />
              </td>
              <td>
                <textarea
                  rows={2}
                  value={r.criterios_notacion.join('; ')}
                  disabled={generating}
                  onChange={(e) => edit(i, { criterios_notacion: e.target.value.split(';').map((x) => x.trim()) })}
                />
              </td>
              <td>
                <button className="link" disabled={generating} onClick={() => { setRows((x) => x.filter((_, j) => j !== i)); setDirty(true) }}>
                  Quitar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="download-bar">
        <button disabled={generating} onClick={() => { setRows((x) => [...x, { ...EMPTY, numero: String(x.length + 1) }]); setDirty(true) }}>
          + Agregar ejercicio
        </button>
        <button disabled={busy || generating || !dirty} onClick={() => void save()}>
          Guardar cambios
        </button>
        <button className="primary" disabled={busy || generating || (key.state === 'validada' && !dirty)} onClick={() => void validate()}>
          {dirty ? 'Guardar y validar clave' : 'Validar clave'}
        </button>
      </div>

      <h3>Error menor</h3>
      <p className="muted small">
        Error menor = procedimiento bien, resultado o notación mal. Cada ejercicio vale 100 / número de ejercicios.
      </p>
      <label className="toggle">
        En esta tarea, un error menor vale:{' '}
        <select
          value={key.minor_error_factor_override === null ? 'default' : String(key.minor_error_factor_override)}
          disabled={busy}
          onChange={(e) =>
            void run(() => api.setMinorFactor(courseId, cwId, e.target.value === 'default' ? null : Number(e.target.value)))
          }
        >
          <option value="default">Lo de mi configuración ({key.teacher_minor_error_factor} del valor)</option>
          {FACTORS.map((f) => (
            <option key={f.v} value={f.v}>
              {f.label}
            </option>
          ))}
        </select>
      </label>
    </section>
  )
}
