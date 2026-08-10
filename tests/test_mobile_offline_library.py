import hashlib
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"
WEB = MOBILE / "web"


class MobileOfflineLibraryTests(unittest.TestCase):
    def test_capacitor_starts_from_packaged_app_not_remote_server(self):
        config = json.loads((MOBILE / "capacitor.config.json").read_text(encoding="utf-8"))
        self.assertNotIn("url", config.get("server", {}))
        self.assertEqual("web", config["webDir"])

    def test_offline_libraries_match_reviewed_sources(self):
        for filename in (
            "dayz_crafting_library.json",
            "dayz_illness_library.json",
            "dayz_file_guide_library.json",
            "dayz_tier_guide.json",
        ):
            source = ROOT / filename
            bundled = WEB / "data" / filename
            self.assertTrue(bundled.is_file(), filename)
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).digest(),
                hashlib.sha256(bundled.read_bytes()).digest(),
                filename,
            )

    def test_offline_tier_maps_are_bundled(self):
        for filename in ("chernarus.webp", "livonia.webp", "sakhal.webp"):
            source = ROOT / "tier_maps" / filename
            bundled = WEB / "data" / "tier_maps" / filename
            self.assertTrue(bundled.is_file(), filename)
            self.assertEqual(source.stat().st_size, bundled.stat().st_size)

    def test_mobile_shell_separates_offline_guides_from_online_controls(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        script = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn("Works offline", html)
        self.assertIn("Online only", html)
        self.assertIn("Crafting", html)
        self.assertIn("Illnesses & treatment", script)
        self.assertIn("DayZ files explained", script)
        self.assertIn("Loot tiers & maps", script)
        self.assertIn("navigator.onLine", script)
        self.assertNotIn("window.location.replace", script)
        self.assertIn("open-dashboard", html)


if __name__ == "__main__":
    unittest.main()
