import { BrowserRouter, Link, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { MarksPage } from './MarksPage'
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
        <Link to="/" className="brand">
          Revisor de tareas
        </Link>
        {me && (
          <span className="header-right">
            <Link to="/configuracion">Mi marca</Link>
            <span>{me.name}</span>
            <button onClick={logout}>Cerrar sesión</button>
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
          <Route path="/configuracion" element={<MarksPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
