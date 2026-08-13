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

    def _apply_rule(self, guild_id, rule, line, event_type, *, kill_details=None, user_id="55100"):
        self.bot.wallets.pop(self.bot.wallet_key(guild_id, user_id), None)
        config = {"adm_reward_rules": [rule], "chat_rules": []}
        with patch.object(
            self.bot,
            "linked_gamertag_index_record",
            return_value={"discord_id": user_id},
        ), patch.object(self.bot, "discord_guild_for_runtime_id", return_value=None), patch.object(
            self.bot, "save_wallets"
        ) as save_wallets:
            result = asyncio.run(
                self.bot.apply_verified_adm_economy_rules(
                    guild_id,
                    config,
                    kill_details,
                    event_type=event_type,
                    line=line,
                )
            )
        return result, save_wallets, self.bot.guild_wallet(guild_id, user_id)

    def test_player_hit_pays_attacker_after_minimum_damage(self):
        guild_id = "9910010"
        line = (
            '12:00:00 | Player "Victim" (id=v pos=<1,2,3>)[HP: 74] '
            'hit by Player "Attacker" (id=a pos=<4,5,6>) into Head(0) '
            'for 26 damage (Bullet_45ACP) with FX-45 from 12.5 meters'
        )
        result, save_wallets, wallet = self._apply_rule(
            guild_id,
            {"id": "hit", "event_type": "player_hit", "kind": "reward", "amount": 20, "minimum_damage": 10},
            line,
            "cut",
        )
        self.assertEqual("Attacker", result[0]["gamertag"])
        self.assertEqual(20, self.bot.wallet_balance(wallet))
        save_wallets.assert_called_once()

    def test_melee_hit_does_not_match_a_bullet(self):
        line = (
            'Player "Victim" (id=v pos=<1,2,3>)[HP: 74] hit by Player "Attacker" '
            '(id=a pos=<4,5,6>) into Head(0) for 26 damage (Bullet_45ACP) with FX-45 from 2 meters'
        )
        result, save_wallets, _wallet = self._apply_rule(
            "9910011",
            {"id": "melee", "event_type": "melee_hit", "kind": "reward", "amount": 15},
            line,
            "cut",
        )
        self.assertEqual([], result)
        save_wallets.assert_not_called()

    def test_melee_hit_pays_attacker(self):
        line = (
            'Player "Victim" (id=v pos=<1,2,3>)[HP: 80] hit by Player "Attacker" '
            '(id=a pos=<4,5,6>) into Torso(11) for 20 damage (MeleeFist) with Fists from 1.2 meters'
        )
        result, _save_wallets, wallet = self._apply_rule(
            "9910012",
            {"id": "melee", "event_type": "melee_hit", "kind": "reward", "amount": 15},
            line,
            "cut",
        )
        self.assertEqual("Attacker", result[0]["gamertag"])
        self.assertEqual(15, self.bot.wallet_balance(wallet))

    def test_non_kill_corpse_hit_never_pays(self):
        line = (
            'Player "Victim" (DEAD) (id=v pos=<1,2,3>)[HP: 0] hit by Player "Attacker" '
            '(id=a pos=<4,5,6>) into Head(0) for 40 damage (Bullet_9x19) with SG5-K from 2 meters'
        )
        result, save_wallets, _wallet = self._apply_rule(
            "9910013",
            {"id": "hit", "event_type": "player_hit", "kind": "reward", "amount": 20},
            line,
            "cut",
        )
        self.assertEqual([], result)
        save_wallets.assert_not_called()

    def test_infected_death_is_not_mistaken_for_infected_kill(self):
        death_line = 'Player "Victim" (DEAD) killed by Infected'
        result, save_wallets, _wallet = self._apply_rule(
            "9910014",
            {"id": "infected", "event_type": "infected_kill", "kind": "reward", "amount": 50},
            death_line,
            "zombie_kill",
        )
        self.assertEqual([], result)
        save_wallets.assert_not_called()

    def test_infected_kill_requires_player_to_be_named_as_killer(self):
        hunt_line = 'Player "Hunter" killed InfectedArmy'
        result, _save_wallets, wallet = self._apply_rule(
            "9910015",
            {"id": "infected", "event_type": "infected_kill", "kind": "reward", "amount": 50},
            hunt_line,
            "zombie_kill",
        )
        self.assertEqual("Hunter", result[0]["gamertag"])
        self.assertEqual(50, self.bot.wallet_balance(wallet))

    def test_build_and_animal_hunt_rules_pay_only_the_actor(self):
        build_result, _save_wallets, _wallet = self._apply_rule(
            "9910016",
            {"id": "build", "event_type": "build", "kind": "reward", "amount": 8},
            'Player "Builder" (id=b pos=<1,2,3>) built Fence with Shovel',
            "build",
        )
        hunt_result, _save_wallets, _wallet = self._apply_rule(
            "9910017",
            {"id": "hunt", "event_type": "animal_kill", "kind": "reward", "amount": 30},
            'Player "Hunter" killed Animal_CanisLupus (pos=<1,2,3>)',
            "animal_kill",
        )
        self.assertEqual("Builder", build_result[0]["gamertag"])
        self.assertEqual("Hunter", hunt_result[0]["gamertag"])

    def test_headshot_rule_only_matches_headshot_kill(self):
        result, _save_wallets, wallet = self._apply_rule(
            "9910018",
            {"id": "headshot", "event_type": "headshot", "kind": "reward", "amount": 75},
            "",
            "kill",
            kill_details={"killer": "Killer", "victim": "Victim", "distance": 20, "headshot": True},
        )
        self.assertEqual("Killer", result[0]["gamertag"])
        self.assertEqual(75, self.bot.wallet_balance(wallet))

    def test_official_bohemia_pvp_death_format_is_classified_and_parsed(self):
        line = (
            'Player "Survivor A"(id=victim pos=<13212.8, 10124.8, 6.0>) '
            'killed by "Survivor B"(id=killer pos=<13211.8, 10120.8, 6.0>) '
            'with M4-A1 from 42 meters'
        )
        self.assertEqual("kill", self.bot.classify_event(line))
        details = self.bot.extract_pvp_kill_details(line)
        self.assertEqual("Survivor A", details["victim"])
        self.assertEqual("Survivor B", details["killer"])
        self.assertEqual("M4-A1", details["weapon"])
        self.assertEqual(42.0, details["distance"])

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
