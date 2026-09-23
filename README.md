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
| 2 | Descarga y conversión a imágenes | ✅ |
| 3 | Módulo de marca de validación | ✅ modo local · falta probar con Claude |
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

## Actualizar a una versión nueva

```powershell
git pull
cd backend
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"     # por si hay librerías nuevas
alembic upgrade head        # por si hay tablas nuevas
```

## Pruebas

```bash
cd backend && pytest
cd frontend && npm run build && npm run lint
```

## Módulo de marca de validación

1. En **Mi marca** sube 1 a 5 fotos o recortes de tu firma o sello, elige su significado
   ("Tarea correcta" = 100 sin revisar contenido, o "Solo informativa") y dónde buscarla.
2. En la tarea: **Descargar entregas** y luego **Revisar marcas**.
3. Cada entrega con marca muestra el recorte junto al nombre del alumno.

Cómo decide:

- **Prefiltro por color** (sin costo): busca la tinta de tu marca en el espacio de color Lab,
  que detecta tintas tenues sobre cuadrícula y la separa de otros colores (azul, rosa…).
- **Verificación**:
  - *Con `ANTHROPIC_API_KEY`*: Claude compara cada recorte con tus referencias y da una
    confianza. ≥ 0.85 → "Con marca" (100); 0.60–0.85 → "¿Es tu marca?" (tú decides);
    < 0.60 → sin marca. Si la API falla, la entrega queda en "Revisar a mano" con el recorte.
  - *Sin clave (modo local)*: la app encuentra la tinta y te muestra el recorte, pero **nunca
    pone 100 sola**; tú confirmas cada una (o "Confirmar las N por confirmar" tras verlas).
- El interruptor "Buscar mi marca en esta tarea" desactiva el módulo por tarea.
- Tu decisión (sí / no) nunca se sobrescribe al volver a revisar.

## Privacidad (los alumnos son menores)

- De los alumnos solo se guarda lo necesario para el panel; nunca su correo.
- Los logs pasan por un filtro que enmascara correos y nombres; el código solo registra IDs internos.
- Las imágenes descargadas y los recortes de marcas se borran tras `RETENTION_DAYS` días (configurable por docente).
- Las imágenes de las entregas se envían a la API de Anthropic solo si configuras `ANTHROPIC_API_KEY`.
- Los tracebacks de errores también pasan por el filtro de nombres.
- El refresh token de Google se guarda cifrado (Fernet, `TOKEN_ENCRYPTION_KEY`).
