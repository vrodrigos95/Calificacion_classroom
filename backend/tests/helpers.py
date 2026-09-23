"""Generadores de archivos de prueba (sin datos reales)."""

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw

PRIVATE = Path(__file__).parent / "fixtures_private"


def sheet_image(size=(1200, 1600), color=(250, 250, 245)) -> Image.Image:
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    for y in range(100, size[1], 60):
        d.line([(50, y), (size[0] - 50, y)], fill=(180, 180, 220), width=2)
    d.text((80, 120), "1. P(A) = 2/6 = 33%", fill=(20, 20, 20))
    return img


def jpeg_bytes(img: Image.Image, exif_orientation: int | None = None) -> bytes:
    buf = io.BytesIO()
    if exif_orientation:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def pdf_bytes(pages: int = 2, password: str | None = None) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)  # A4 en puntos
        buf = io.BytesIO()
        sheet_image().save(buf, "PNG")
        page.insert_image(page.rect, stream=buf.getvalue())
        page.insert_text((72, 72), f"Hoja {i + 1}")
    kwargs = {}
    if password:
        kwargs = dict(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    data = doc.tobytes(**kwargs)
    doc.close()
    return data
