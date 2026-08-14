import hashlib
import json
import pathlib
import re
import struct
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
        self.assertIn('get("store") === "1"', script)
        self.assertNotIn("window.location.replace", script)
        self.assertIn("open-dashboard", html)
        self.assertIn("open-qr-builder", html)
        self.assertIn("xml_tool=qr-code", script)
        self.assertIn("source=native_android", script)
        self.assertIn("qr-maker-preview.png", html)

    def test_mobile_shell_has_reviewed_offline_language_catalogue(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        script = (WEB / "app.js").read_text(encoding="utf-8")
        translations = (WEB / "translations.js").read_text(encoding="utf-8")

        self.assertIn('id="language-select"', html)
        self.assertIn('src="./translations.js?v=1.0.4"', html)
        self.assertIn("wanderingUiLanguage", script)
        self.assertIn("localStorage.setItem", script)
        self.assertIn("navigator.language", script)
        self.assertIn("document.documentElement.lang", script)
        for language in ("de", "fr", "es", "pl"):
            self.assertIn(f"  {language}: {{", translations)
        for phrase in (
            "Open live dashboard",
            "Browse offline guides",
            "Crafting & building",
            "Illnesses & treatment",
            "DayZ files explained",
            "Loot tiers & maps",
            "Offline guide unavailable",
        ):
            self.assertEqual(4, translations.count(f'"{phrase}"'), phrase)

    def test_every_static_mobile_interface_phrase_has_four_translations(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        script = (WEB / "app.js").read_text(encoding="utf-8")
        translations = (WEB / "translations.js").read_text(encoding="utf-8")
        phrases = set(
            re.findall(
                r'data-i18n(?:-placeholder|-aria-label|-alt)?="([^"]+)"',
                html,
            )
        )
        phrases.update(re.findall(r'\bt\("([^"]+)"', script))
        self.assertGreaterEqual(len(phrases), 45)
        for phrase in phrases:
            self.assertEqual(4, translations.count(f'"{phrase}":'), phrase)

    def test_mobile_qr_preview_matches_the_reviewed_dashboard_example(self):
        source = ROOT / "public_feed_previews" / "qr-maker-finished.png"
        bundled = WEB / "qr-maker-preview.png"
        self.assertTrue(source.is_file())
        self.assertTrue(bundled.is_file())
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).digest(),
            hashlib.sha256(bundled.read_bytes()).digest(),
        )

    def test_play_store_phone_screenshots_are_valid_portrait_rgb_pngs(self):
        screenshot_dir = MOBILE / "store-assets" / "phone"
        expected = {
            "01-home.png",
            "02-crafting.png",
            "03-health.png",
            "04-files.png",
            "05-tiers.png",
            "06-qr-builder.png",
        }
        self.assertEqual(expected, {path.name for path in screenshot_dir.glob("*.png")})
        for filename in expected:
            payload = (screenshot_dir / filename).read_bytes()
            self.assertEqual(b"\x89PNG\r\n\x1a\n", payload[:8], filename)
            width, height = struct.unpack(">II", payload[16:24])
            self.assertGreaterEqual(width, 320, filename)
            self.assertGreater(height, width, filename)
            self.assertLessEqual(height, width * 2, filename)
            self.assertEqual(2, payload[25], f"{filename} must be RGB PNG without alpha")

    def test_translated_mobile_assets_are_copied_into_android_package(self):
        android_public = MOBILE / "android" / "app" / "src" / "main" / "assets" / "public"
        for filename in ("index.html", "app.js", "styles.css", "translations.js"):
            source = WEB / filename
            packaged = android_public / filename
            self.assertTrue(packaged.is_file(), filename)
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).digest(),
                hashlib.sha256(packaged.read_bytes()).digest(),
                filename,
            )

    def test_mobile_translation_does_not_replace_dayz_technical_identifiers(self):
        translations = (WEB / "translations.js").read_text(encoding="utf-8")
        for technical_value in (
            "types.xml",
            "events.xml",
            "cfggameplay.json",
            "dayzOffline.chernarusplus",
            "mpmissions/<mission>",
        ):
            self.assertNotIn(f'"{technical_value}":', translations)

    def test_mobile_source_contains_no_known_mojibake(self):
        for filename in ("index.html", "app.js", "translations.js"):
            text = (WEB / filename).read_text(encoding="utf-8")
            for marker in ("Ã", "ðŸ", "â€”", "â€¦", "Â·"):
                self.assertNotIn(marker, text, filename)


if __name__ == "__main__":
    unittest.main()
