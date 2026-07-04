from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class FakeChannel:
    def __init__(self, name, channel_id):
        self.name = name
        self.id = channel_id


class FakeCategory:
    def __init__(self, name):
        self.name = name


class FakeGuild:
    def __init__(self, channels):
        self.text_channels = channels

    def get_channel(self, channel_id):
        for channel in self.text_channels:
            if channel.id == channel_id:
                return channel
        return None


class ChannelMatchingTests(unittest.TestCase):
    def test_nitrado_ban_feed_matches_decorated_renamed_original(self):
        channel = FakeChannel("nitrado-ban", 100)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "nitrado_ban_logs"))

    def test_nitrado_ban_feed_prefers_decorated_original_over_plain_duplicate(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])

        self.assertIs(bot.preferred_existing_feed_channel(guild, "nitrado_ban_logs"), original)

    def test_discover_updates_saved_nitrado_duplicate_to_preferred_original(self):
        original = FakeChannel("🔴🔴・nitrado-ban・🔴🔴", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])
        config = {"channels": {"nitrado_ban_logs": duplicate.id}}

        self.assertTrue(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["nitrado_ban_logs"], original.id)

    def test_custom_feed_route_is_not_overwritten_by_default_channel(self):
        default = FakeChannel("🚨🏴・raids・🏴🚨", 100)
        custom = FakeChannel("airfield-pings", 200)
        guild = FakeGuild([default, custom])
        config = {"channels": {"raids": custom.id}, "custom_channel_routes": ["raids"]}

        self.assertFalse(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["raids"], custom.id)

    def test_feed_target_resolves_live_pack_and_raid_alias(self):
        keys, error = bot.resolve_feed_target_keys("live")
        self.assertIsNone(error)
        self.assertIn("raids", keys)

        keys, error = bot.resolve_feed_target_keys("raid events")
        self.assertIsNone(error)
        self.assertEqual(keys, ["raids"])

    def test_radar_channel_matches_plain_radars(self):
        channel = FakeChannel("Radars", 300)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "radar"))

    def test_radar_category_matches_plain_radars(self):
        category = FakeCategory("Radars")

        self.assertTrue(bot.category_matches_bot_spec(category, "radar_pings"))

    def test_livo_trader_category_matches_plain_owner_category(self):
        category = FakeCategory("Livo Trader")

        self.assertTrue(bot.category_matches_bot_spec(category, "livo_trader"))

    def test_livo_trader_channels_match_plain_names(self):
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel("trader-log", 400), "livo_trader_log"))
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel("transactions", 401), "livo_trader_transactions"))
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel("balance-feed", 402), "livo_trader_balance"))

    def test_livo_trader_pack_is_guild_local_not_in_all(self):
        self.assertIn("livo_trader_balance", bot.CHANNEL_RESTORE_PACKS["livo_trader"])
        self.assertNotIn("livo_trader_balance", bot.CHANNEL_RESTORE_PACKS["all"])

    def test_swear_jar_feed_is_managed_channel(self):
        channel = FakeChannel("swear-jar", 500)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "swear_jar_feed"))
        self.assertIn("swear_jar_feed", bot.CHANNEL_RESTORE_PACKS["economy"])

    def test_setup_server_settings_preserve_existing_values_when_blank(self):
        config = {
            "server_platform": "playstation",
            "server_map": "livonia",
            "server_mode": "pve",
        }

        platform, server_map, server_mode = bot.resolve_setup_server_settings(config)

        self.assertEqual("playstation", platform)
        self.assertEqual("livonia", server_map)
        self.assertEqual("pve", server_mode)

    def test_setup_server_settings_can_change_only_server_mode(self):
        config = {
            "server_platform": "xbox",
            "server_map": "chernarus",
            "server_mode": "pve",
        }

        platform, server_map, server_mode = bot.resolve_setup_server_settings(config, server_mode="PVP only")

        self.assertEqual("xbox", platform)
        self.assertEqual("chernarus", server_map)
        self.assertEqual("pvp", server_mode)


if __name__ == "__main__":
    unittest.main()
