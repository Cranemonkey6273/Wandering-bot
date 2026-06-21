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
        self.original_linked_player_claims = bot.linked_player_claims
        self.original_guild_configs = bot.guild_configs
        self.original_online_players = bot.online_players
        self.original_save_guild_configs = bot.save_guild_configs
        self.original_add_ban = bot.add_player_to_nitrado_banlist
        self.original_remove_ban = bot.remove_player_from_nitrado_banlist
        self.original_post_ban_log = bot.post_nitrado_banlist_log
        bot.save_guild_configs = lambda: None
        bot.linked_players = {}
        bot.linked_player_claims = {}
        bot.guild_configs = {}
        bot.online_players = {}
        bot.post_nitrado_banlist_log = self._noop_ban_log

    def tearDown(self):
        bot.linked_players = self.original_linked_players
        bot.linked_player_claims = self.original_linked_player_claims
        bot.guild_configs = self.original_guild_configs
        bot.online_players = self.original_online_players
        bot.save_guild_configs = self.original_save_guild_configs
        bot.add_player_to_nitrado_banlist = self.original_add_ban
        bot.remove_player_from_nitrado_banlist = self.original_remove_ban
        bot.post_nitrado_banlist_log = self.original_post_ban_log

    async def _noop_ban_log(self, *_args, **_kwargs):
        return None

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

    def test_link_enforcement_ban_writer_checks_accept_list_first(self):
        config = {
            "discord_link_enforcement_state": {
                "accepted": {
                    "cranemonkey6273": {
                        "gamertag": "CraneMonkey6273",
                        "normalized_gamertag": "cranemonkey6273",
                        "status": "accepted",
                    }
                }
            }
        }
        bot.guild_configs = {"1504": config}

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("Nitrado ban writer should not be called for an accepted player")

        bot.add_player_to_nitrado_banlist = fail_if_called
        bot.remove_player_from_nitrado_banlist = lambda _config, _gamertag: (True, "removed")

        ok, message = asyncio.run(
            bot.add_player_to_nitrado_banlist_async(
                "1504",
                config,
                "CraneMonkey6273",
                ban_type="temp",
                reason="Discord link required",
                source="discord_link_enforcement",
                minutes=60,
            )
        )

        self.assertFalse(ok)
        self.assertIn("already linked", message)

    def test_link_enforcement_ban_writer_uses_verified_claims(self):
        bot.linked_player_claims = {
            "cranemonkey6273": {
                "current_user_id": "100",
                "current_discord_name": "Cranemonkey",
                "guild_id": "livo",
                "gamertag": "CraneMonkey6273",
                "status": "active",
            }
        }

        def fail_if_called(*_args, **_kwargs):
            raise AssertionError("Nitrado ban writer should not be called for an active linked claim")

        bot.add_player_to_nitrado_banlist = fail_if_called

        ok, message = asyncio.run(
            bot.add_player_to_nitrado_banlist_async(
                "cherno",
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

    def test_link_enforcement_skip_clears_stale_nitrado_ban(self):
        bot.linked_player_claims = {
            "cranemonkey6273": {
                "current_user_id": "100",
                "current_discord_name": "Cranemonkey",
                "guild_id": "livo",
                "gamertag": "CraneMonkey6273",
                "status": "active",
            }
        }
        removed = []

        def fake_remove(_config, gamertag):
            removed.append(gamertag)
            return True, "removed"

        bot.remove_player_from_nitrado_banlist = fake_remove

        ok, message = asyncio.run(
            bot.add_player_to_nitrado_banlist_async(
                "cherno",
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
        self.assertEqual(["CraneMonkey6273"], removed)

    def test_link_cleanup_keeps_non_link_temp_ban(self):
        config = {
            "nitrado_temp_bans": [
                {
                    "gamertag": "CraneMonkey6273",
                    "source": "safe_zone",
                    "reason": "Safe-zone violation",
                    "until_ts": 9999999999,
                }
            ]
        }
        removed = []

        def fake_remove(_config, gamertag):
            removed.append(gamertag)
            return True, "removed"

        bot.remove_player_from_nitrado_banlist = fake_remove

        changed = asyncio.run(
            bot.cleanup_link_enforcement_after_link(
                "cherno",
                config,
                "CraneMonkey6273",
                source="linkgamer",
            )
        )

        self.assertFalse(changed)
        self.assertEqual([], removed)

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

    def test_link_enforcement_join_uses_verified_link_from_other_server(self):
        bot.guild_configs = {
            "cherno": {
                "discord_link_enforcement": {"enabled": True, "grace_minutes": 1},
            }
        }
        bot.linked_players = {
            "100": {
                "discord_name": "Cranemonkey",
                "discord_id": "100",
                "guild_links": {
                    "livo": {
                        "discord_name": "Cranemonkey",
                        "discord_id": "100",
                        "guild_id": "livo",
                        "gamertag": "CraneMonkey6273",
                        "verified_by": "ADM",
                    }
                },
            }
        }

        queued = bot.record_link_enforcement_join("cherno", "CraneMonkey6273")

        self.assertFalse(queued)
        index = bot.guild_configs["cherno"]["linked_gamertag_index"]
        self.assertEqual("CraneMonkey6273", index["cranemonkey6273"]["gamertag"])
        self.assertEqual({}, bot.guild_configs["cherno"].get("discord_link_enforcement_state", {}).get("pending", {}))

    def test_link_enforcement_join_records_reject_list(self):
        bot.guild_configs = {
            "cherno": {
                "discord_link_enforcement": {"enabled": True, "grace_minutes": 1},
            }
        }

        queued = bot.record_link_enforcement_join("cherno", "UnlinkedPlayer")

        self.assertTrue(queued)
        rejected = bot.guild_configs["cherno"]["discord_link_enforcement_state"]["rejected"]
        self.assertEqual("UnlinkedPlayer", rejected["unlinkedplayer"]["gamertag"])
        self.assertEqual("pending", rejected["unlinkedplayer"]["status"])

    def test_linked_player_moves_from_reject_to_accept_list(self):
        config = {
            "discord_link_enforcement_state": {
                "pending": {"cranemonkey6273": {"gamertag": "CraneMonkey6273"}},
                "rejected": {"cranemonkey6273": {"gamertag": "CraneMonkey6273", "status": "pending"}},
            }
        }

        changed = bot.remember_linked_gamertag_for_server(
            "cherno",
            config,
            "100",
            "Cranemonkey",
            "CraneMonkey6273",
            source="linkgamer",
        )

        self.assertTrue(changed)
        state = config["discord_link_enforcement_state"]
        self.assertIn("cranemonkey6273", state["accepted"])
        self.assertEqual({}, state["pending"])
        self.assertEqual({}, state["rejected"])

    def test_link_enforcement_schedule_does_not_create_task_for_protected_link(self):
        bot.guild_configs = {
            "cherno": {
                "discord_link_enforcement": {"enabled": True, "grace_minutes": 1},
                "linked_gamertag_index": {
                    "cranemonkey6273": {
                        "gamertag": "CraneMonkey6273",
                        "normalized_gamertag": "cranemonkey6273",
                    }
                },
            }
        }
        original_create_task = bot.asyncio.create_task

        def fail_if_called(coro):
            coro.close()
            raise AssertionError("Protected linked players should not get delayed enforcement tasks")

        bot.asyncio.create_task = fail_if_called
        try:
            bot.schedule_link_enforcement_check("cherno", "CraneMonkey6273")
        finally:
            bot.asyncio.create_task = original_create_task


if __name__ == "__main__":
    unittest.main()
