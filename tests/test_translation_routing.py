"""Regression tests for same-channel bidirectional translation routing."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class TranslationLanguageGuardTests(unittest.TestCase):
    def test_english_message_matches_en_to_de_only(self):
        text = "Hahaha see you are just loosing your mind"

        detected, _score = bot.detect_translation_language_hint(text)
        self.assertEqual(detected, "en")
        self.assertEqual(bot.translation_source_matches_text(text, "en", "de"), (True, ""))

        matches, reason = bot.translation_source_matches_text(text, "de", "en")
        self.assertFalse(matches)
        self.assertIn("detected en", reason)

    def test_german_message_matches_de_to_en_only(self):
        text = "Hahaha, siehst du, du verlierst einfach den Verstand!"

        detected, _score = bot.detect_translation_language_hint(text)
        self.assertEqual(detected, "de")
        self.assertEqual(bot.translation_source_matches_text(text, "de", "en"), (True, ""))

        matches, reason = bot.translation_source_matches_text(text, "en", "de")
        self.assertFalse(matches)
        self.assertIn("detected de", reason)

    def test_screenshot_english_slang_does_not_back_translate(self):
        text = "scared the shit outa me LOL"

        detected, _score = bot.detect_translation_language_hint(text)
        self.assertEqual(detected, "en")
        self.assertEqual(bot.translation_source_matches_text(text, "en", "de"), (True, ""))

        matches, reason = bot.translation_source_matches_text(text, "de", "en")
        self.assertFalse(matches)
        self.assertIn("detected en", reason)

    def test_stretched_english_chat_does_not_back_translate(self):
        text = "Allllll is gooood!"

        detected, _score = bot.detect_translation_language_hint(text)
        self.assertEqual(detected, "en")
        self.assertEqual(bot.translation_source_matches_text(text, "en", "de"), (True, ""))

        matches, reason = bot.translation_source_matches_text(text, "de", "en")
        self.assertFalse(matches)
        self.assertIn("detected en", reason)

    def test_screenshot_german_slang_does_not_echo_to_german(self):
        text = "Mhh ok sieht sehr Haftig!"

        detected, _score = bot.detect_translation_language_hint(text)
        self.assertEqual(detected, "de")
        self.assertEqual(bot.translation_source_matches_text(text, "de", "en"), (True, ""))

        matches, reason = bot.translation_source_matches_text(text, "en", "de")
        self.assertFalse(matches)
        self.assertIn("detected de", reason)

    def test_auto_source_still_allows_detection_by_provider(self):
        self.assertEqual(
            bot.translation_source_matches_text("ok lol", "auto", "de"),
            (True, ""),
        )


class _FakeAuthor:
    id = 42
    bot = False
    webhook_id = None
    display_name = "Admin"
    mention = "@Admin"
    display_avatar = None

    def __str__(self):
        return "Admin"


class _FakeChannel:
    def __init__(self, channel_id, name="chat"):
        self.id = channel_id
        self.name = name
        self.mention = f"<#{channel_id}>"
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class _FakeGuild:
    def __init__(self, guild_id, channels):
        self.id = guild_id
        self._channels = channels

    def get_channel(self, channel_id):
        return self._channels.get(channel_id)


class _FakeMessage:
    def __init__(self, guild, channel, content):
        self.guild = guild
        self.channel = channel
        self.content = content
        self.author = _FakeAuthor()
        self.webhook_id = None


class TranslationBatchingTests(unittest.IsolatedAsyncioTestCase):
    def test_batch_embed_payload_keeps_original_then_languages(self):
        payload = bot.translation_batch_embed_payload(
            "Hello everyone, raid weekend starts tonight.",
            [
                {"target_language": "de", "used_source": "en", "translated": "Hallo zusammen."},
                {"target_language": "fr", "used_source": "en", "translated": "Bonjour tout le monde."},
            ],
        )

        self.assertEqual(payload["title"], "Multi-language translation")
        self.assertEqual([field["name"] for field in payload["fields"][:3]], [
            "Original",
            "German (EN -> DE)",
            "French (EN -> FR)",
        ])

    async def test_multiple_rules_to_same_channel_send_one_embed(self):
        guild_id = "987654321"
        source_channel = _FakeChannel(10, "general")
        target_channel = _FakeChannel(20, "translations")
        guild = _FakeGuild(guild_id, {20: target_channel})
        message = _FakeMessage(guild, source_channel, "Hello everyone this is good and we can go today")

        old_config = bot.guild_configs.get(guild_id)
        old_translate = bot.translate_text
        bot.guild_configs[guild_id] = {
            "translations": [
                {"enabled": True, "mode": "channel", "source_language": "en", "target_language": "de", "target_channel_id": 20},
                {"enabled": True, "mode": "channel", "source_language": "en", "target_language": "fr", "target_channel_id": 20},
            ]
        }

        async def fake_translate(text, target_language="en", source_language="auto"):
            return f"{target_language}:{text}"

        bot.translate_text = fake_translate
        try:
            await bot.maybe_translate_message(message)
        finally:
            bot.translate_text = old_translate
            if old_config is None:
                bot.guild_configs.pop(guild_id, None)
            else:
                bot.guild_configs[guild_id] = old_config

        self.assertEqual(len(target_channel.sent), 1)
        self.assertIn("embed", target_channel.sent[0])

    async def test_same_channel_rules_send_one_reply_embed(self):
        guild_id = "123456789"
        source_channel = _FakeChannel(30, "chat")
        guild = _FakeGuild(guild_id, {30: source_channel})
        message = _FakeMessage(guild, source_channel, "Hello everyone this is good and we can go today")

        old_config = bot.guild_configs.get(guild_id)
        old_translate = bot.translate_text
        old_mentions_none = getattr(bot.discord.AllowedMentions, "none", None)
        bot.discord.AllowedMentions.none = staticmethod(lambda: None)
        bot.guild_configs[guild_id] = {
            "translations": [
                {"enabled": True, "mode": "same", "source_language": "en", "target_language": "de"},
                {"enabled": True, "mode": "same", "source_language": "en", "target_language": "fr"},
            ]
        }

        async def fake_translate(text, target_language="en", source_language="auto"):
            return f"{target_language}:{text}"

        bot.translate_text = fake_translate
        try:
            await bot.maybe_translate_message(message)
        finally:
            bot.translate_text = old_translate
            if old_mentions_none is None:
                delattr(bot.discord.AllowedMentions, "none")
            else:
                bot.discord.AllowedMentions.none = old_mentions_none
            if old_config is None:
                bot.guild_configs.pop(guild_id, None)
            else:
                bot.guild_configs[guild_id] = old_config

        self.assertEqual(len(source_channel.sent), 1)
        self.assertIs(source_channel.sent[0].get("reference"), message)
        self.assertFalse(source_channel.sent[0].get("mention_author"))


if __name__ == "__main__":
    unittest.main()
