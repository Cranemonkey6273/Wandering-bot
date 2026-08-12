from __future__ import annotations

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class FakeResponse:
    def __init__(self):
        self.done = False
        self.deferred = []
        self.messages = []

    def is_done(self):
        return self.done

    async def defer(self, **kwargs):
        self.done = True
        self.deferred.append(kwargs)

    async def send_message(self, **kwargs):
        self.done = True
        self.messages.append(kwargs)


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.guild = SimpleNamespace(id=123)
        self.user = SimpleNamespace(id=456)
        self.channel = SimpleNamespace(id=789)
        self.command = SimpleNamespace(name="buy")


class LegacySlashAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_legacy_command_is_deferred_before_callback(self):
        interaction = FakeInteraction()
        callback_started_after_defer = False

        async def callback(_ctx, **_kwargs):
            nonlocal callback_started_after_defer
            callback_started_after_defer = interaction.response.done
            await asyncio.sleep(0)

        command = SimpleNamespace(callback=callback)
        with patch.object(bot.bot, "get_command", return_value=command):
            await bot.run_legacy_as_slash(interaction, "buy", item_name="NailBox")

        self.assertTrue(callback_started_after_defer)
        self.assertEqual(
            [{"ephemeral": True, "thinking": True}],
            interaction.response.deferred,
        )

    async def test_legacy_exception_returns_followup_instead_of_timing_out(self):
        interaction = FakeInteraction()

        async def callback(_ctx, **_kwargs):
            raise RuntimeError("simulated shop route failure")

        command = SimpleNamespace(callback=callback)
        with patch.object(bot.bot, "get_command", return_value=command):
            await bot.run_legacy_as_slash(interaction, "buy")

        self.assertEqual(1, len(interaction.response.deferred))
        self.assertEqual(1, len(interaction.followup.messages))
        message = interaction.followup.messages[0]
        self.assertTrue(message["ephemeral"])
        self.assertIn("could not complete", message["content"])
        self.assertIn("delivery-preparation failures are rolled back", message["content"])


if __name__ == "__main__":
    unittest.main()
