from __future__ import annotations

import pathlib
import re
import unittest


BOT_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "bot.py"


class DiscordCommandLimitTests(unittest.TestCase):
    def test_global_slash_command_limit_is_not_exceeded(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")
        direct_commands = len(re.findall(r"@bot\.tree\.command\b", text))
        top_level_groups = len(re.findall(r"bot\.tree\.add_command\(", text))

        self.assertLessEqual(direct_commands + top_level_groups, 100)

    def test_tools_group_child_limit_is_not_exceeded(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")
        tools_children = len(re.findall(r"@extra_tools_group\.command\b", text))

        self.assertLessEqual(tools_children, 25)

    def test_retired_showcase_command_is_not_registered(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")

        self.assertNotRegex(
            text,
            r"@bot\.tree\.command\(name=[\"']ownerbotshowcase[\"']",
        )


if __name__ == "__main__":
    unittest.main()
