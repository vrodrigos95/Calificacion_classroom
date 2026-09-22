import logging

from app.logging_conf import RedactionFilter


def test_redaction_masks_emails_and_registered_names():
    RedactionFilter.register_sensitive("Ana Zúñiga")
    rec = logging.LogRecord(
        "x", logging.INFO, "f", 1, "Entrega de %s (%s) falló", ("Ana Zúñiga", "ana@x.mx"), None
    )
    RedactionFilter().filter(rec)
    assert rec.getMessage() == "Entrega de [alumno] ([correo]) falló"
