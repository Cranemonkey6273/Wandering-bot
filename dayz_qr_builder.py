"""Deterministic DayZ ObjectSpawner QR builds.

The fixed frame is the proven low-object construction supplied by the owner.
Only dark QR modules are emitted, keeping the generated scene compact.
"""

from __future__ import annotations

import copy
import io
import json
import math
import os
import re
import urllib.parse
from typing import Any


QR_VERSION = 3
QR_SIZE = 29
QR_PIXEL_CLASS = "StaticObj_Misc_BoxWooden"
QR_PIXEL_YPR = [-105.99520111083984, 0.0, -0.0]
QR_PIXEL_SCALE = 0.049997858703136444
QR_TEMPLATE_ANCHOR = [4248.76416015625, 338.9676818847656, 10621.2783203125]
QR_TEMPLATE_HEADING = -106.53050231933594
QR_TEMPLATE_TOP_LEFT = [4248.98388671875, 340.07586669921875, 10620.755859375]
QR_TEMPLATE_COLUMN_STEP = [-0.013671875, 0.0, 0.0380859375]
QR_TEMPLATE_ROW_STEP = [0.0, -0.04046412876674107, 0.0]
QR_FRAME_TEMPLATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qr_frame_template.json")


class DayZQRBuilderError(ValueError):
    """Raised when an input cannot produce the proven 29x29 DayZ build."""


def safe_qr_name(value: Any) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_-")
    if not name:
        raise DayZQRBuilderError("Enter a unique QR name using letters, numbers, hyphens or underscores.")
    return name[:64]


def validate_qr_url(value: Any) -> str:
    url = str(value or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DayZQRBuilderError("Enter a complete http:// or https:// URL.")
    return url


def _qr_matrix(url: str) -> list[list[bool]]:
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
        from qrcode.exceptions import DataOverflowError
    except ImportError as error:  # pragma: no cover - deployment dependency guard
        raise DayZQRBuilderError("QR generation support is not installed on this deployment.") from error

    qr = qrcode.QRCode(
        version=QR_VERSION,
        error_correction=ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(url, optimize=0)
    try:
        qr.make(fit=False)
    except DataOverflowError as error:
        raise DayZQRBuilderError(
            "That URL is too long for the proven low-object 29x29 frame. Use a shorter direct URL or a trusted short link."
        ) from error
    matrix = [[bool(cell) for cell in row] for row in qr.get_matrix()]
    border = int(qr.border)
    matrix = [row[border:-border] for row in matrix[border:-border]]
    if len(matrix) != QR_SIZE or any(len(row) != QR_SIZE for row in matrix):
        raise DayZQRBuilderError("The URL did not produce the required 29x29 QR layout.")
    return matrix


def _load_frame_objects() -> list[dict[str, Any]]:
    try:
        with open(QR_FRAME_TEMPLATE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise DayZQRBuilderError("The proven QR frame template is unavailable or invalid.") from error
    objects = payload.get("Objects") if isinstance(payload, dict) else None
    if not isinstance(objects, list) or len(objects) != 29:
        raise DayZQRBuilderError("The proven QR frame template failed its 29-object integrity check.")
    return [copy.deepcopy(item) for item in objects if isinstance(item, dict)]


def _compass_rotate(dx: float, dz: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (dx * cosine + dz * sine, -dx * sine + dz * cosine)


def _move_object(
    item: dict[str, Any],
    target: list[float],
    heading_delta: float,
) -> dict[str, Any]:
    moved = copy.deepcopy(item)
    pos = moved.get("pos")
    if not isinstance(pos, list) or len(pos) != 3:
        raise DayZQRBuilderError("The proven QR frame contains an invalid object position.")
    dx = float(pos[0]) - QR_TEMPLATE_ANCHOR[0]
    dy = float(pos[1]) - QR_TEMPLATE_ANCHOR[1]
    dz = float(pos[2]) - QR_TEMPLATE_ANCHOR[2]
    rotated_x, rotated_z = _compass_rotate(dx, dz, heading_delta)
    moved["pos"] = [target[0] + rotated_x, target[1] + dy, target[2] + rotated_z]
    ypr = moved.get("ypr")
    if isinstance(ypr, list) and len(ypr) == 3:
        moved["ypr"] = [float(ypr[0]) + heading_delta, float(ypr[1]), float(ypr[2])]
    return moved


def _pixel_at(row: int, column: int) -> dict[str, Any]:
    return {
        "name": QR_PIXEL_CLASS,
        "pos": [
            QR_TEMPLATE_TOP_LEFT[0] + column * QR_TEMPLATE_COLUMN_STEP[0] + row * QR_TEMPLATE_ROW_STEP[0],
            QR_TEMPLATE_TOP_LEFT[1] + column * QR_TEMPLATE_COLUMN_STEP[1] + row * QR_TEMPLATE_ROW_STEP[1],
            QR_TEMPLATE_TOP_LEFT[2] + column * QR_TEMPLATE_COLUMN_STEP[2] + row * QR_TEMPLATE_ROW_STEP[2],
        ],
        "ypr": list(QR_PIXEL_YPR),
        "scale": QR_PIXEL_SCALE,
        "enableCEPersistency": 0,
        "customString": "",
    }


def render_qr_preview_png(matrix: list[list[bool]]) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError as error:  # pragma: no cover - deployment dependency guard
        raise DayZQRBuilderError("QR preview support is not installed on this deployment.") from error
    border = 4
    cell = 14
    size = (QR_SIZE + border * 2) * cell
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    for row, values in enumerate(matrix):
        for column, enabled in enumerate(values):
            if enabled:
                left = (column + border) * cell
                top = (row + border) * cell
                draw.rectangle((left, top, left + cell - 1, top + cell - 1), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def build_dayz_qr_scene(
    url: Any,
    name: Any,
    x: Any,
    y: Any,
    z: Any,
    heading: Any,
) -> dict[str, Any]:
    clean_url = validate_qr_url(url)
    clean_name = safe_qr_name(name)
    try:
        target = [float(x), float(y), float(z)]
        target_heading = float(heading)
    except (TypeError, ValueError) as error:
        raise DayZQRBuilderError("X, Y, Z and compass heading must be valid numbers.") from error
    if not all(math.isfinite(value) for value in [*target, target_heading]):
        raise DayZQRBuilderError("X, Y, Z and compass heading must be finite numbers.")

    matrix = _qr_matrix(clean_url)
    heading_delta = target_heading - QR_TEMPLATE_HEADING
    frame = [_move_object(item, target, heading_delta) for item in _load_frame_objects()]
    pixels = [
        _move_object(_pixel_at(row, column), target, heading_delta)
        for row, values in enumerate(matrix)
        for column, enabled in enumerate(values)
        if enabled
    ]
    scene = {"Objects": frame + pixels}
    return {
        "name": clean_name,
        "url": clean_url,
        "anchor": target,
        "heading": target_heading,
        "frame_object_count": len(frame),
        "pixel_object_count": len(pixels),
        "total_object_count": len(frame) + len(pixels),
        "matrix": matrix,
        "preview_png": render_qr_preview_png(matrix),
        "scene": scene,
    }
