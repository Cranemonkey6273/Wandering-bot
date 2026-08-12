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

    def test_console_group_child_limit_is_not_exceeded(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")
        console_children = len(re.findall(r"@console_group\.command\b", text))

        self.assertGreater(console_children, 0)
        self.assertLessEqual(console_children, 25)

    def test_console_setup_group_is_public(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")

        self.assertRegex(
            text,
            r"@console_group\.command\(name=[\"']setupobjects[\"']",
        )
        hidden_groups = re.search(
            r"HIDDEN_SLASH_GROUPS\s*=\s*(.*?)(?:\n\n|HIDDEN_GROUP_SUBCOMMANDS)",
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(hidden_groups)
        self.assertNotIn('"console"', hidden_groups.group(1))
        self.assertNotIn("'console'", hidden_groups.group(1))

    def test_console_setupobjects_hides_technical_path_options(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")
        command = re.search(
            r"@console_group\.command\(name=[\"']setupobjects[\"'].*?\nasync def console_setupobjects\((.*?)\n\):",
            text,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(command)
        signature = command.group(1)
        self.assertIn("upload: bool", signature)
        self.assertNotIn("object_path", signature)
        self.assertNotIn("cfggameplay_path", signature)
        self.assertNotIn("spawner_ref", signature)

    def test_economy_currency_command_is_registered_with_supported_choices(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")
        command = re.search(
            r"@economy_group\.command\(name=[\"']currency[\"'].*?"
            r"async def slash_economycurrency\(.*?\n\s*\)",
            text,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(command)
        command_text = command.group(0)
        for currency in ("pennies", "euros", "pounds", "dollars"):
            self.assertIn(f'value="{currency}"', command_text)
        self.assertIn("@app_commands.default_permissions(administrator=True)", command_text)

    def test_retired_showcase_command_is_not_registered(self):
        text = BOT_SOURCE.read_text(encoding="utf-8")

        self.assertNotRegex(
            text,
            r"@bot\.tree\.command\(name=[\"']ownerbotshowcase[\"']",
        )


if __name__ == "__main__":
    unittest.main()
