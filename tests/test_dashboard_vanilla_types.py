from __future__ import annotations

from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FOLDERS = {
    "chernarus": "dayzOffline.chernarusplus",
    "livonia": "dayzOffline.enoch",
    "sakhal": "dayzOffline.sakhal",
}


class DashboardVanillaTypesTests(unittest.TestCase):
    def test_factory_types_files_are_available_for_supported_maps(self):
        for map_key, folder in REFERENCE_FOLDERS.items():
            with self.subTest(map_key=map_key):
                types_path = REPO_ROOT / "dayz_reference" / folder / "db" / "types.xml"
                root = ET.fromstring(types_path.read_text(encoding="utf-8", errors="ignore"))

                self.assertEqual("types", root.tag)
                self.assertGreater(len(root.findall(".//type")), 1000)

    def test_factory_map_cards_have_html_fallback_links(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertNotRegex(source, re.compile(r"<button[^>]+data-types-load-factory"))
        self.assertNotRegex(source, re.compile(r"<button[^>]+data-types-download-factory"))
        for map_key in REFERENCE_FOLDERS:
            with self.subTest(map_key=map_key):
                self.assertIn(f"factory_map={map_key}", source)
                self.assertIn(f"/api/admin/vanilla-types/download?map={map_key}", source)
                self.assertIn(f'data-types-load-factory data-map-key="{map_key}"', source)

    def test_factory_vanilla_download_and_preload_paths_are_wired(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn("def factory_vanilla_types_payload", source)
        self.assertIn('@APP.get("/api/admin/vanilla-types/download")', source)
        self.assertIn("types_factory_preload = factory_vanilla_types_payload", source)
        self.assertIn('data-types-preload>{{ types_factory_preload|tojson }}</script>', source)

    def test_types_editor_exposes_full_xml_copy_and_view_controls(self):
        source = (REPO_ROOT / "dashboard.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('data-tool-copy="generated_xml">Copy XML</button>', source)
        self.assertIn('data-types-show-xml>View XML</a>', source)
        self.assertIn('id="types-xml-output" data-types-xml-panel', source)
        self.assertIn("panel.open = true", source)


if __name__ == "__main__":
    unittest.main()
