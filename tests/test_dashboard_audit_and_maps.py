from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from tests._bot_loader import import_bot_module


class FakeChannel:
    def __init__(self, channel_id, name):
        self.id = channel_id
        self.name = name


class FakeGuild:
    id = 1429812480749735978
    name = "Left 4 Dead Day Z"

    def __init__(self):
        self._channels = {100: FakeChannel(100, "bot-updates"), 200: FakeChannel(200, "restart-alerts")}

    def get_channel(self, channel_id):
        return self._channels.get(int(channel_id))

    def get_role(self, _role_id):
        return None

    def get_member(self, _member_id):
        return None


class DashboardAuditAndMapTests(unittest.TestCase):
    def setUp(self):
        self.bot = import_bot_module()

    def test_dashboard_audit_hides_guild_id_and_resolves_channel_keys(self):
        guild = FakeGuild()
        config = {"channels": {"bot_updates": 100, "restart_logs": 200}}
        payload = {
            "guild_id": str(guild.id),
            "restart_channel_key": "bot_updates",
            "restart_log_channel_key": "restart_logs",
            "restart_schedule_enabled": "true",
        }

        details = self.bot.format_dashboard_audit_details(payload, guild, config)

        self.assertNotIn(str(guild.id), details)
        self.assertNotIn("bot_updates", details)
        self.assertIn("**Restart Channel:** #bot-updates", details)
        self.assertIn("**Restart Log Channel:** #restart-alerts", details)
        self.assertIn("**Restart Schedule:** On", details)

    def test_dashboard_audit_summary_hides_raw_ids(self):
        summary = self.bot.format_dashboard_audit_summary_text(
            "guild_id: 1429812480749735978; action: save; channel_id: 123456789012345678"
        )

        self.assertEqual("action: save", summary)

    def test_bundled_livonia_map_wins_over_bad_guild_override(self):
        old_files = dict(self.bot.MAP_IMAGE_FILES)
        old_configs = dict(self.bot.guild_configs)
        fd, temp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        try:
            self.bot.MAP_IMAGE_FILES["livonia"] = temp_path
            self.bot.guild_configs["guild-1"] = {"heatmap_images": {"livonia": "wrong_photo.jpg"}}

            self.assertEqual(temp_path, self.bot.configured_heatmap_image_source("guild-1", "livonia"))
        finally:
            self.bot.MAP_IMAGE_FILES.clear()
            self.bot.MAP_IMAGE_FILES.update(old_files)
            self.bot.guild_configs.clear()
            self.bot.guild_configs.update(old_configs)
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def test_chat_attachments_no_longer_auto_save_map_images(self):
        message = type("Message", (), {"guild": object(), "attachments": [object()]})()

        result = asyncio.run(self.bot.maybe_save_map_image_from_message(message, "save livonia map"))

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
