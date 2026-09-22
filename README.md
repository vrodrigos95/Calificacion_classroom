# Revisor de tareas manuscritas para Google Classroom

App web que ayuda a docentes de matemáticas a calificar tareas entregadas en Classroom
como foto o PDF. **La app no escribe nada en Classroom**: lee las entregas, genera una
calificación y un comentario sugeridos, y el docente los captura a mano.

- Backend: Python 3.11+, FastAPI, SQLAlchemy + Alembic (SQLite en v1)
- Frontend: React + TypeScript (Vite)

## Estado

| Etapa | Contenido | Estado |
|---|---|---|
| 1 | OAuth y listado de cursos, tareas y entregas | ✅ |
| 2 | Descarga y conversión a imágenes | pendiente |
| 3 | Módulo de marca de validación | pendiente |
| 4 | Calificación de una entrega | pendiente |
| 5 | Procesamiento por lote y panel | pendiente |
| 6 | Detección de copias | pendiente |

## Configurar Google Cloud (una sola vez)

1. En [Google Cloud Console](https://console.cloud.google.com/) crea un proyecto.
2. **APIs y servicios → Biblioteca**: habilita **Google Classroom API** y **Google Drive API**.
3. **Pantalla de consentimiento OAuth** (Google Auth Platform):
   - Tipo de usuario: **Externo** (o Interno si tu cuenta de la UdeG lo permite).
   - Estado de publicación: **Pruebas**. Agrega tu cuenta como **usuario de prueba**.
     `drive.readonly` es un scope restringido; en modo prueba no requiere verificación.
   - Scopes: los de la tabla de abajo.
4. **Credenciales → Crear credenciales → ID de cliente de OAuth → Aplicación web**:
   - URI de redirección autorizado: `http://localhost:5173/api/auth/callback`
5. Copia el ID y el secreto a `backend/.env` (usa `.env.example` como plantilla).

> Si tu cuenta es de Google Workspace institucional, el administrador puede tener
> bloqueado el acceso de apps de terceros a Classroom o Drive. Si al iniciar sesión
> aparece "acceso bloqueado", ese es el motivo.

### Scopes

| Scope | Uso |
|---|---|
| `openid`, `userinfo.email`, `userinfo.profile` | Identificar al docente |
| `classroom.courses.readonly` | Listar cursos |
| `classroom.coursework.students.readonly` | Tareas y entregas (estado, adjuntos, enlace) |
| `classroom.rosters.readonly` | Nombres de los alumnos |
| `drive.readonly` | Descargar los archivos entregados (solo v1, modo prueba) |

## Correr en local

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env        # y llena los valores
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend (otra terminal)
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

### En Windows (PowerShell)

```powershell
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # si falla: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -e ".[dev]"
copy ..\.env.example .env       # y llena los valores con: notepad .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend (otra ventana de PowerShell)
cd frontend
npm install
npm run dev
```

Vite reenvía `/api` al backend, así que la cookie de sesión y el redirect de OAuth
usan el mismo origen (`localhost:5173`).

## Pruebas

```bash
cd backend && pytest
cd frontend && npm run build && npm run lint
```

## Privacidad (los alumnos son menores)

- De los alumnos solo se guarda lo necesario para el panel; nunca su correo.
- Los logs pasan por un filtro que enmascara correos y nombres; el código solo registra IDs internos.
- Las imágenes descargadas se borrarán tras `RETENTION_DAYS` días (etapa 2).
- El refresh token de Google se guarda cifrado (Fernet, `TOKEN_ENCRYPTION_KEY`).
