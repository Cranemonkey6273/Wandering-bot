from __future__ import annotations

import unittest
from datetime import UTC, datetime

from tests._bot_loader import import_bot_module


class DamageRestoreScheduleTests(unittest.TestCase):
    def setUp(self):
        self.bot = import_bot_module()
        self._old_upload = self.bot.upload_cfggameplay_damage_settings
        self._old_save = self.bot.save_guild_configs
        self.save_calls = 0
        self.upload_calls = []

        def fake_upload(guild_id, config, base_state, container_state):
            self.upload_calls.append((guild_id, base_state, container_state))
            return True, "uploaded", "/missions/cfggameplay.json", {
                "disableBaseDamage": base_state == "off",
                "disableContainerDamage": container_state == "off",
            }

        def fake_save():
            self.save_calls += 1

        self.bot.upload_cfggameplay_damage_settings = fake_upload
        self.bot.save_guild_configs = fake_save

    def tearDown(self):
        self.bot.upload_cfggameplay_damage_settings = self._old_upload
        self.bot.save_guild_configs = self._old_save

    def test_damage_restore_schedule_stages_protection_off_flags(self):
        now = datetime(2026, 6, 19, 20, 45, tzinfo=UTC)
        config = {
            "damage_preflight_minutes": 15,
            "damage_restore_schedule_enabled": True,
            "damage_restore_schedule": {
                "enabled": True,
                "first_date": "2026-06-19",
                "time": "21:00",
                "timezone": "UTC",
                "interval_value": 14,
                "interval_unit": "days",
            },
        }

        results = self.bot.apply_due_damage_schedule("guild-1", config, now)

        self.assertIsNotNone(results)
        self.assertEqual(["raid_damage_off"], [item["schedule_label"] for item in results])
        self.assertEqual([("guild-1", "off", "off")], self.upload_calls)
        self.assertEqual("off", config["base_damage_state"])
        self.assertEqual("off", config["container_damage_state"])
        self.assertTrue(results[0]["flags"]["disableBaseDamage"])
        self.assertTrue(results[0]["flags"]["disableContainerDamage"])
        self.assertGreaterEqual(self.save_calls, 1)

    def test_restore_schedule_wins_when_start_and_restore_are_due(self):
        now = datetime(2026, 6, 19, 20, 45, tzinfo=UTC)
        due_schedule = {
            "enabled": True,
            "first_date": "2026-06-19",
            "time": "21:00",
            "timezone": "UTC",
            "interval_value": 14,
            "interval_unit": "days",
        }
        config = {
            "base_damage_state": "on",
            "container_damage_state": "on",
            "damage_preflight_minutes": 15,
            "damage_schedule_enabled": True,
            "damage_schedule": {
                **due_schedule,
                "base_state": "on",
                "container_state": "on",
            },
            "damage_restore_schedule_enabled": True,
            "damage_restore_schedule": dict(due_schedule),
        }

        results = self.bot.apply_due_damage_schedule("guild-1", config, now)

        self.assertEqual(["raid_damage_on", "raid_damage_off"], [item["schedule_label"] for item in results])
        self.assertEqual([
            ("guild-1", "on", "on"),
            ("guild-1", "off", "off"),
        ], self.upload_calls)
        self.assertEqual("off", config["base_damage_state"])
        self.assertEqual("off", config["container_damage_state"])


if __name__ == "__main__":
    unittest.main()
