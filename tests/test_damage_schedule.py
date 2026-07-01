from __future__ import annotations

import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tests._bot_loader import import_bot_module


class RestartTimezoneTests(unittest.TestCase):
    def setUp(self):
        self.bot = import_bot_module()

    def test_restart_timezone_prefers_server_timezone(self):
        config = {"server_timezone": "America/New_York"}

        self.assertEqual("America/New_York", self.bot.restart_timezone_name(config))
        self.assertEqual("America/New_York", str(self.bot.restart_timezone_for_config(config)))

    def test_restart_minutes_are_calculated_from_local_time(self):
        config = {"server_timezone": "America/New_York"}
        local_now = datetime(2026, 6, 20, 6, 50, tzinfo=UTC).astimezone(
            self.bot.restart_timezone_for_config(config)
        )

        self.assertEqual(10, self.bot._minutes_until_next_restart(local_now, 3, 4))

    def test_restart_hours_wrap_across_midnight(self):
        self.assertEqual([1, 5, 9, 13, 17, 21], self.bot._restart_schedule_hours(17, 4))
        self.assertTrue(self.bot._restart_schedule_matches(datetime(2026, 7, 1, 13, 0, tzinfo=UTC), 17, 4))
        self.assertFalse(self.bot._restart_schedule_matches(datetime(2026, 7, 1, 14, 0, tzinfo=UTC), 17, 4))

    def test_nitrado_token_reports_hidden_lookalike_character(self):
        ok, _token, message = self.bot.validate_nitrado_api_token("еabc123")

        self.assertFalse(ok)
        self.assertIn("U+0435", message)
        self.assertIn("position 1", message)

    def test_apply_server_timezone_links_restart_and_adm_time(self):
        config = {}

        clean, error = self.bot.apply_server_timezone(config, "Europe/Berlin")

        self.assertEqual("", error)
        self.assertEqual("Europe/Berlin", clean)
        self.assertEqual("Europe/Berlin", config["server_timezone"])
        self.assertEqual("Europe/Berlin", config["adm_timezone"])
        self.assertEqual("Europe/Berlin", config["restart_timezone"])
        self.assertIsInstance(ZoneInfo(config["restart_timezone"]), ZoneInfo)


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

    def test_nested_only_damage_schedule_enabled_still_applies(self):
        now = datetime(2026, 6, 19, 20, 45, tzinfo=UTC)
        config = {
            "damage_preflight_minutes": 15,
            "base_damage_state": "on",
            "container_damage_state": "on",
            "damage_schedule": {
                "enabled": True,
                "base_state": "on",
                "container_state": "on",
                "first_date": "2026-06-19",
                "time": "21:00",
                "timezone": "UTC",
                "interval_value": 7,
                "interval_unit": "days",
            },
        }

        results = self.bot.apply_due_damage_schedule("guild-1", config, now)

        self.assertIsNotNone(results)
        self.assertTrue(config["damage_schedule_enabled"])
        self.assertEqual(["raid_damage_on"], [item["schedule_label"] for item in results])
        self.assertEqual([("guild-1", "on", "on")], self.upload_calls)

    def test_weekday_only_damage_schedule_applies_without_first_date(self):
        now = datetime(2026, 6, 19, 20, 45, tzinfo=UTC)
        config = {
            "damage_preflight_minutes": 15,
            "base_damage_state": "on",
            "container_damage_state": "on",
            "damage_schedule_enabled": True,
            "damage_schedule": {
                "enabled": True,
                "base_state": "on",
                "container_state": "on",
                "first_date": "",
                "time": "21:00",
                "timezone": "UTC",
                "interval_value": 7,
                "interval_unit": "days",
                "day_of_week": "friday",
            },
        }

        results = self.bot.apply_due_damage_schedule("guild-1", config, now)

        self.assertIsNotNone(results)
        self.assertEqual(["raid_damage_on"], [item["schedule_label"] for item in results])
        self.assertEqual([("guild-1", "on", "on")], self.upload_calls)

    def test_scheduler_status_heartbeat_and_error_are_recorded(self):
        now = datetime(2026, 6, 19, 20, 45, tzinfo=UTC)
        config = {}

        self.assertTrue(self.bot.mark_server_control_scheduler_status(config, now))
        self.assertEqual(now.isoformat(), config["server_control_scheduler_status"]["last_checked_at"])
        self.assertFalse(self.bot.mark_server_control_scheduler_status(config, now))

        later = datetime(2026, 6, 19, 20, 51, tzinfo=UTC)
        self.assertTrue(self.bot.mark_server_control_scheduler_status(config, later, "boom"))
        self.assertEqual(later.isoformat(), config["server_control_scheduler_status"]["last_checked_at"])
        self.assertEqual("boom", config["server_control_scheduler_status"]["last_error"])

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
