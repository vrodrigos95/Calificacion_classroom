import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_teacher
from app.auth import google_oauth
from app.config import get_settings
from app.db.models import Teacher
from app.db.session import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _to_frontend(path: str = "/", **params: str) -> RedirectResponse:
    url = get_settings().frontend_url.rstrip("/") + path
    if params:
        url += "?" + urlencode(params)
    return RedirectResponse(url, status_code=303)


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    url, state, verifier = google_oauth.start_authorization()
    request.session["oauth_state"] = state
    request.session["oauth_verifier"] = verifier
    return RedirectResponse(url, status_code=303)


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    expected_state = request.session.pop("oauth_state", None)
    verifier = request.session.pop("oauth_verifier", None)
    if error:
        return _to_frontend("/login", error="acceso_denegado")
    if not code or not state or state != expected_state or not verifier:
        return _to_frontend("/login", error="estado_invalido")
    try:
        result = google_oauth.finish_authorization(code, state, verifier)
    except Exception:
        log.exception("Falló el intercambio del código OAuth")
        return _to_frontend("/login", error="oauth")

    missing = google_oauth.missing_scopes(result.granted_scopes)
    if missing:
        # Google permite desmarcar permisos en la pantalla de consentimiento.
        # Los scopes no son datos personales; registrarlos ayuda a diagnosticar.
        log.warning(
            "Permisos incompletos. Faltan: %s | Concedidos: %s",
            " ".join(missing),
            " ".join(sorted(result.granted_scopes)),
        )
        return _to_frontend("/login", error="permisos", faltan=" ".join(missing))

    teacher = google_oauth.upsert_teacher(db, result)
    request.session.clear()
    request.session["teacher_id"] = teacher.id
    log.info("Inicio de sesión del docente id=%s", teacher.id)
    return _to_frontend("/")


class Me(BaseModel):
    id: int
    name: str
    email: str


@router.get("/me", response_model=Me)
def me(teacher: Teacher = Depends(current_teacher)) -> Me:
    return Me(id=teacher.id, name=teacher.name, email=teacher.email)


@router.post("/logout", status_code=204)
def logout(request: Request) -> None:
    teacher_id = request.session.get("teacher_id")
    if teacher_id:
        google_oauth.invalidate_credentials(teacher_id)
    request.session.clear()
