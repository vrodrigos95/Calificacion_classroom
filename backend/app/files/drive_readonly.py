"""FileSource sobre Google Drive con el scope drive.readonly."""

import io
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.files.base import FetchedFile, FileFetchError

MAX_BYTES = 50 * 1024 * 1024
GOOGLE_APPS_PREFIX = "application/vnd.google-apps."


def build_drive_service(credentials: Credentials):
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


class DriveReadonlySource:
    def __init__(self, service: Any):
        self.svc = service

    def _download(self, request) -> bytes:
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
            if buf.tell() > MAX_BYTES:
                raise FileFetchError("Archivo demasiado grande (más de 50 MB)")
        return buf.getvalue()

    def fetch(self, file_id: str) -> FetchedFile:
        try:
            meta = (
                self.svc.files()
                .get(fileId=file_id, fields="id,name,mimeType,size", supportsAllDrives=True)
                .execute()
            )
            mime = meta.get("mimeType", "")
            if int(meta.get("size") or 0) > MAX_BYTES:
                raise FileFetchError("Archivo demasiado grande (más de 50 MB)")
            if mime.startswith(GOOGLE_APPS_PREFIX):
                # Documentos de Google (Docs, Slides…): se exportan a PDF.
                request = self.svc.files().export_media(fileId=file_id, mimeType="application/pdf")
                mime = "application/pdf"
            else:
                request = self.svc.files().get_media(fileId=file_id, supportsAllDrives=True)
            data = self._download(request)
        except HttpError as exc:
            status = exc.resp.status if exc.resp is not None else 0
            reason = {
                403: "Sin permiso para leer el archivo en Drive",
                404: "El archivo ya no existe en Drive",
            }.get(status, f"Error de Drive ({status})")
            raise FileFetchError(reason) from exc
        return FetchedFile(file_id=file_id, name=meta.get("name", ""), mime_type=mime, data=data)
