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

export const api = {
  me: () => request<Me>('/api/auth/me'),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  courses: () => request<Course[]>('/api/courses'),
  coursework: (courseId: string) =>
    request<CourseWork[]>(`/api/courses/${encodeURIComponent(courseId)}/coursework`),
  submissions: (courseId: string, cwId: string) =>
    request<SubmissionsResponse>(
      `/api/courses/${encodeURIComponent(courseId)}/coursework/${encodeURIComponent(cwId)}/submissions`,
    ),
}
