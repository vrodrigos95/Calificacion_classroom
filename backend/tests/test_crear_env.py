import importlib.util
from pathlib import Path

from cryptography.fernet import Fernet

spec = importlib.util.spec_from_file_location(
    "crear_env", Path(__file__).parent.parent / "scripts" / "crear_env.py"
)
crear_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crear_env)

TEMPLATE = """# comentario
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
# python -c "..."
SESSION_SECRET=
TOKEN_ENCRYPTION_KEY=
RETENTION_DAYS=14
"""


def _values(text):
    return dict(l.split("=", 1) for l in text.splitlines() if "=" in l and not l.startswith("#"))


def test_generates_missing_secrets_and_reports_google_values():
    text, generated, missing = crear_env.fill(TEMPLATE)
    v = _values(text)
    assert set(generated) == {"SESSION_SECRET", "TOKEN_ENCRYPTION_KEY"}
    assert len(v["SESSION_SECRET"]) > 40
    Fernet(v["TOKEN_ENCRYPTION_KEY"].encode())  # clave Fernet válida
    assert missing == ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]
    assert v["RETENTION_DAYS"] == "14" and "# comentario" in text


def test_never_replaces_existing_keys():
    filled = TEMPLATE.replace("TOKEN_ENCRYPTION_KEY=", "TOKEN_ENCRYPTION_KEY=clave-vieja").replace(
        "GOOGLE_CLIENT_ID=", "GOOGLE_CLIENT_ID=abc"
    ).replace("GOOGLE_CLIENT_SECRET=", "GOOGLE_CLIENT_SECRET=xyz")
    text, generated, missing = crear_env.fill(filled)
    assert _values(text)["TOKEN_ENCRYPTION_KEY"] == "clave-vieja"
    assert generated == ["SESSION_SECRET"] and missing == []
    # Idempotente: una segunda pasada no cambia nada.
    assert crear_env.fill(text)[0] == text
