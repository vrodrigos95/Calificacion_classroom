import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, classroom
from app.auth.google_oauth import OAuthError, invalidate_credentials
from app.auth.token_crypto import TokenCryptoError
from app.config import get_settings
from app.logging_conf import setup_logging

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    if not settings.session_secret:
        raise RuntimeError("Falta SESSION_SECRET en el entorno")

    app = FastAPI(title="Revisor de tareas Classroom")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="cc_session",
        same_site="lax",
        https_only=settings.session_https_only,
        max_age=60 * 60 * 12,
    )
    app.include_router(auth.router)
    app.include_router(classroom.router)

    @app.exception_handler(RefreshError)
    @app.exception_handler(OAuthError)
    @app.exception_handler(TokenCryptoError)
    async def _auth_expired(request: Request, exc: Exception):
        teacher_id = request.session.get("teacher_id")
        if teacher_id:
            invalidate_credentials(teacher_id)
        log.warning("Credenciales inválidas: %s", type(exc).__name__)
        return JSONResponse(
            status_code=401,
            content={"detail": "Tu sesión con Google expiró. Vuelve a iniciar sesión."},
        )

    @app.exception_handler(HttpError)
    async def _google_error(request: Request, exc: HttpError):
        status = exc.resp.status if exc.resp is not None else 502
        # Solo el código y el motivo: la URL puede contener IDs de alumnos.
        log.warning("Error de la API de Google: %s %s", status, exc.reason)
        detail = {
            403: "Google negó el acceso. Revisa que seas docente del curso y que "
            "hayas concedido todos los permisos.",
            404: "Google no encontró el recurso (curso o tarea).",
            429: "Google limitó las peticiones. Intenta de nuevo en un minuto.",
        }.get(status, f"Error de la API de Google ({status}).")
        return JSONResponse(status_code=502 if status >= 500 else status, content={"detail": detail})

    @app.get("/api/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
