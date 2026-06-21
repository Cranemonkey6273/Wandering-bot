from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class FakeChannel:
    def __init__(self, name, channel_id):
        self.name = name
        self.id = channel_id


class FakeCategory:
    def __init__(self, name):
        self.name = name


class FakeGuild:
    def __init__(self, channels):
        self.text_channels = channels


class ChannelMatchingTests(unittest.TestCase):
    def test_nitrado_ban_feed_matches_decorated_renamed_original(self):
        channel = FakeChannel("nitrado-ban", 100)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "nitrado_ban_logs"))

    def test_nitrado_ban_feed_prefers_decorated_original_over_plain_duplicate(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])

        self.assertIs(bot.preferred_existing_feed_channel(guild, "nitrado_ban_logs"), original)

    def test_radar_channel_matches_plain_radars(self):
        channel = FakeChannel("Radars", 300)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "radar"))

    def test_radar_category_matches_plain_radars(self):
        category = FakeCategory("Radars")

        self.assertTrue(bot.category_matches_bot_spec(category, "radar_pings"))


if __name__ == "__main__":
    unittest.main()
