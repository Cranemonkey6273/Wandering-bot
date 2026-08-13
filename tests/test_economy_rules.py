from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests._bot_loader import import_bot_module


class EconomyRuleTests(unittest.TestCase):
    def setUp(self):
        self.bot = import_bot_module()

    def test_legacy_kill_rule_is_moved_out_of_chat_rules(self):
        config = {
            "chat_rules": [
                {"kind": "reward", "keyword": "kill", "event_type": "kill", "amount": 100},
                {"kind": "reward", "keyword": "gg", "amount": 5},
            ]
        }

        changed = self.bot.normalize_economy_rule_stores(config)

        self.assertTrue(changed)
        self.assertEqual(["gg"], [rule["keyword"] for rule in config["chat_rules"]])
        self.assertEqual(["kill"], [rule["event_type"] for rule in config["adm_reward_rules"]])

    def test_saying_kill_in_chat_does_not_trigger_verified_kill_rule(self):
        guild_id = "9910001"
        config = {
            "chat_rules": [
                {"kind": "reward", "keyword": "kill", "event_type": "kill", "amount": 100}
            ]
        }
        message = SimpleNamespace(
            guild=SimpleNamespace(id=int(guild_id)),
            author=SimpleNamespace(id=44, mention="<@44>"),
            channel=SimpleNamespace(send=AsyncMock()),
        )
        self.bot.guild_configs[guild_id] = config

        with patch.object(self.bot, "save_wallets") as save_wallets, patch.object(
            self.bot, "send_money_feed", new=AsyncMock()
        ) as send_money_feed:
            asyncio.run(self.bot.apply_chat_reward_punishment_rules(message, "i got a kill"))

        save_wallets.assert_not_called()
        send_money_feed.assert_not_awaited()
        message.channel.send.assert_not_awaited()

    def test_verified_adm_kill_pays_linked_killer(self):
        guild_id = "9910002"
        user_id = "55002"
        config = {
            "adm_reward_rules": [
                {"id": "pay-kills", "event_type": "kill", "kind": "reward", "amount": 250, "enabled": True}
            ],
            "chat_rules": [],
        }
        wallet_key = self.bot.wallet_key(guild_id, user_id)
        self.bot.wallets.pop(wallet_key, None)
        kill_details = {"killer": "KillerOne", "victim": "VictimOne", "distance": 42.5}

        with patch.object(
            self.bot,
            "linked_gamertag_index_record",
            return_value={"discord_id": user_id, "gamertag": "KillerOne"},
        ), patch.object(self.bot, "discord_guild_for_runtime_id", return_value=SimpleNamespace(id=int(guild_id))), patch.object(
            self.bot, "send_money_feed", new=AsyncMock()
        ) as send_money_feed, patch.object(self.bot, "save_wallets") as save_wallets:
            result = asyncio.run(self.bot.apply_verified_adm_economy_rules(guild_id, config, kill_details))

        self.assertEqual(1, len(result))
        self.assertEqual(250, self.bot.wallet_balance(self.bot.guild_wallet(guild_id, user_id, "KillerOne")))
        save_wallets.assert_called_once()
        send_money_feed.assert_awaited_once()

    def test_longshot_rule_requires_configured_distance(self):
        guild_id = "9910003"
        config = {
            "adm_reward_rules": [
                {
                    "id": "longshot",
                    "event_type": "longshot",
                    "kind": "reward",
                    "amount": 500,
                    "minimum_distance": 300,
                    "enabled": True,
                }
            ],
            "chat_rules": [],
        }
        with patch.object(self.bot, "linked_gamertag_index_record") as link_lookup, patch.object(
            self.bot, "save_wallets"
        ) as save_wallets:
            result = asyncio.run(
                self.bot.apply_verified_adm_economy_rules(
                    guild_id,
                    config,
                    {"killer": "KillerOne", "victim": "VictimOne", "distance": 299.9},
                )
            )

        self.assertEqual([], result)
        link_lookup.assert_not_called()
        save_wallets.assert_not_called()

    def test_console_delivery_file_writes_are_serialized(self):
        guild_id = "9910004"
        self.bot.delivery_upload_locks.pop(guild_id, None)
        active = 0
        maximum_active = 0

        async def fake_delivery(*_args, **_kwargs):
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.02)
            active -= 1
            return True, "test", "done"

        async def run_parallel():
            calls = [
                self.bot.route_console_shop_delivery(
                    guild_id, {}, {"Hacksaw": 1}, 1, 2, False, 0, f"order-{index}", "Player", "44"
                )
                for index in range(5)
            ]
            return await asyncio.gather(*calls)

        try:
            with patch.object(self.bot, "_route_console_shop_delivery_unlocked", side_effect=fake_delivery):
                results = asyncio.run(run_parallel())
        finally:
            self.bot.delivery_upload_locks.pop(guild_id, None)

        self.assertEqual(1, maximum_active)
        self.assertEqual(5, len(results))
        self.assertTrue(all(result[0] for result in results))

    def test_five_console_orders_are_all_preserved(self):
        guild_id = "9910005:cherno"
        config = {"scenario_events": []}
        self.bot.delivery_upload_locks.pop(guild_id, None)

        async def successful_push(*_args, **_kwargs):
            await asyncio.sleep(0.005)
            return True, "uploaded"

        async def run_parallel():
            return await asyncio.gather(*[
                self.bot.route_console_shop_delivery(
                    guild_id,
                    config,
                    {"Hacksaw": 1},
                    100 + index,
                    200 + index,
                    False,
                    0,
                    f"order-{index}",
                    f"Player{index}",
                    str(1000 + index),
                )
                for index in range(5)
            ])

        try:
            with patch.object(
                self.bot, "auto_push_scenario_events_xml", side_effect=successful_push
            ), patch.object(self.bot, "save_guild_configs_for_runtime"):
                results = asyncio.run(run_parallel())
        finally:
            self.bot.delivery_upload_locks.pop(guild_id, None)

        order_ids = {
            str(event.get("shop_order_id"))
            for event in config["scenario_events"]
        }
        self.assertEqual({f"order-{index}" for index in range(5)}, order_ids)
        self.assertEqual(5, len(config["scenario_events"]))
        self.assertTrue(all(result[0] for result in results))


if __name__ == "__main__":
    unittest.main()
