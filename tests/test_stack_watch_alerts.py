from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime
from unittest import mock


sys.path.insert(0, os.path.dirname(__file__))

from _bot_loader import import_bot_module


bot = import_bot_module()


class _CaptureChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return mock.Mock(id=123)


class StackWatchAlertTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.recent_stack_watch_placements.clear()
        bot.recent_stack_watch_alerts.clear()

    def test_server_identity_includes_profile_platform_and_map(self):
        identity = bot.stack_watch_server_identity(
            "guild-1:sakhal",
            {
                "profile_name": "W.A.C SAKHAL+PVE",
                "server_platform": "playstation",
                "server_map": "sakhal",
                "_server_profile_id": "sakhal",
            },
        )

        self.assertIn("W.A.C SAKHAL+PVE", identity)
        self.assertIn("PlayStation", identity)
        self.assertIn("Sakhal", identity)
        self.assertIn("profile `sakhal`", identity)

    async def test_stack_watch_embed_names_the_exact_dayz_server(self):
        channel = _CaptureChannel()
        config = {
            "profile_name": "W.A.C CHERNO+PVE",
            "server_platform": "xbox",
            "server_map": "chernarus",
            "_server_profile_id": "cherno",
            "channels": {"admin_logs": "123"},
            "stack_watch": {
                "enabled": True,
                "objects": ["Fireplace"],
                "alert_each_watched": True,
                "min_count": 2,
                "window_seconds": 180,
                "radius_meters": 8,
                "action": "notify",
            },
        }

        with mock.patch.object(bot, "extract_placed_object", return_value="Fireplace"), mock.patch.object(
            bot, "extract_adm_coords", return_value="6588.0, 7003.9, 2.3"
        ), mock.patch.object(bot, "parse_adm_xyz", return_value=(6588.0, 7003.9, 2.3)), mock.patch.object(
            bot, "extract_player_name", return_value="Toadmatey"
        ), mock.patch.object(bot, "discord_guild_for_runtime_id", return_value=mock.Mock()), mock.patch.object(
            bot.bot, "get_channel", return_value=channel
        ), mock.patch.object(bot, "build_izurvive_link", return_value=None), mock.patch.object(
            bot, "StackWatchActionView", return_value=mock.Mock()
        ):
            await bot.check_stack_watch_for_adm(
                "1491521072275788040:cherno",
                config,
                "placed",
                '21:37:55 | Player "Toadmatey" placed Fireplace',
                event_time=datetime(2026, 8, 12, 20, 37, 55, tzinfo=UTC),
            )

        self.assertEqual(1, len(channel.sent))
        embed = channel.sent[0]["embed"]
        fields = {field.name: field.value for field in embed.fields}
        self.assertIn("DayZ Server", fields)
        self.assertIn("W.A.C CHERNO+PVE", fields["DayZ Server"])
        self.assertIn("Xbox", fields["DayZ Server"])
        self.assertIn("Chernarus", fields["DayZ Server"])
        self.assertIn("profile `cherno`", fields["DayZ Server"])


if __name__ == "__main__":
    unittest.main()
