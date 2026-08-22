from __future__ import annotations

import types
import unittest

from tests._bot_loader import import_bot_module


class _Emoji:
    def __init__(self, name, emoji_id):
        self.name = name
        self.id = emoji_id

    def __str__(self):
        return f"<:{self.name}:{self.id}>"


class ApplicationEmojiTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_bot_module()

    def setUp(self):
        self.original_bot = self.module.bot
        self.original_emojis = dict(self.module.wandering_emojis)

    def tearDown(self):
        self.module.bot = self.original_bot
        self.module.wandering_emojis.clear()
        self.module.wandering_emojis.update(self.original_emojis)

    def test_application_names_are_stable_and_scoped(self):
        self.assertEqual(
            "wb_warning",
            self.module.wandering_application_emoji_name("Warning"),
        )
        self.assertEqual(
            "warning",
            self.module.wandering_emoji_key_from_application_name("wb_warning"),
        )
        self.assertEqual(
            "warning",
            self.module.wandering_emoji_key_from_application_name("wandering_warning"),
        )
        self.assertEqual(
            "",
            self.module.wandering_emoji_key_from_application_name("customer"),
        )
        self.assertEqual(
            "custom_face",
            self.module.wandering_emoji_key_from_application_name("wb_custom_face"),
        )
        self.assertEqual(
            "wb_alert",
            self.module.wandering_application_emoji_name("wandering_alert"),
        )

    def test_custom_emoji_mentions_are_parsed(self):
        parsed = self.module.parse_wandering_custom_emoji(
            "<a:wandering_alert:123456789012345678>"
        )
        self.assertEqual(
            {
                "animated": True,
                "name": "wandering_alert",
                "id": "123456789012345678",
            },
            parsed,
        )
        self.assertIsNone(self.module.parse_wandering_custom_emoji("🚨"))

    def test_uploaded_assets_must_be_real_supported_images(self):
        png = b"\x89PNG\r\n\x1a\n" + b"safe-image"
        self.assertEqual(png, self.module.validate_wandering_emoji_asset(png))
        with self.assertRaisesRegex(ValueError, "valid PNG"):
            self.module.validate_wandering_emoji_asset(b"not-an-image")

    async def test_application_emojis_override_legacy_guild_mentions(self):
        async def fetch_application_emojis():
            return [
                _Emoji("wb_alert", 123456789012345678),
                _Emoji("unrelated", 223456789012345678),
            ]

        self.module.bot = types.SimpleNamespace(
            fetch_application_emojis=fetch_application_emojis,
        )
        self.module.wandering_emojis.clear()
        self.module.wandering_emojis["alert"] = "<:old_alert:323456789012345678>"

        applied = await self.module.refresh_wandering_application_emojis()

        self.assertEqual(
            {"alert": "<:wb_alert:123456789012345678>"},
            applied,
        )
        self.assertEqual(
            "<:wb_alert:123456789012345678>",
            self.module.wandering_emojis["alert"],
        )

    async def test_sync_migrates_a_legacy_emoji_into_the_application(self):
        application_emojis = []

        async def fetch_application_emojis():
            return list(application_emojis)

        async def create_application_emoji(*, name, image):
            self.assertEqual("wb_alert", name)
            self.assertEqual(b"image-bytes", image)
            emoji = _Emoji(name, 423456789012345678)
            application_emojis.append(emoji)
            return emoji

        async def download_wandering_emoji_asset(source):
            self.assertEqual("<:old_alert:323456789012345678>", source)
            return b"image-bytes"

        original_configured = self.module.configured_wandering_emoji_map
        original_download = self.module.download_wandering_emoji_asset
        self.module.configured_wandering_emoji_map = lambda: {
            "alert": "<:old_alert:323456789012345678>",
        }
        self.module.download_wandering_emoji_asset = download_wandering_emoji_asset
        self.module.bot = types.SimpleNamespace(
            fetch_application_emojis=fetch_application_emojis,
            create_application_emoji=create_application_emoji,
        )
        try:
            report = await self.module.sync_wandering_application_emojis()
        finally:
            self.module.configured_wandering_emoji_map = original_configured
            self.module.download_wandering_emoji_asset = original_download

        self.assertEqual(["alert"], report["created"])
        self.assertEqual([], report["failed"])
        self.assertEqual(
            "<:wb_alert:423456789012345678>",
            self.module.wandering_emojis["alert"],
        )

    async def test_direct_image_import_creates_one_global_emoji(self):
        application_emojis = []
        png = b"\x89PNG\r\n\x1a\n" + b"safe-image"

        async def fetch_application_emojis():
            return list(application_emojis)

        async def create_application_emoji(*, name, image):
            self.assertEqual("wb_bot", name)
            self.assertEqual(png, image)
            emoji = _Emoji(name, 523456789012345678)
            application_emojis.append(emoji)
            return emoji

        self.module.bot = types.SimpleNamespace(
            fetch_application_emojis=fetch_application_emojis,
            create_application_emoji=create_application_emoji,
        )

        emoji, created = await self.module.import_wandering_application_emoji(
            "bot",
            png,
        )

        self.assertTrue(created)
        self.assertEqual("<:wb_bot:523456789012345678>", str(emoji))
        self.assertEqual(str(emoji), self.module.wandering_emojis["bot"])

    async def test_full_guild_import_preserves_every_visible_emoji(self):
        source_emojis = [
            _Emoji("wandering_alert", 623456789012345678),
            _Emoji("custom_face", 723456789012345678),
        ]
        application_emojis = [_Emoji("wb_alert", 823456789012345678)]
        png = b"\x89PNG\r\n\x1a\n" + b"safe-image"

        async def fetch_application_emojis():
            return list(application_emojis)

        async def create_application_emoji(*, name, image):
            self.assertEqual("wb_custom_face", name)
            self.assertEqual(png, image)
            emoji = _Emoji(name, 923456789012345678)
            application_emojis.append(emoji)
            return emoji

        async def download_wandering_emoji_asset(_source):
            return png

        original_download = self.module.download_wandering_emoji_asset
        self.module.download_wandering_emoji_asset = download_wandering_emoji_asset
        self.module.bot = types.SimpleNamespace(
            fetch_application_emojis=fetch_application_emojis,
            create_application_emoji=create_application_emoji,
        )
        guild = types.SimpleNamespace(emojis=source_emojis)
        try:
            report = await self.module.sync_guild_emojis_to_wandering_application(
                guild
            )
        finally:
            self.module.download_wandering_emoji_asset = original_download

        self.assertEqual(2, report["source_count"])
        self.assertEqual(["custom_face"], report["created"])
        self.assertEqual(["wandering_alert"], report["existing"])
        self.assertEqual([], report["failed"])
        self.assertIn("custom_face", self.module.wandering_emojis)

    def test_bundled_pack_contains_111_static_and_12_animated_assets(self):
        assets = self.module.bundled_wandering_emoji_assets()

        self.assertEqual(123, len(assets))
        self.assertEqual(123, len({asset["name"] for asset in assets}))
        self.assertEqual(
            12,
            len([asset for asset in assets if asset["name"].endswith("_a")]),
        )
        self.assertTrue(all(len(asset["name"]) <= 32 for asset in assets))

    async def test_bundled_pack_sync_is_safe_to_resume(self):
        assets = self.module.bundled_wandering_emoji_assets()[:2]
        application_emojis = [_Emoji(assets[0]["name"], 103456789012345678)]

        async def fetch_application_emojis():
            return list(application_emojis)

        async def create_application_emoji(*, name, image):
            self.assertEqual(assets[1]["name"], name)
            self.module.validate_wandering_emoji_asset(image)
            emoji = _Emoji(name, 113456789012345678)
            application_emojis.append(emoji)
            return emoji

        self.module.bot = types.SimpleNamespace(
            fetch_application_emojis=fetch_application_emojis,
            create_application_emoji=create_application_emoji,
        )

        report = await self.module.sync_bundled_wandering_application_emojis(
            assets
        )

        self.assertEqual(2, report["total"])
        self.assertEqual([assets[0]["name"]], report["existing"])
        self.assertEqual([assets[1]["name"]], report["created"])
        self.assertEqual([], report["failed"])


if __name__ == "__main__":
    unittest.main()
