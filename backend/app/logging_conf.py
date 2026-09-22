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

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        msg = _EMAIL_RE.sub("[correo]", msg)
        with self._lock:
            names = sorted(self._names, key=len, reverse=True)
        for name in names:
            if name in msg:
                msg = msg.replace(name, "[alumno]")
        record.msg, record.args = msg, None
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # googleapiclient registra URLs con IDs de Google; no aportan y pueden ser ruido.
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
