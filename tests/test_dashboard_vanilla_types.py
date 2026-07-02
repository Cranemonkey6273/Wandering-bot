from __future__ import annotations

from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
