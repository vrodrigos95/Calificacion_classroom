"""Flujo OAuth de Google (web server flow con PKCE) y credenciales por docente."""

import os
import threading
from dataclasses import dataclass

import google.auth.transport.requests
from google.oauth2 import id_token as google_id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.auth import token_crypto
from app.config import GOOGLE_SCOPES, get_settings
from app.db.models import OAuthToken, Teacher, TeacherSettings, utcnow

# Google puede devolver los scopes en otro orden o con alias ("email" vs userinfo.email).
# Validamos los scopes concedidos nosotros mismos (ver missing_scopes).
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

TOKEN_URI = "https://oauth2.googleapis.com/token"

# Alias con los que Google puede reportar los scopes de identidad.
_SCOPE_ALIASES = {
    "email": "https://www.googleapis.com/auth/userinfo.email",
    "profile": "https://www.googleapis.com/auth/userinfo.profile",
}


class OAuthError(RuntimeError):
    pass


def _client_config() -> dict:
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise OAuthError("Faltan GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET en el entorno")
    return {
        "web": {
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": TOKEN_URI,
            "redirect_uris": [s.oauth_redirect_uri],
        }
    }


def _flow(state: str | None = None, code_verifier: str | None = None) -> Flow:
    return Flow.from_client_config(
        _client_config(),
        scopes=GOOGLE_SCOPES,
        redirect_uri=get_settings().oauth_redirect_uri,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=code_verifier is None,
    )


def start_authorization() -> tuple[str, str, str]:
    """Devuelve (url, state, code_verifier). state y verifier se guardan en la sesión."""
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",  # garantiza refresh_token en cada inicio de sesión
        include_granted_scopes="true",
    )
    return url, state, flow.code_verifier


def normalize_scopes(raw: str | list[str] | None) -> set[str]:
    if raw is None:
        return set()
    items = raw.split() if isinstance(raw, str) else list(raw)
    return {_SCOPE_ALIASES.get(s, s) for s in items}


def missing_scopes(granted: set[str]) -> list[str]:
    """Scopes pedidos que no se concedieron. Un scope con escritura cubre su versión .readonly."""
    return [
        s for s in GOOGLE_SCOPES if s not in granted and s.removesuffix(".readonly") not in granted
    ]


@dataclass
class OAuthResult:
    google_sub: str
    email: str
    name: str
    refresh_token: str
    granted_scopes: set[str]


def finish_authorization(code: str, state: str, code_verifier: str) -> OAuthResult:
    flow = _flow(state=state, code_verifier=code_verifier)
    token = flow.fetch_token(code=code)
    granted = normalize_scopes(token.get("scope"))
    creds = flow.credentials
    if not creds.id_token:
        raise OAuthError("Google no devolvió id_token")
    info = google_id_token.verify_oauth2_token(
        creds.id_token,
        google.auth.transport.requests.Request(),
        get_settings().google_client_id,
    )
    if not creds.refresh_token:
        raise OAuthError("Google no devolvió refresh_token")
    return OAuthResult(
        google_sub=info["sub"],
        email=info.get("email", ""),
        name=info.get("name", ""),
        refresh_token=creds.refresh_token,
        granted_scopes=granted,
    )


def upsert_teacher(db: Session, result: OAuthResult) -> Teacher:
    teacher = db.query(Teacher).filter_by(google_sub=result.google_sub).one_or_none()
    if teacher is None:
        teacher = Teacher(google_sub=result.google_sub, email=result.email, name=result.name)
        teacher.settings = TeacherSettings()
        db.add(teacher)
    else:
        teacher.email, teacher.name = result.email, result.name
        teacher.last_login_at = utcnow()
    enc = token_crypto.encrypt(result.refresh_token)
    scopes = " ".join(sorted(result.granted_scopes))
    if teacher.token is None:
        teacher.token = OAuthToken(refresh_token_enc=enc, scopes=scopes)
    else:
        teacher.token.refresh_token_enc, teacher.token.scopes = enc, scopes
    db.commit()
    invalidate_credentials(teacher.id)
    return teacher


# Caché en memoria de credenciales para no refrescar el access token en cada petición.
_cred_cache: dict[int, Credentials] = {}
_cred_lock = threading.Lock()


def invalidate_credentials(teacher_id: int) -> None:
    with _cred_lock:
        _cred_cache.pop(teacher_id, None)


def credentials_for(db: Session, teacher_id: int) -> Credentials:
    with _cred_lock:
        cached = _cred_cache.get(teacher_id)
    if cached is not None:
        return cached
    token = db.query(OAuthToken).filter_by(teacher_id=teacher_id).one_or_none()
    if token is None:
        raise OAuthError("El docente no tiene token; debe iniciar sesión de nuevo")
    s = get_settings()
    creds = Credentials(
        token=None,
        refresh_token=token_crypto.decrypt(token.refresh_token_enc),
        token_uri=TOKEN_URI,
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        scopes=token.scopes.split(),
    )
    with _cred_lock:
        _cred_cache[teacher_id] = creds
    return creds
