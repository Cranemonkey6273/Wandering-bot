from __future__ import annotations

import os
import sys
import asyncio
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class FakeRole:
    def __init__(self, name, role_id):
        self.name = name
        self.id = role_id


class FakeMember:
    def __init__(self, roles=None):
        self.roles = roles or []


class FakeChannel:
    def __init__(self, name, channel_id, category=None):
        self.name = name
        self.id = channel_id
        self.category = category
        self.category_id = getattr(category, "id", None)
        self.edit_calls = []

    async def edit(self, **kwargs):
        self.edit_calls.append(kwargs)
        if "name" in kwargs:
            self.name = kwargs["name"]
        if "category" in kwargs:
            self.category = kwargs["category"]
            self.category_id = getattr(kwargs["category"], "id", None)
        return self


class FakeCategory:
    def __init__(self, name, category_id=0):
        self.name = name
        self.id = category_id


class FakeFooter:
    def __init__(self, text=""):
        self.text = text


class FakeEmbed:
    def __init__(self, footer_text=""):
        self.footer = FakeFooter(footer_text)
        self.timestamp = None

    def set_footer(self, *, text=None, **_kwargs):
        self.footer = FakeFooter(text or "")
        return self


class FakeSendChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return type("SentMessage", (), {"id": 123})()


class FakeGuild:
    def __init__(self, channels, guild_id="guild-a", name="Guild A"):
        self.text_channels = channels
        self.id = guild_id
        self.name = name
        self.owner = "owner"

    def get_channel(self, channel_id):
        for channel in self.text_channels:
            if channel.id == channel_id:
                return channel
        return None


class ChannelMatchingTests(unittest.TestCase):
    def test_style_embed_replaces_legacy_alpha_footer(self):
        embed = FakeEmbed("Wandering Bot Alpha - Disconnect Feed")

        bot.style_embed(embed)

        self.assertEqual(bot.POWERED_BY_FOOTER_TEXT, embed.footer.text)

    def test_send_feed_embed_replaces_legacy_alpha_footer_without_style_flag(self):
        embed = FakeEmbed("Wandering Bot Alpha - Disconnect Feed")
        channel = FakeSendChannel()

        asyncio.run(bot.send_feed_embed("guild-1", "disconnects", channel, embed, context="disconnect"))

        self.assertEqual(bot.POWERED_BY_FOOTER_TEXT, channel.sent[0]["embed"].footer.text)

    def test_nitrado_ban_feed_matches_decorated_renamed_original(self):
        channel = FakeChannel("nitrado-ban", 100)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "nitrado_ban_logs"))

    def test_nitrado_ban_feed_prefers_decorated_original_over_plain_duplicate(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])

        self.assertIs(bot.preferred_existing_feed_channel(guild, "nitrado_ban_logs"), original)

    def test_discover_does_not_update_saved_route_without_explicit_auto_discovery(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])
        config = {"channels": {"nitrado_ban_logs": duplicate.id}}

        self.assertFalse(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["nitrado_ban_logs"], duplicate.id)

    def test_discover_updates_saved_route_when_auto_discovery_is_explicit(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])
        config = {"allow_channel_auto_discovery": True, "channels": {"nitrado_ban_logs": duplicate.id}}

        self.assertTrue(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["nitrado_ban_logs"], original.id)

    def test_custom_feed_route_is_not_overwritten_by_default_channel(self):
        default = FakeChannel("🚨🏴・raids・🏴🚨", 100)
        custom = FakeChannel("airfield-pings", 200)
        guild = FakeGuild([default, custom])
        config = {"channels": {"raids": custom.id}, "custom_channel_routes": ["raids"]}

        self.assertFalse(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["raids"], custom.id)

    def test_forced_create_does_not_rename_saved_dashboard_audit_channel(self):
        custom = FakeChannel("staff-change-log", 300)
        guild = FakeGuild([custom])
        config = {"channels": {"dashboard_audit": custom.id}}

        async def run():
            with mock.patch.object(bot, "ensure_bot_category", new_callable=mock.AsyncMock) as ensure_category:
                channel = await bot.get_or_create_feed_channel(
                    guild,
                    config,
                    "dashboard_audit",
                    bot.DEFAULT_CHANNEL_NAMES["dashboard_audit"],
                    private=True,
                    force=True,
                )
                ensure_category.assert_not_awaited()
                return channel

        channel = asyncio.run(run())

        self.assertIs(channel, custom)
        self.assertEqual("staff-change-log", custom.name)
        self.assertEqual([], custom.edit_calls)

    def test_get_or_create_feed_channel_resolves_dashboard_string_channel_id(self):
        routed = FakeChannel("LiVo-FLAg-FeeD", 1507886422521155644)
        guild = FakeGuild([routed])
        config = {"channels": {"flag_feed": "1507886422521155644"}}

        async def run():
            return await bot.get_or_create_feed_channel(
                guild,
                config,
                "flag_feed",
                bot.DEFAULT_CHANNEL_NAMES["flag_feed"],
                private=True,
            )

        channel = asyncio.run(run())

        self.assertIs(channel, routed)
        self.assertEqual([], routed.edit_calls)

    def test_explicit_repair_can_rename_saved_dashboard_audit_channel(self):
        custom = FakeChannel("staff-change-log", 300)
        category = FakeCategory("Staff Ops", 900)
        guild = FakeGuild([custom])
        config = {"channels": {"dashboard_audit": custom.id}}

        async def run():
            with mock.patch.object(bot, "ensure_bot_category", new_callable=mock.AsyncMock, return_value=category):
                return await bot.get_or_create_feed_channel(
                    guild,
                    config,
                    "dashboard_audit",
                    bot.DEFAULT_CHANNEL_NAMES["dashboard_audit"],
                    private=True,
                    force=True,
                    repair_existing=True,
                )

        channel = asyncio.run(run())

        self.assertIs(channel, custom)
        self.assertEqual(bot.DEFAULT_CHANNEL_NAMES["dashboard_audit"], custom.name)
        self.assertEqual(category.id, custom.category_id)

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

    def test_dashboard_live_feed_mapping_records_dashboard_only_events(self):
        previous = bot.dashboard_live_feeds
        try:
            bot.dashboard_live_feeds = {}

            self.assertEqual("placed_feed", bot.dashboard_live_feed_key_for_event("placed"))
            self.assertEqual("building", bot.dashboard_live_feed_key_for_event("build"))
            changed = bot.record_dashboard_live_feed(
                "guild-1",
                "placed",
                '10:00:00 | Player "Crane" (pos=<1000,2000,10>) placed FenceKit',
            )
        finally:
            recorded = bot.dashboard_live_feeds
            bot.dashboard_live_feeds = previous

        self.assertTrue(changed)
        self.assertEqual("placed_feed", recorded["guild-1"][0]["feed_key"])
        self.assertIn("Crane", recorded["guild-1"][0]["summary"])

    def test_server_profile_runtime_ids_keep_guilds_isolated(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "A",
                    "nitrado_token": "shared-token",
                    "service_id": "base-service",
                    "server_profiles": {
                        "livo": {"profile_name": "Livo", "service_id": "111", "server_map": "livonia", "channels": {"building": "10"}},
                    },
                },
                "guild-b": {
                    "guild_name": "B",
                    "server_profiles": {
                        "livo": {"profile_name": "Other Livo", "service_id": "222", "server_map": "chernarus", "channels": {"building": "20"}},
                    },
                },
            }

            runtime_a = bot.server_profile_runtime_id("guild-a", "livo")
            runtime_b = bot.server_profile_runtime_id("guild-b", "livo")
            config_a = bot.config_for_server_runtime(runtime_a)
            config_b = bot.config_for_server_runtime(runtime_b)

            self.assertEqual("guild-a:livo", runtime_a)
            self.assertEqual("guild-b:livo", runtime_b)
            self.assertNotEqual(bot.adm_file_path(runtime_a), bot.adm_file_path(runtime_b))
            self.assertEqual("shared-token", config_a["nitrado_token"])
            self.assertEqual("111", config_a["service_id"])
            self.assertEqual("222", config_b["service_id"])
            self.assertNotIn("nitrado_token", config_b)
            self.assertEqual("10", config_a["channels"]["building"])
            self.assertEqual("20", config_b["channels"]["building"])
            self.assertEqual("livonia", bot.server_map_key(runtime_a))
            self.assertEqual("chernarus", bot.server_map_key(runtime_b))
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_uses_saved_feed_channel_id(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {"killfeed": "100"}},
                        "livo": {"profile_name": "Wandering Around Livo", "server_map": "livonia", "channels": {"killfeed": "200"}},
                    },
                }
            }
            channel = FakeChannel("killfeed", 200)
            guild = FakeGuild([channel])

            runtime_id, config, error = bot.runtime_config_for_command_context(guild, channel=channel, require_profile=True)

            self.assertIsNone(error)
            self.assertEqual("guild-a:livo", runtime_id)
            self.assertEqual("livonia", config["server_map"])
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_uses_category_name(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {}},
                        "livo": {"profile_name": "Livo", "server_map": "livonia", "channels": {}},
                    },
                }
            }
            category = FakeCategory("Wandering Around Cherno")
            channel = FakeChannel("leaderboards", 300, category=category)
            guild = FakeGuild([channel])

            runtime_id, _config, error = bot.runtime_config_for_command_context(guild, channel=channel, require_profile=True)

            self.assertIsNone(error)
            self.assertEqual("guild-a:cherno", runtime_id)
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_channel_name_beats_ambiguous_roles(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {}},
                        "livo": {"profile_name": "Livo", "server_map": "livonia", "channels": {}},
                    },
                }
            }
            member = FakeMember([FakeRole("Cherno Survivor", 10), FakeRole("Livo Survivor", 20)])
            channel = FakeChannel("livo-leaderboard", 400)
            guild = FakeGuild([channel])

            runtime_id, _config, error = bot.runtime_config_for_command_context(guild, channel=channel, member=member, require_profile=True)

            self.assertIsNone(error)
            self.assertEqual("guild-a:livo", runtime_id)
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_ambiguous_roles_require_choice(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {}},
                        "livo": {"profile_name": "Livo", "server_map": "livonia", "channels": {}},
                    },
                }
            }
            member = FakeMember([FakeRole("Cherno Survivor", 10), FakeRole("Livo Survivor", 20)])
            guild = FakeGuild([])

            runtime_id, config, error = bot.runtime_config_for_command_context(guild, member=member, require_profile=True)

            self.assertIsNone(runtime_id)
            self.assertIsNone(config)
            self.assertIn("more than one possible", error)
        finally:
            bot.guild_configs = previous_configs

    def test_player_stats_same_name_can_split_by_server_profile(self):
        previous_stats = bot.player_stats
        try:
            bot.player_stats = {
                "Crane": {
                    "guild_id": "guild-a:cherno",
                    "player_name": "Crane",
                    "kills": 5,
                }
            }

            stats = bot.ensure_player_stats_record("guild-a:livo", "Crane")
            stats["kills"] = 2
            again = bot.ensure_player_stats_record("guild-a:livo", "Crane")
            storage_key, found = bot.player_stats_for_guild_player("guild-a:livo", "Crane")

            self.assertIs(again, stats)
            self.assertEqual("Crane [guild-a_livo]", storage_key)
            self.assertEqual("Crane", bot.player_stats_display_name(storage_key, found))
            self.assertEqual("guild-a:livo", found["guild_id"])
            self.assertEqual(5, bot.player_stats["Crane"]["kills"])
        finally:
            bot.player_stats = previous_stats

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
