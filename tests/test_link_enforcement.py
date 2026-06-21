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


if __name__ == "__main__":
    unittest.main()
