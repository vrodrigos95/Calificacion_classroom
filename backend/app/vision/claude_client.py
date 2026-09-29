"""Llamadas a Claude con salida JSON validada contra un esquema (Pydantic).

Centraliza: modelo configurable (CLAUDE_MODEL), fallback de rechazo del servidor,
traducción de errores a mensajes claros en español y registro de tokens (sin datos
de alumnos).
"""

import base64
import logging
from dataclasses import dataclass
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from app.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Modelos con fallback de rechazo del lado del servidor (modo "default").
FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}


class VisionError(RuntimeError):
    """La llamada al modelo no se pudo completar; el mensaje es apto para el docente."""


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int


def image_block(data: bytes, media_type: str = "image/jpeg") -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.standard_b64encode(data).decode()},
    }


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def has_api_key() -> bool:
    return bool(get_settings().anthropic_api_key)


class ClaudeClient:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str | None = None):
        settings = get_settings()
        self.model = model or settings.claude_model
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3)

    def structured(
        self, system: str, content: list[dict], output: type[T], *, purpose: str, max_tokens: int = 16000
    ) -> tuple[T, Usage]:
        kwargs = {}
        if self.model in FALLBACK_MODELS:
            kwargs = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            resp = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=output,
                **kwargs,
            )
        except anthropic.AuthenticationError as exc:
            raise VisionError("La clave de la API de Claude no es válida") from exc
        except anthropic.PermissionDeniedError as exc:
            raise VisionError("La clave de la API de Claude no tiene permiso para este modelo") from exc
        except anthropic.RateLimitError as exc:
            raise VisionError("Claude limitó las peticiones; reintenta en un minuto") from exc
        except anthropic.BadRequestError as exc:
            if "credit" in str(exc).lower():
                raise VisionError("Tu cuenta de la API de Claude no tiene crédito") from exc
            raise VisionError("Claude rechazó la petición (400)") from exc
        except anthropic.APIStatusError as exc:
            raise VisionError(f"Error de la API de Claude ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise VisionError("Sin conexión con la API de Claude") from exc

        if resp.stop_reason == "refusal":
            raise VisionError("Claude se negó a procesar estas imágenes")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            raise VisionError("Claude no devolvió una respuesta completa")
        usage = Usage(resp.usage.input_tokens, resp.usage.output_tokens)
        log.info("Claude %s: tokens entrada=%s salida=%s", purpose, usage.input_tokens, usage.output_tokens)
        return resp.parsed_output, usage
