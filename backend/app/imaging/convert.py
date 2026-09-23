"""Convierte archivos entregados (PDF o imagen) a páginas JPEG normalizadas.

- PDF: una imagen por página, renderizada a PDF_DPI.
- Imagen (JPG, PNG, WEBP, HEIC…): corrige la rotación EXIF de la cámara.
- Todas: RGB, lado mayor limitado a MAX_SIDE px (legibilidad de manuscrito sin
  archivos enormes). El reescalado final para el modelo se hace al enviar.
"""

import io
from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageOps

try:  # fotos de iPhone
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pass

PDF_DPI = 200
MAX_SIDE = 2400
JPEG_QUALITY = 90
MAX_PAGES_PER_FILE = 30  # una tarea no debería tener más; protege contra PDFs gigantes

# Evita "bombas de descompresión" pero admite fotos de celular de 50 MP.
Image.MAX_IMAGE_PIXELS = 60_000_000


class UnsupportedFile(ValueError):
    pass


@dataclass
class PageImage:
    jpeg: bytes
    width: int
    height: int


def _finish(img: Image.Image) -> PageImage:
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        # Transparencia (PNG) sobre blanco, como una hoja.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return PageImage(buf.getvalue(), img.width, img.height)


def _is_pdf(data: bytes, mime_type: str) -> bool:
    return mime_type == "application/pdf" or data[:5] == b"%PDF-"


def to_pages(data: bytes, mime_type: str = "") -> list[PageImage]:
    """Convierte el contenido de un archivo en páginas. Lanza UnsupportedFile si no se puede."""
    if not data:
        raise UnsupportedFile("El archivo está vacío")

    if _is_pdf(data, mime_type):
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise UnsupportedFile("PDF dañado o protegido") from exc
        with doc:
            if doc.needs_pass:
                raise UnsupportedFile("PDF protegido con contraseña")
            if doc.page_count == 0:
                raise UnsupportedFile("PDF sin páginas")
            if doc.page_count > MAX_PAGES_PER_FILE:
                raise UnsupportedFile(f"PDF con demasiadas páginas ({doc.page_count})")
            pages = []
            for page in doc:
                pix = page.get_pixmap(dpi=PDF_DPI, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pages.append(_finish(img))
            return pages

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise UnsupportedFile(f"Formato no soportado ({mime_type or 'desconocido'})") from exc
    return [_finish(img)]
