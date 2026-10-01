import { useEffect, useState } from 'react'
import { api, type AssignmentSettings, type GradingMode } from './api'

/** Modo de calificación de la tarea: por ejercicios (clave + Claude) o solo revisar firma. */
export function ModeBox({ courseId, cwId, onChange }: { courseId: string; cwId: string; onChange: () => void }) {
  const [settings, setSettings] = useState<AssignmentSettings | null>(null)
  const [score, setScore] = useState('')
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api
      .settings(courseId, cwId)
      .then((s) => {
        if (!alive) return
        setSettings(s)
        setScore(String(s.unsigned_score))
        setComment(s.unsigned_comment)
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      alive = false
    }
  }, [courseId, cwId])

  const save = async (patch: Partial<AssignmentSettings>) => {
    setError(null)
    try {
      const s = await api.saveSettings(courseId, cwId, patch)
      setSettings(s)
      setScore(String(s.unsigned_score))
      setComment(s.unsigned_comment)
      onChange()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (!settings) return null
  const mode = settings.grading_mode
  const setMode = (m: GradingMode) => void save({ grading_mode: m })

  return (
    <div className="mode-box">
      <strong>¿Cómo se califica esta tarea?</strong>
      <label className="toggle">
        <input type="radio" name="modo" checked={mode === 'solo_firma'} onChange={() => setMode('solo_firma')} /> Solo revisar
        mi firma <span className="muted small">(no usa Claude)</span>
      </label>
      <label className="toggle">
        <input type="radio" name="modo" checked={mode === 'ejercicios'} onChange={() => setMode('ejercicios')} /> Revisar
        los ejercicios <span className="muted small">(con firma = 100; las demás con clave de respuestas y Claude)</span>
      </label>
      {mode === 'solo_firma' && (
        <div className="mode-fields">
          <span>Con firma: <strong>100</strong>. Sin firma:</span>
          <input
            className="score-input"
            inputMode="decimal"
            aria-label="Calificación sin firma"
            value={score}
            onChange={(e) => setScore(e.target.value)}
            onBlur={() => {
              const n = Number(score)
              if (score.trim() === '' || Number.isNaN(n) || n < 0 || n > 100) setScore(String(settings.unsigned_score))
              else if (n !== settings.unsigned_score) void save({ unsigned_score: n })
            }}
          />
          <span>con el comentario</span>
          <input
            className="comment-input"
            aria-label="Comentario sin firma"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onBlur={() => comment !== settings.unsigned_comment && void save({ unsigned_comment: comment })}
          />
        </div>
      )}
      {error && <div className="alert">{error}</div>}
    </div>
  )
}
