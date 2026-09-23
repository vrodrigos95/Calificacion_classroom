import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type Mark, type MarksConfig, type Meaning, type Zone } from './api'
import { useApi } from './useApi'

const MEANINGS: Record<Meaning, string> = {
  correcta: 'Tarea correcta: vale 100 y no se revisa el contenido',
  informativa: 'Solo informativa: se muestra, pero la tarea se revisa normal',
}
const ZONES: Record<Zone, string> = {
  primera: 'Solo en la primera página',
  cualquiera: 'En cualquier página',
}

function errorText(err: unknown) {
  return err instanceof ApiError || err instanceof Error ? err.message : String(err)
}

function MarkCard({ mark, onChange }: { mark: Mark; onChange: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const save = async (patch: Parameters<typeof api.updateMark>[1]) => {
    setError(null)
    try {
      await api.updateMark(mark.id, patch)
      onChange()
    } catch (err) {
      setError(errorText(err))
    }
  }
  const replace = async (files: FileList | null) => {
    if (!files?.length) return
    const form = new FormData()
    for (const f of files) form.append('files', f)
    try {
      await api.replaceReferences(mark.id, form)
      onChange()
    } catch (err) {
      setError(errorText(err))
    }
  }
  const remove = async () => {
    if (!window.confirm(`¿Borrar la marca «${mark.name}»?`)) return
    await api.deleteMark(mark.id)
    onChange()
  }
  return (
    <div className="mark-card">
      <div className="ref-strip">
        {mark.references.map((r) => (
          <img key={r.id} src={r.url} alt="Referencia" />
        ))}
      </div>
      <div className="mark-form">
        <strong>{mark.name}</strong>
        {!mark.colored && (
          <div className="warn small">
            La tinta no tiene un color distintivo (negro o gris): la búsqueda por color no aplica y se
            revisará la página completa con Claude.
          </div>
        )}
        <label>
          Significado
          <select value={mark.meaning} onChange={(e) => void save({ meaning: e.target.value as Meaning })}>
            {Object.entries(MEANINGS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Dónde buscarla
          <select value={mark.zone} onChange={(e) => void save({ zone: e.target.value as Zone })}>
            {Object.entries(ZONES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={mark.active} onChange={(e) => void save({ active: e.target.checked })} /> Activa
        </label>
        <div className="mark-card-actions">
          <label className="button">
            Cambiar imágenes
            <input type="file" accept="image/*" multiple hidden onChange={(e) => void replace(e.target.files)} />
          </label>
          <button onClick={() => void remove()}>Borrar</button>
        </div>
        {error && <div className="alert">{error}</div>}
      </div>
    </div>
  )
}

function NewMarkForm({ onCreated }: { onCreated: () => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const formEl = e.currentTarget // React limpia el evento después del await
    const form = new FormData(formEl)
    form.delete('files')
    for (const f of files) form.append('files', f)
    setSaving(true)
    setError(null)
    try {
      await api.createMark(form)
      formEl.reset()
      setFiles([])
      onCreated()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }
  return (
    <form className="mark-card new-mark" onSubmit={(e) => void submit(e)}>
      <div className="ref-strip">
        {files.map((f) => (
          <img key={f.name + f.size} src={URL.createObjectURL(f)} alt={f.name} />
        ))}
      </div>
      <div className="mark-form">
        <strong>Agregar una marca</strong>
        <label>
          Nombre
          <input name="name" defaultValue="Mi firma" required maxLength={100} />
        </label>
        <label>
          Imágenes de referencia (1 a 5 fotos o recortes de tu firma o sello)
          <input
            type="file"
            accept="image/*"
            multiple
            required
            onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 5))}
          />
        </label>
        <label>
          Significado
          <select name="meaning" defaultValue="correcta">
            {Object.entries(MEANINGS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Dónde buscarla
          <select name="zone" defaultValue="primera">
            {Object.entries(ZONES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={saving || files.length === 0}>
          {saving ? 'Guardando…' : 'Guardar marca'}
        </button>
        {error && <div className="alert">{error}</div>}
      </div>
    </form>
  )
}

export function MarksPage() {
  const [version, setVersion] = useState(0)
  const { data, error, loading } = useApi<MarksConfig>(api.marks, [version])
  const reload = () => setVersion((v) => v + 1)
  return (
    <section>
      <p>
        <Link to="/">← Cursos</Link>
      </p>
      <h2>Mi marca de validación</h2>
      <p className="muted">
        Sube fotos de tu firma o sello tal como aparece en las hojas. La app la busca en cada entrega y te
        muestra el recorte junto al nombre del alumno.
      </p>
      {data && (
        <div className={data.verifier === 'claude' ? 'info' : 'warn-box'}>
          {data.verifier === 'claude'
            ? `Verificación con Claude (${data.model}). Solo las coincidencias claras valen 100; las dudosas te las muestra para que decidas.`
            : 'Modo local (sin clave de la API de Claude): la app encuentra la tinta de tu marca y te muestra el recorte, pero tú confirmas cada una. Nunca pone 100 sola.'}
        </div>
      )}
      {loading && <p className="muted">Cargando…</p>}
      {error && <div className="alert">{error.message}</div>}
      {data?.marks.map((m) => <MarkCard key={m.id} mark={m} onChange={reload} />)}
      <NewMarkForm onCreated={reload} />
    </section>
  )
}
