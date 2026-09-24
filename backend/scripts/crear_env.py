"""Crea o completa backend/.env a partir de .env.example.

- Si backend/.env no existe, lo copia de la plantilla.
- Genera SESSION_SECRET y TOKEN_ENCRYPTION_KEY solo si están vacías. Nunca reemplaza
  una clave existente: cambiar TOKEN_ENCRYPTION_KEY obligaría a iniciar sesión de nuevo.
- Avisa qué valores faltan por llenar a mano (los de Google Cloud).

Uso (desde la carpeta backend, con el entorno activado):  python scripts/crear_env.py
"""

import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND = Path(__file__).resolve().parent.parent
ENV = BACKEND / ".env"
TEMPLATE = BACKEND.parent / ".env.example"

GENERATED = {
    "SESSION_SECRET": lambda: secrets.token_urlsafe(48),
    "TOKEN_ENCRYPTION_KEY": lambda: Fernet.generate_key().decode(),
}
REQUIRED_BY_HAND = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]


def fill(text: str) -> tuple[str, list[str], list[str]]:
    """Devuelve (texto nuevo, claves generadas, claves que faltan a mano)."""
    lines, generated, values = [], [], {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and not line.lstrip().startswith("#"):
            if key in GENERATED and not value.strip():
                value = GENERATED[key]()
                line = f"{key}={value}"
                generated.append(key)
            values[key] = value.strip()
        lines.append(line)
    missing = [k for k in REQUIRED_BY_HAND if not values.get(k)]
    return "\n".join(lines) + "\n", generated, missing


def main() -> int:
    if not ENV.exists():
        if not TEMPLATE.exists():
            print(f"No encuentro la plantilla {TEMPLATE}")
            return 1
        ENV.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Creado {ENV}")
    new_text, generated, missing = fill(ENV.read_text(encoding="utf-8"))
    ENV.write_text(new_text, encoding="utf-8")
    for key in generated:
        print(f"Generada {key}")
    if missing:
        print("Faltan por llenar en backend\\.env: " + ", ".join(missing))
        print("  (los copias de Google Cloud > Google Auth Platform > Clientes)")
    else:
        print("backend\\.env listo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
