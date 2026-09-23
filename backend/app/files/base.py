"""Acceso a los archivos entregados, aislado para poder cambiar de fuente.

v1: DriveReadonlySource (scope drive.readonly, solo modo prueba).
Después: carga de ZIP, o drive.file con Google Picker, implementando el mismo protocolo.
"""

from dataclasses import dataclass
from typing import Protocol


class FileFetchError(RuntimeError):
    """El archivo no se pudo obtener (permiso, no existe, demasiado grande…)."""


@dataclass
class FetchedFile:
    file_id: str
    name: str
    mime_type: str
    data: bytes


class FileSource(Protocol):
    def fetch(self, file_id: str) -> FetchedFile: ...
