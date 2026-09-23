"""DriveReadonlySource contra el cliente real de googleapiclient con respuestas HTTP simuladas."""

import json

import pytest
from googleapiclient.discovery import build
from googleapiclient.http import HttpMockSequence

from app.files.base import FileFetchError
from app.files.drive_readonly import DriveReadonlySource
from tests.helpers import pdf_bytes


def _service(responses):
    http = HttpMockSequence(responses)
    return build("drive", "v3", http=http, static_discovery=True), http


def test_downloads_binary_file():
    pdf = pdf_bytes(1)
    svc, http = _service(
        [
            ({"status": "200"}, json.dumps({"id": "f1", "name": "tarea.pdf", "mimeType": "application/pdf", "size": str(len(pdf))})),
            ({"status": "200", "content-range": f"bytes 0-{len(pdf) - 1}/{len(pdf)}"}, pdf),
        ]
    )
    f = DriveReadonlySource(svc).fetch("f1")
    assert f.data == pdf and f.mime_type == "application/pdf" and f.name == "tarea.pdf"
    # get_media pide el contenido con alt=media
    assert "alt=media" in http.request_sequence[1][0]


def test_google_doc_is_exported_as_pdf():
    pdf = pdf_bytes(1)
    svc, http = _service(
        [
            ({"status": "200"}, json.dumps({"id": "d1", "name": "Tarea", "mimeType": "application/vnd.google-apps.document"})),
            ({"status": "200"}, pdf),
        ]
    )
    f = DriveReadonlySource(svc).fetch("d1")
    assert f.mime_type == "application/pdf"
    assert "/export" in http.request_sequence[1][0]


@pytest.mark.parametrize("status,msg", [("404", "ya no existe"), ("403", "Sin permiso")])
def test_http_errors_become_clear_messages(status, msg):
    svc, _ = _service([({"status": status}, json.dumps({"error": {"message": "x"}}))])
    with pytest.raises(FileFetchError, match=msg):
        DriveReadonlySource(svc).fetch("f1")


def test_too_big_file_is_rejected_before_download():
    svc, _ = _service(
        [({"status": "200"}, json.dumps({"id": "f1", "name": "x.pdf", "mimeType": "application/pdf", "size": str(200 * 1024 * 1024)}))]
    )
    with pytest.raises(FileFetchError, match="demasiado grande"):
        DriveReadonlySource(svc).fetch("f1")
