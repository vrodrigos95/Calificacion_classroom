export interface Me {
  id: number
  name: string
  email: string
}

export interface Course {
  id: string
  name: string
  section: string
  alternate_link: string
}

export interface Attachment {
  file_id: string
  title: string
  alternate_link: string
}

export interface CourseWork {
  id: string
  title: string
  description: string
  state: string
  alternate_link: string
  due_date: string | null
  max_points: number | null
  materials: Attachment[]
  other_materials: number
}

export type SubmissionStatus = 'entregada' | 'entregada_sin_archivos' | 'sin_entrega'

export interface Submission {
  id: string
  user_id: string
  student_name: string
  state: string
  status: SubmissionStatus
  late: boolean
  alternate_link: string
  attachments: Attachment[]
  other_attachments: number
}

export interface SubmissionsResponse {
  coursework: CourseWork
  summary: { total: number; entregadas: number; sin_archivos: number; sin_entrega: number }
  submissions: Submission[]
}

export type DownloadState =
  | 'sin_entrega'
  | 'pendiente'
  | 'descargando'
  | 'lista'
  | 'error'
  | 'expirada'

export interface PageInfo {
  id: number
  index: number
  width: number
  height: number
}

export type MarkStatus =
  | 'con_marca'
  | 'dudosa'
  | 'sin_marca'
  | 'error'
  | 'desactivado'
  | 'sin_config'
  | 'no_revisable'

export interface Detection {
  id: number
  mark_name: string
  meaning: Meaning
  verdict: 'marca' | 'dudosa'
  confidence: number
  reason: string
  verifier: 'claude' | 'local' | 'ninguno'
  page_index: number
}

export interface SubmissionDownload {
  status: DownloadState
  error: string | null
  pages: PageInfo[]
  mark_status: MarkStatus | null
  mark_detail: string | null
  mark_confirmed: boolean | null
  detections: Detection[]
  suggested_score: number | null
}

export interface DownloadStatus {
  running: boolean
  marks_running: boolean
  mark_module_enabled: boolean
  counts: Partial<Record<DownloadState, number>>
  /** clave: id de la entrega en Classroom */
  submissions: Record<string, SubmissionDownload>
}

export const pageImageUrl = (pageId: number) => `/api/pages/${pageId}`
export const cropUrl = (detectionId: number) => `/api/detections/${detectionId}/crop`

export type Meaning = 'correcta' | 'informativa'
export type Zone = 'primera' | 'cualquiera'

export interface Mark {
  id: number
  name: string
  meaning: Meaning
  zone: Zone
  active: boolean
  colored: boolean
  references: { id: number; url: string }[]
}

export interface MarksConfig {
  verifier: 'claude' | 'local'
  model: string | null
  marks: Mark[]
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, { credentials: 'same-origin', ...init })
  if (!resp.ok) {
    let detail = `Error ${resp.status}`
    try {
      const body = await resp.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(resp.status, detail)
  }
  return resp.status === 204 ? (undefined as T) : resp.json()
}

const cw = (courseId: string, cwId: string) =>
  `/api/courses/${encodeURIComponent(courseId)}/coursework/${encodeURIComponent(cwId)}`

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  me: () => request<Me>('/api/auth/me'),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  courses: () => request<Course[]>('/api/courses'),
  coursework: (courseId: string) =>
    request<CourseWork[]>(`/api/courses/${encodeURIComponent(courseId)}/coursework`),
  downloadStatus: (courseId: string, cwId: string) =>
    request<DownloadStatus>(`${cw(courseId, cwId)}/download`),
  startDownload: (courseId: string, cwId: string) =>
    request<DownloadStatus>(`${cw(courseId, cwId)}/download`, { method: 'POST' }),
  submissions: (courseId: string, cwId: string) =>
    request<SubmissionsResponse>(`${cw(courseId, cwId)}/submissions`),

  // Módulo de marca
  marks: () => request<MarksConfig>('/api/marks'),
  createMark: (form: FormData) => request<Mark>('/api/marks', { method: 'POST', body: form }),
  updateMark: (id: number, patch: Partial<Pick<Mark, 'name' | 'meaning' | 'zone' | 'active'>>) =>
    request<Mark>(`/api/marks/${id}`, json('PATCH', patch)),
  replaceReferences: (id: number, form: FormData) =>
    request<Mark>(`/api/marks/${id}/references`, { method: 'PUT', body: form }),
  deleteMark: (id: number) => request<void>(`/api/marks/${id}`, { method: 'DELETE' }),
  setMarkModule: (courseId: string, cwId: string, enabled: boolean) =>
    request<{ mark_module_enabled: boolean }>(
      `${cw(courseId, cwId)}/settings`,
      json('PUT', { mark_module_enabled: enabled }),
    ),
  detectMarks: (courseId: string, cwId: string) =>
    request<{ started: boolean }>(`${cw(courseId, cwId)}/marks/detect`, { method: 'POST' }),
  markDecision: (courseId: string, cwId: string, sid: string, confirmed: boolean | null) =>
    request<{ mark_status: MarkStatus }>(
      `${cw(courseId, cwId)}/submissions/${encodeURIComponent(sid)}/mark-decision`,
      json('PUT', { confirmed }),
    ),
  confirmAllMarks: (courseId: string, cwId: string) =>
    request<{ confirmed: number }>(`${cw(courseId, cwId)}/marks/confirm-all`, { method: 'POST' }),
}
