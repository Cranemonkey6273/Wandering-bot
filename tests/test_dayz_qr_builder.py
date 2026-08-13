from __future__ import annotations

import io
import json
import math
import os
import sys
import unittest
import zipfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import dashboard  # noqa: E402
from dayz_file_intelligence import validate_dayz_upload_text  # noqa: E402
from dayz_qr_builder import (  # noqa: E402
    DayZQRBuilderError,
    QR_FRAME_TEMPLATE_FILE,
    QR_PIXEL_CLASS,
    QR_SIZE,
    QR_TEMPLATE_ANCHOR,
    QR_TEMPLATE_COLUMN_STEP,
    QR_TEMPLATE_HEADING,
    QR_TEMPLATE_ROW_STEP,
    QR_TEMPLATE_TOP_LEFT,
    build_dayz_qr_scene,
)


class DayZQRBuilderTests(unittest.TestCase):
    URL = "https://discord.gg/aQ4r9XSn2T"
    OWNER_SOURCE_FILE = r"C:\Users\Crane\Documents\DayZ\Editor\Missions\ChernoQR1NWAF.json"

    def test_supplied_mission_frame_and_grid_geometry_decode_as_proven_source(self):
        if not os.path.isfile(self.OWNER_SOURCE_FILE):
            self.skipTest("Owner source mission is not present on this test host")
        try:
            import cv2
            import numpy as np
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("OpenCV and Pillow are optional source-forensics dependencies")
        with open(self.OWNER_SOURCE_FILE, "r", encoding="utf-8-sig") as handle:
            source_objects = json.load(handle)["Objects"]
        source_pixels = [row for row in source_objects if row.get("name") == QR_PIXEL_CLASS]
        matrix = [[False] * QR_SIZE for _ in range(QR_SIZE)]
        top_left = QR_TEMPLATE_TOP_LEFT
        column_length = QR_TEMPLATE_COLUMN_STEP[0] ** 2 + QR_TEMPLATE_COLUMN_STEP[2] ** 2
        for item in source_pixels:
            x, y, z = map(float, item["pos"])
            row_index = round((y - top_left[1]) / QR_TEMPLATE_ROW_STEP[1])
            column_index = round(
                ((x - top_left[0]) * QR_TEMPLATE_COLUMN_STEP[0]
                 + (z - top_left[2]) * QR_TEMPLATE_COLUMN_STEP[2]) / column_length
            )
            self.assertTrue(0 <= row_index < QR_SIZE and 0 <= column_index < QR_SIZE)
            matrix[row_index][column_index] = True
        self.assertEqual(429, len(source_pixels))
        self.assertEqual(429, sum(sum(row) for row in matrix))
        border, cell = 4, 16
        image = Image.new("RGB", ((QR_SIZE + border * 2) * cell,) * 2, "white")
        draw = ImageDraw.Draw(image)
        for row_index, row in enumerate(matrix):
            for column_index, enabled in enumerate(row):
                if enabled:
                    left = (column_index + border) * cell
                    top = (row_index + border) * cell
                    draw.rectangle((left, top, left + cell - 1, top + cell - 1), fill="black")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        decoded, points, _straight = cv2.QRCodeDetector().detectAndDecode(
            cv2.imdecode(np.frombuffer(buffer.getvalue(), np.uint8), cv2.IMREAD_GRAYSCALE)
        )
        self.assertIsNotNone(points)
        self.assertEqual("https://discord.gg/HqQBuBdKNV", decoded)

    def test_base_heading_preserves_every_proven_frame_object_exactly(self):
        with open(QR_FRAME_TEMPLATE_FILE, "r", encoding="utf-8") as handle:
            original_frame = json.load(handle)["Objects"]
        result = build_dayz_qr_scene(
            self.URL,
            "SupportQR",
            *QR_TEMPLATE_ANCHOR,
            QR_TEMPLATE_HEADING,
        )
        self.assertEqual(29, result["frame_object_count"])
        self.assertEqual(original_frame, result["scene"]["Objects"][:29])
        self.assertTrue(all(obj["name"] != QR_PIXEL_CLASS for obj in original_frame))

    def test_emits_only_dark_modules_and_valid_dayz_json(self):
        result = build_dayz_qr_scene(self.URL, "SupportQR", 13030.0439, 16.015965, 14046.6679, 180)
        dark_modules = sum(1 for row in result["matrix"] for enabled in row if enabled)
        self.assertEqual(QR_SIZE, len(result["matrix"]))
        self.assertTrue(all(len(row) == QR_SIZE for row in result["matrix"]))
        self.assertEqual(dark_modules, result["pixel_object_count"])
        self.assertEqual(29 + dark_modules, result["total_object_count"])
        self.assertLess(dark_modules, QR_SIZE * QR_SIZE)
        self.assertTrue(all(obj["name"] == QR_PIXEL_CLASS for obj in result["scene"]["Objects"][29:]))
        self.assertEqual((True, ""), validate_dayz_upload_text(
            "./custom/SupportQR.json",
            json.dumps(result["scene"]),
        ))
        self.assertTrue(result["preview_png"].startswith(b"\x89PNG\r\n\x1a\n"))

    def test_independent_scanner_decodes_exact_support_url_when_available(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV is an optional independent QA dependency")
        result = build_dayz_qr_scene(self.URL, "ScannerQA", 1, 2, 3, 0)
        image = cv2.imdecode(np.frombuffer(result["preview_png"], np.uint8), cv2.IMREAD_GRAYSCALE)
        decoded, points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
        self.assertIsNotNone(points)
        self.assertEqual(self.URL, decoded)

    def test_rigid_move_and_rotation_preserve_frame_geometry(self):
        base = build_dayz_qr_scene(self.URL, "Base", *QR_TEMPLATE_ANCHOR, QR_TEMPLATE_HEADING)
        moved = build_dayz_qr_scene(self.URL, "Moved", 1000, 50, 2000, QR_TEMPLATE_HEADING + 90)
        for left, right in zip(base["scene"]["Objects"][:29], moved["scene"]["Objects"][:29]):
            base_distance = math.hypot(
                left["pos"][0] - QR_TEMPLATE_ANCHOR[0],
                left["pos"][2] - QR_TEMPLATE_ANCHOR[2],
            )
            moved_distance = math.hypot(right["pos"][0] - 1000, right["pos"][2] - 2000)
            self.assertAlmostEqual(base_distance, moved_distance, places=8)
            self.assertAlmostEqual(left["pos"][1] - QR_TEMPLATE_ANCHOR[1], right["pos"][1] - 50, places=8)
            self.assertAlmostEqual(float(left["ypr"][0]) + 90, float(right["ypr"][0]), places=8)

    def test_rejects_invalid_and_oversized_links(self):
        with self.assertRaisesRegex(DayZQRBuilderError, "complete http"):
            build_dayz_qr_scene("discord.gg/no-scheme", "Bad", 1, 2, 3, 0)
        with self.assertRaisesRegex(DayZQRBuilderError, "too long"):
            build_dayz_qr_scene("https://example.com/" + ("a" * 400), "TooLong", 1, 2, 3, 0)

    def test_pro_and_ultimate_have_qr_entitlement_but_basic_does_not(self):
        plans = {row["id"]: row for row in dashboard.DEFAULT_BILLING_PLANS}
        self.assertFalse(bool(plans["dashboard"]["features"].get("qr_builder")))
        self.assertTrue(plans["dashboard_ai"]["features"]["qr_builder"])
        self.assertTrue(plans["dashboard_ultimate"]["features"]["qr_builder"])
        self.assertIn("/api/admin/qr-code-generate", dashboard.ADMIN_ROUTE_FEATURES)
        self.assertEqual("qr_builder", dashboard.ADMIN_ROUTE_FEATURES["/api/admin/qr-code-generate"])

    def test_download_route_returns_valid_package_for_owner(self):
        original_auth = dashboard.current_auth
        dashboard.current_auth = lambda: {"kind": "owner", "user_id": "qr-test-owner"}
        try:
            client = dashboard.APP.test_client()
            response = client.post("/api/admin/qr-code-generate", data={
                "dashboard_mode": "owner",
                "url": self.URL,
                "name": "SupportQR",
                "x": "13030.0439",
                "y": "16.015965",
                "z": "14046.6679",
                "heading": "180",
            })
        finally:
            dashboard.current_auth = original_auth
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/zip", response.mimetype)
        with zipfile.ZipFile(io.BytesIO(response.data), "r") as archive:
            names = set(archive.namelist())
            self.assertEqual(
                {"SupportQR.json", "SupportQR-preview.png", "SupportQR-manifest.json", "README.txt"},
                names,
            )
            scene_text = archive.read("SupportQR.json").decode("utf-8")
            manifest = json.loads(archive.read("SupportQR-manifest.json"))
            self.assertEqual((True, ""), validate_dayz_upload_text("./custom/SupportQR.json", scene_text))
            self.assertTrue(manifest["validation"]["ok"])
            self.assertEqual("./custom/SupportQR.json", manifest["custom_path"])
            self.assertIn("WorldsData.objectSpawnersArr", archive.read("README.txt").decode("utf-8"))

    def test_owner_dashboard_renders_generator_instead_of_upgrade_card(self):
        original_auth = dashboard.current_auth
        dashboard.current_auth = lambda: {"kind": "owner", "user_id": "qr-ui-owner"}
        try:
            response = dashboard.APP.test_client().get(
                "/admin?section=xml-workshop&xml_tool=qr-code"
            )
        finally:
            dashboard.current_auth = original_auth
        self.assertEqual(200, response.status_code)
        self.assertIn(b'id="qr-code-builder"', response.data)
        self.assertIn(b"Generate Validated QR Package", response.data)
        self.assertIn(b'action="/api/admin/qr-code-generate" data-html-submit="true"', response.data)
        self.assertIn(b'name="dashboard_mode" value="owner"', response.data)
        self.assertNotIn(b"Compare plans", response.data)


if __name__ == "__main__":
    unittest.main()
