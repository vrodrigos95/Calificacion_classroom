from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class TokenCryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        raise TokenCryptoError("Falta TOKEN_ENCRYPTION_KEY en el entorno")
    return Fernet(key.encode())


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(value: bytes) -> str:
    try:
        return _fernet().decrypt(value).decode()
    except InvalidToken as exc:
        raise TokenCryptoError("No se pudo descifrar el token (¿cambió la clave?)") from exc
