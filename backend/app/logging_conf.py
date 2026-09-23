"""Logging sin datos de alumnos.

Regla: el código registra solo IDs internos. Este filtro es una red de seguridad que
enmascara correos y nombres de alumnos que se hayan registrado en el proceso.
"""

import logging
import re
import threading

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class RedactionFilter(logging.Filter):
    _lock = threading.Lock()
    _names: set[str] = set()

    @classmethod
    def register_sensitive(cls, *values: str) -> None:
        with cls._lock:
            cls._names.update(v for v in values if v and len(v) >= 3)

    @classmethod
    def redact(cls, text: str) -> str:
        text = _EMAIL_RE.sub("[correo]", text)
        with cls._lock:
            names = sorted(cls._names, key=len, reverse=True)
        for name in names:
            if name in text:
                text = text.replace(name, "[alumno]")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = self.redact(record.getMessage()), None
        # Los tracebacks también pueden llevar nombres (p. ej. en el nombre de un archivo).
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        return True


def build_handler(stream=None) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactionFilter())
    return handler


def setup_logging(level: str = "INFO") -> None:
    handler = build_handler()
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # googleapiclient registra URLs con IDs de Google; no aportan y pueden ser ruido.
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
