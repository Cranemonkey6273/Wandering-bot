from __future__ import annotations

import asyncio
import inspect
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
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

    def test_restart_schedule_has_a_bounded_catch_up_window(self):
        due = self.bot._restart_schedule_due_slot(datetime(2026, 7, 1, 13, 7, tzinfo=UTC), 1, 4, 10)

        self.assertEqual(datetime(2026, 7, 1, 13, 0, tzinfo=UTC), due)
        self.assertIsNone(self.bot._restart_schedule_due_slot(datetime(2026, 7, 1, 13, 11, tzinfo=UTC), 1, 4, 10))
        self.assertIsNone(self.bot._restart_schedule_due_slot(datetime(2026, 7, 1, 14, 2, tzinfo=UTC), 1, 4, 10))

    def test_scheduled_restart_proceeds_when_discord_channel_is_unavailable(self):
        class Response:
            status_code = 202

        config = {
            "nitrado_token": "test-token",
            "service_id": "1234567",
            "restart_timezone": "UTC",
        }
        now = datetime(2026, 7, 1, 13, 4, tzinfo=UTC)
        with patch.object(self.bot, "nitrado_restart_headers_or_error", return_value=({"Authorization": "Bearer test"}, "")), \
             patch.object(self.bot, "prepare_delivery_xml_before_restart", new=AsyncMock(return_value=(True, False, "No paid work."))), \
             patch.object(self.bot.requests, "post", return_value=Response()) as restart_post, \
             patch.object(self.bot, "save_guild_configs_for_runtime"), \
             patch.object(self.bot, "publish_restart_history", new=AsyncMock()), \
             patch.object(self.bot, "clear_online_state_for_restart", return_value=False):
            ok = asyncio.run(self.bot.request_scheduled_restart_without_discord_channel("guild-1", config, now, 13))

        self.assertTrue(ok)
        restart_post.assert_called_once()
        self.assertEqual("requested", config["restart_history"][0]["status"])
        self.assertIn("without a Discord announcement channel", config["restart_history"][0]["details"])

    def test_scheduled_restart_is_blocked_before_nitrado_when_paid_delivery_is_unsafe(self):
        config = {
            "nitrado_token": "test-token",
            "service_id": "1234567",
            "restart_timezone": "UTC",
        }
        now = datetime(2026, 7, 1, 13, 4, tzinfo=UTC)
        with patch.object(
            self.bot,
            "prepare_delivery_xml_before_restart",
            new=AsyncMock(return_value=(False, True, "Paid delivery upload failed; queue preserved.")),
        ), patch.object(self.bot.requests, "post") as restart_post, patch.object(
            self.bot, "save_guild_configs_for_runtime"
        ), patch.object(
            self.bot, "publish_restart_history", new=AsyncMock()
        ):
            ok = asyncio.run(
                self.bot.request_scheduled_restart_without_discord_channel("guild-1", config, now, 13)
            )

        self.assertFalse(ok)
        restart_post.assert_not_called()
        self.assertEqual("blocked", config["restart_history"][0]["status"])
        self.assertIn("queue preserved", config["restart_history"][0]["details"])

    def test_routine_restart_never_reuploads_native_console_ce_files(self):
        source = "\n".join((
            inspect.getsource(self.bot.scheduled_restart_loop.coro),
            inspect.getsource(self.bot.restart_delivery_processor.coro),
        ))

        self.assertNotIn("upload_console_ce_event_files", source)

    def test_all_restart_processors_use_the_paid_delivery_safety_gate(self):
        scheduled_source = inspect.getsource(self.bot.scheduled_restart_loop.coro)
        delivery_source = inspect.getsource(self.bot.restart_delivery_processor.coro)

        self.assertIn("prepare_delivery_xml_before_restart", scheduled_source)
        self.assertIn("prepare_delivery_xml_before_restart", delivery_source)
        self.assertNotIn("write_and_upload_delivery_xml", delivery_source)

    def test_restart_warning_is_persisted_and_removed_from_its_original_channel(self):
        class Message:
            deleted = False

            async def delete(self):
                self.deleted = True

        class Channel:
            id = 321

            def __init__(self, message):
                self.message = message
                self.requested_ids = []

            async def fetch_message(self, message_id):
                self.requested_ids.append(message_id)
                return self.message

        config = {"_is_server_profile_runtime": False}
        message = Message()
        channel = Channel(message)
        self.bot.last_restart_countdown_message_ids.clear()

        with patch.object(self.bot, "save_guild_configs_for_runtime") as save_config, \
             patch.object(self.bot.bot, "get_channel", return_value=channel):
            self.bot.remember_restart_countdown_message("guild-1", config, channel.id, 987)
            removed = asyncio.run(self.bot.delete_pending_restart_countdown("guild-1", config))

        self.assertTrue(removed)
        self.assertEqual([987], channel.requested_ids)
        self.assertTrue(message.deleted)
        self.assertNotIn("restart_countdown_message", config)
        self.assertNotIn("guild-1", self.bot.last_restart_countdown_message_ids)
        self.assertGreaterEqual(save_config.call_count, 2)
        self.assertIn("restart_countdown_message", self.bot.SERVER_PROFILE_PERSIST_KEYS)

    def test_nitrado_token_reports_hidden_lookalike_character(self):
        ok, _token, message = self.bot.validate_nitrado_api_token("\u0435abc123")

        self.assertFalse(ok)
        self.assertIn("U+0435", message)
        self.assertIn("position 1", message)

    def test_nitrado_headers_reject_hidden_token_before_request(self):
        headers, message = self.bot.nitrado_api_headers_or_error({"nitrado_token": "\u0435abc123"})

        self.assertIsNone(headers)
        self.assertIn("U+0435", message)

    def test_nitrado_status_reports_hidden_token_without_request(self):
        original_get = self.bot.requests.get

        def fail_get(*_args, **_kwargs):
            raise AssertionError("Nitrado status should not make a request with a bad token")

        self.bot.requests.get = fail_get
        try:
            ok, message = self.bot.nitrado_gameserver_status({
                "nitrado_token": "\u0435abc123",
                "service_id": "1234567",
            })
        finally:
            self.bot.requests.get = original_get

        self.assertFalse(ok)
        self.assertIn("U+0435", message)

    def test_pc_connection_prefers_battleye_rcon_when_complete(self):
        config = {
            "server_platform": "pc",
            "rcon_host": "203.0.113.10",
            "rcon_port": "2312",
            "rcon_password": "secret",
        }

        self.assertEqual("battlEye_rcon_then_nitrado", self.bot.dayz_connection_preference(config))
        self.assertEqual(
            {"host": "203.0.113.10", "port": 2312, "password": "secret"},
            self.bot.battleye_rcon_settings(config),
        )

    def test_rcon_is_not_selected_for_console_servers(self):
        config = {
            "server_platform": "xbox",
            "rcon_host": "203.0.113.10",
            "rcon_port": "2312",
            "rcon_password": "secret",
        }

        self.assertIsNone(self.bot.battleye_rcon_settings(config))
        self.assertEqual("nitrado_api_ftp", self.bot.dayz_connection_preference(config))

    def test_pc_status_uses_rcon_before_nitrado_api(self):
        config = {
            "server_platform": "pc",
            "rcon_host": "203.0.113.10",
            "rcon_port": "2312",
            "rcon_password": "secret",
            "nitrado_token": "bad-token-not-used",
            "service_id": "1234567",
        }

        with patch.object(self.bot, "battleye_rcon_command_sync", return_value=(True, "Players on server: 0")):
            with patch.object(self.bot.requests, "get", side_effect=AssertionError("Nitrado should not be queried after RCon succeeds")):
                ok, message = self.bot.nitrado_gameserver_status(config)

        self.assertTrue(ok)
        self.assertIn("BattlEye RCon online", message)

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
