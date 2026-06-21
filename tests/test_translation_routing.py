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


if __name__ == "__main__":
    unittest.main()
