from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class LinkEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.original_linked_players = bot.linked_players
        self.original_guild_configs = bot.guild_configs
        self.original_online_players = bot.online_players
        self.original_save_guild_configs = bot.save_guild_configs
        self.original_add_ban = bot.add_player_to_nitrado_banlist
        bot.save_guild_configs = lambda: None
        bot.linked_players = {}
        bot.guild_configs = {}
        bot.online_players = {}

    def tearDown(self):
        bot.linked_players = self.original_linked_players
        bot.guild_configs = self.original_guild_configs
        bot.online_players = self.original_online_players
        bot.save_guild_configs = self.original_save_guild_configs
        bot.add_player_to_nitrado_banlist = self.original_add_ban

    def test_known_linked_gamertag_uses_guild_scoped_links(self):
        bot.linked_players = {
            "100": {
                "discord_name": "Cranemonkey",
                "discord_id": "100",
                "guild_id": "cherno",
                "gamertag": "ChernoMonkey",
                "guild_links": {
                    "livo": {
                        "discord_name": "Cranemonkey",
                        "discord_id": "100",
                        "guild_id": "livo",
                        "gamertag": "CraneMonkey6273",
                        "verified_by": "ADM",
                    },
                    "cherno": {
                        "discord_name": "Cranemonkey",
                        "discord_id": "100",
                        "guild_id": "cherno",
                        "gamertag": "ChernoMonkey",
                        "verified_by": "ADM",
                    },
                },
            }
        }

        self.assertTrue(bot.has_known_linked_gamertag("livo", "Cranemonkey6273"))
        self.assertTrue(bot.has_known_linked_gamertag("cherno", "ChernoMonkey"))
        self.assertFalse(bot.has_known_linked_gamertag("livo", "ChernoMonkey"))

    def test_legacy_link_records_are_migrated_into_guild_links(self):
        bot.linked_players = {
            "100": {
                "discord_name": "Cranemonkey",
                "discord_id": "100",
                "guild_id": "1504",
                "gamertag": "CraneMonkey6273",
                "alt_gamertags": ["CraneAlt"],
                "verified_by": "ADM",
            }
        }

        changed = bot.migrate_linked_player_guild_links_from_legacy()

        self.assertTrue(changed)
        self.assertTrue(bot.has_known_linked_gamertag("1504", "CraneMonkey6273"))
        self.assertEqual(
            "CraneMonkey6273",
            bot.linked_players["100"]["guild_links"]["1504"]["gamertag"],
        )
        self.assertEqual(["CraneAlt"], bot.linked_players["100"]["guild_links"]["1504"]["alt_gamertags"])

    def test_link_enforcement_ban_writer_skips_linked_gamertag(self):
        bot.linked_players = {
            "100": {
                "discord_name": "Cranemonkey",
                "discord_id": "100",
                "guild_links": {
                    "1504": {
                        "discord_name": "Cranemonkey",
                        "discord_id": "100",
                        "guild_id": "1504",
                        "gamertag": "CraneMonkey6273",
                        "verified_by": "ADM",
                    }
                },
            }
        }

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("Nitrado ban writer should not be called for a linked player")

        bot.add_player_to_nitrado_banlist = fail_if_called

        ok, message = asyncio.run(
            bot.add_player_to_nitrado_banlist_async(
                "1504",
                {},
                "CraneMonkey6273",
                ban_type="temp",
                reason="Discord link required",
                source="discord_link_enforcement",
                minutes=60,
            )
        )

        self.assertFalse(ok)
        self.assertIn("already linked", message)

    def test_link_enforcement_ban_writer_uses_server_link_index(self):
        bot.linked_players = {}
        bot.guild_configs = {
            "1504": {
                "linked_gamertag_index": {
                    "cranemonkey6273": {
                        "gamertag": "CraneMonkey6273",
                        "normalized_gamertag": "cranemonkey6273",
                        "discord_id": "100",
                        "discord_name": "Cranemonkey",
                        "guild_id": "1504",
                        "source": "linkgamer",
                    }
                }
            }
        }

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("Nitrado ban writer should not be called for a server-indexed linked player")

        bot.add_player_to_nitrado_banlist = fail_if_called

        ok, message = asyncio.run(
            bot.add_player_to_nitrado_banlist_async(
                "1504",
                bot.guild_configs["1504"],
                "CraneMonkey6273",
                ban_type="temp",
                reason="Discord link required",
                source="discord_link_enforcement",
                minutes=60,
            )
        )

        self.assertFalse(ok)
        self.assertIn("already linked", message)

    def test_sync_linked_gamertag_index_backfills_existing_links(self):
        bot.guild_configs = {"1504": {"guild_name": "Livonia"}}
        bot.linked_players = {
            "100": {
                "discord_name": "Cranemonkey",
                "discord_id": "100",
                "guild_links": {
                    "1504": {
                        "discord_name": "Cranemonkey",
                        "discord_id": "100",
                        "guild_id": "1504",
                        "gamertag": "CraneMonkey6273",
                        "alt_gamertags": ["CraneAlt"],
                    }
                },
            }
        }

        self.assertTrue(bot.sync_linked_gamertag_index_from_linked_players())
        index = bot.guild_configs["1504"]["linked_gamertag_index"]
        self.assertEqual("CraneMonkey6273", index["cranemonkey6273"]["gamertag"])
        self.assertEqual("CraneAlt", index["cranealt"]["gamertag"])

    def test_link_enforcement_join_does_not_queue_indexed_link(self):
        bot.guild_configs = {
            "1504": {
                "discord_link_enforcement": {"enabled": True, "grace_minutes": 1},
                "linked_gamertag_index": {
                    "cranemonkey6273": {
                        "gamertag": "CraneMonkey6273",
                        "normalized_gamertag": "cranemonkey6273",
                        "discord_id": "100",
                        "guild_id": "1504",
                    }
                },
            }
        }

        queued = bot.record_link_enforcement_join("1504", "CraneMonkey6273")

        self.assertFalse(queued)
        self.assertEqual({}, bot.guild_configs["1504"].get("discord_link_enforcement_state", {}).get("pending", {}))


if __name__ == "__main__":
    unittest.main()
