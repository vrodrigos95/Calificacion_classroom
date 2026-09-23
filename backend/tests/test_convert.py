import io

import pytest
from PIL import Image

from app.imaging.convert import MAX_SIDE, UnsupportedFile, to_pages
from tests.helpers import PRIVATE, jpeg_bytes, pdf_bytes, sheet_image


def _open(page):
    return Image.open(io.BytesIO(page.jpeg))


def test_pdf_becomes_one_image_per_page():
    pages = to_pages(pdf_bytes(3), "application/pdf")
    assert len(pages) == 3
    for p in pages:
        img = _open(p)
        assert img.format == "JPEG" and img.mode == "RGB"
        assert img.height > img.width  # vertical, como la hoja
        assert max(img.size) <= MAX_SIDE


def test_pdf_detected_by_content_even_without_mime():
    assert len(to_pages(pdf_bytes(1), "")) == 1


def test_exif_rotation_is_applied():
    # Foto guardada "acostada" con orientación EXIF 6 (girar 90°): debe quedar vertical.
    landscape = sheet_image(size=(1600, 1200))
    page = to_pages(jpeg_bytes(landscape, exif_orientation=6), "image/jpeg")[0]
    assert (page.width, page.height) == (1200, 1600)


def test_big_photo_is_downscaled():
    page = to_pages(jpeg_bytes(sheet_image(size=(3000, 4000))), "image/jpeg")[0]
    assert max(page.width, page.height) == MAX_SIDE


def test_transparent_png_gets_white_background():
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = _open(to_pages(buf.getvalue(), "image/png")[0])
    assert out.getpixel((50, 50))[0] > 240


@pytest.mark.parametrize(
    "data,msg",
    [
        (b"", "vacío"),
        (b"no soy una imagen", "Formato no soportado"),
        (b"%PDF-1.4 roto", "PDF dañado"),
    ],
)
def test_bad_files_raise_clear_errors(data, msg):
    with pytest.raises(UnsupportedFile, match=msg):
        to_pages(data, "application/octet-stream")


def test_password_pdf_is_rejected():
    with pytest.raises(UnsupportedFile, match="contraseña"):
        to_pages(pdf_bytes(1, password="x"), "application/pdf")


@pytest.mark.skipif(not (PRIVATE / "entrega_firmada.webp").exists(), reason="sin archivo real")
def test_real_student_sheet_webp():
    data = (PRIVATE / "entrega_firmada.webp").read_bytes()
    pages = to_pages(data, "image/webp")
    assert len(pages) == 1
    img = _open(pages[0])
    assert img.height > img.width
    # La tinta verde de la firma sobrevive a la conversión (esquina superior derecha).
    w, h = img.size
    region = img.crop((int(w * 0.75), int(h * 0.12), int(w * 0.95), int(h * 0.22)))
    greens = sum(1 for r, g, b in region.get_flattened_data() if g > r + 25 and g > b + 10)
    assert greens > 50
