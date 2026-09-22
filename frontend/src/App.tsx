import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { CourseWorkPage, CoursesPage, LoginPage, SubmissionsPage } from './pages'
import { useApi } from './useApi'

function Layout() {
  const { data: me } = useApi(api.me, [])
  const logout = async () => {
    await api.logout()
    window.location.assign('/login')
  }
  return (
    <>
      <header>
        <strong>Revisor de tareas</strong>
        {me && (
          <span>
            {me.name} <button onClick={logout}>Cerrar sesión</button>
          </span>
        )}
      </header>
      <main>
        <Outlet />
      </main>
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Layout />}>
          <Route path="/" element={<CoursesPage />} />
          <Route path="/cursos/:courseId" element={<CourseWorkPage />} />
          <Route path="/cursos/:courseId/tareas/:cwId" element={<SubmissionsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
