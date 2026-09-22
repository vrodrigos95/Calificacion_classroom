"""Configuración de la aplicación. Todas las credenciales vienen de variables de entorno."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Scopes OAuth exactos. drive.readonly es restringido: solo en modo prueba (v1).
GOOGLE_SCOPES: list[str] = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    # Con el proxy de Vite en desarrollo: http://localhost:5173/api/auth/callback
    oauth_redirect_uri: str = "http://localhost:5173/api/auth/callback"
    frontend_url: str = "http://localhost:5173"

    # Sesión y cifrado
    session_secret: str = ""
    session_https_only: bool = False
    # Clave Fernet (base64 de 32 bytes) para cifrar refresh tokens en la BD
    token_encryption_key: str = ""

    # Base de datos
    database_url: str = "sqlite:///./data/app.db"
    data_dir: str = "./data"

    # Claude (se usa a partir de la etapa 3)
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5"

    # Defaults de docente (sobrescribibles por docente en BD)
    retention_days: int = Field(default=14, ge=1)
    minor_error_factor: float = Field(default=0.5, ge=0, le=1)
    mark_accept_threshold: float = Field(default=0.85, ge=0, le=1)
    mark_doubtful_threshold: float = Field(default=0.60, ge=0, le=1)
    exercise_min_confidence: float = Field(default=0.80, ge=0, le=1)

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
