"""Perfil de color de una marca y prefiltro de candidatos en una página.

Se trabaja en el espacio Lab, en el plano cromático (a*, b*): el papel queda cerca del
origen y cada tinta de color apunta en una dirección (verde: a* negativo; azul: b*
negativo; rosa: a* positivo). Así se detectan tintas tenues que casi no tienen
saturación, como una firma en verde claro sobre cuadrícula azul.

Cada imagen se "balancea" restando el color mediano del papel, para tolerar fotos
amarillentas o con luz fría.
"""

import math
from dataclasses import asdict, dataclass

import cv2
import numpy as np

MIN_INK_CHROMA = 6.0  # croma mínimo (en unidades Lab) para considerar un píxel como tinta
ANGLE_TOLERANCE_DEG = 35.0
WORK_WIDTH = 1000  # la página se analiza a este ancho; las cajas se regresan en px originales
MAX_CANDIDATES = 4


@dataclass
class ColorProfile:
    """Dirección cromática de la tinta de la marca."""

    da: float  # vector unitario en el plano (a*, b*)
    db: float
    min_projection: float
    angle_tolerance_deg: float
    colored: bool  # False si la tinta es negra/gris: el prefiltro por color no aplica
    ink_pixels: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ColorProfile":
        return cls(**d)


def _to_bgr(img_rgb_or_rgba: np.ndarray) -> np.ndarray:
    if img_rgb_or_rgba.ndim == 3 and img_rgb_or_rgba.shape[2] == 4:
        alpha = img_rgb_or_rgba[:, :, 3:4].astype(np.float32) / 255
        rgb = img_rgb_or_rgba[:, :, :3].astype(np.float32) * alpha + 255 * (1 - alpha)
        img_rgb_or_rgba = rgb.astype(np.uint8)
    return cv2.cvtColor(img_rgb_or_rgba, cv2.COLOR_RGB2BGR)


def _balanced_ab(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    a = lab[:, :, 1] - 128
    b = lab[:, :, 2] - 128
    return a - np.median(a), b - np.median(b)


def profile_from_references(images_rgb: list[np.ndarray]) -> ColorProfile:
    """Calcula el perfil de color a partir de las imágenes de referencia (RGB o RGBA)."""
    vecs = []
    for img in images_rgb:
        a, b = _balanced_ab(_to_bgr(img))
        chroma = np.hypot(a, b)
        ink = chroma >= MIN_INK_CHROMA
        vecs.append(np.stack([a[ink], b[ink]], axis=1))
    ink_ab = np.concatenate(vecs) if vecs else np.zeros((0, 2), np.float32)
    if len(ink_ab) < 20:
        return ColorProfile(0.0, 0.0, 0.0, ANGLE_TOLERANCE_DEG, colored=False, ink_pixels=len(ink_ab))

    mean = ink_ab.mean(axis=0)
    norm = float(np.hypot(*mean))
    if norm < MIN_INK_CHROMA * 0.8:
        # Las tintas no apuntan a una dirección clara (negro, gris o mezcla de colores).
        return ColorProfile(0.0, 0.0, 0.0, ANGLE_TOLERANCE_DEG, colored=False, ink_pixels=len(ink_ab))
    da, db = float(mean[0] / norm), float(mean[1] / norm)
    proj = ink_ab @ np.array([da, db])
    # Umbral por debajo de la tinta típica de la referencia, sin bajar del mínimo.
    min_proj = float(max(MIN_INK_CHROMA, np.percentile(proj, 25) * 0.6))
    return ColorProfile(da, db, min_proj, ANGLE_TOLERANCE_DEG, colored=True, ink_pixels=len(ink_ab))


def ink_mask(bgr: np.ndarray, profile: ColorProfile) -> np.ndarray:
    """Máscara booleana de los píxeles con la tinta del perfil."""
    a, b = _balanced_ab(bgr)
    proj = a * profile.da + b * profile.db
    perp = np.abs(-a * profile.db + b * profile.da)
    tan = math.tan(math.radians(profile.angle_tolerance_deg))
    return (proj >= profile.min_projection) & (perp <= proj * tan)


@dataclass
class Candidate:
    x0: int
    y0: int
    x1: int
    y1: int
    ink_pixels: int

    def padded(self, width: int, height: int, pad_ratio: float = 0.2, min_size: int = 160):
        w, h = self.x1 - self.x0, self.y1 - self.y0
        px = max(int(w * pad_ratio), (min_size - w) // 2, 0)
        py = max(int(h * pad_ratio), (min_size - h) // 2, 0)
        return (max(0, self.x0 - px), max(0, self.y0 - py), min(width, self.x1 + px), min(height, self.y1 + py))


def _merge(boxes: list[list[int]], gap: int) -> list[list[int]]:
    merged = True
    while merged:
        merged = False
        out: list[list[int]] = []
        for b in boxes:
            for m in out:
                if b[0] <= m[2] + gap and m[0] <= b[2] + gap and b[1] <= m[3] + gap and m[1] <= b[3] + gap:
                    m[0], m[1] = min(m[0], b[0]), min(m[1], b[1])
                    m[2], m[3] = max(m[2], b[2]), max(m[3], b[3])
                    m[4] += b[4]
                    merged = True
                    break
            else:
                out.append(list(b))
        boxes = out
    return boxes


def find_candidates(page_rgb: np.ndarray, profile: ColorProfile) -> list[Candidate]:
    """Zonas de la página con la tinta de la marca, de mayor a menor cantidad de tinta."""
    if not profile.colored:
        return []
    h0, w0 = page_rgb.shape[:2]
    scale = WORK_WIDTH / w0 if w0 > WORK_WIDTH else 1.0
    img = cv2.resize(page_rgb, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else page_rgb
    bgr = _to_bgr(img)
    mask = ink_mask(bgr, profile).astype(np.uint8)
    # Quita puntos sueltos (ruido de compresión) y une los trazos de una misma firma.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    joined = cv2.dilate(mask, np.ones((15, 15), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    h, w = mask.shape
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, _ = stats[i]
        ink = int(mask[labels == i].sum())
        if ink < 40 or max(bw, bh) < 25:
            continue
        boxes.append([x, y, x + bw, y + bh, ink])
    boxes = _merge(boxes, gap=int(0.03 * w))
    page_area = w * h
    result = []
    for x0, y0, x1, y1, ink in sorted(boxes, key=lambda b: -b[4]):
        if (x1 - x0) * (y1 - y0) > 0.3 * page_area:
            continue  # demasiado grande para ser una firma o sello (p. ej. toda la hoja en verde)
        result.append(
            Candidate(int(x0 / scale), int(y0 / scale), int(x1 / scale), int(y1 / scale), ink)
        )
        if len(result) == MAX_CANDIDATES:
            break
    return result
