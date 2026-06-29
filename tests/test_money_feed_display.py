from __future__ import annotations

import asyncio
import unittest

from tests._bot_loader import import_bot_module


class FakeMember:
    id = 1413925686267084863
    display_name = "CraneMonkey"
    global_name = ""
    name = "cranemonkey"


class FakeRole:
    name = "Trader Admin"


class FakeGuild:
    def get_member(self, member_id):
        return FakeMember() if int(member_id) == FakeMember.id else None

    async def fetch_member(self, member_id):
        return FakeMember() if int(member_id) == FakeMember.id else None

    def get_role(self, role_id):
        return FakeRole() if int(role_id) == 149182610664218715 else None


class MoneyFeedDisplayTests(unittest.TestCase):
    def setUp(self):
        self.bot = import_bot_module()

    def test_money_feed_display_replaces_user_mentions_with_names(self):
        text = asyncio.run(
            self.bot.money_feed_display_text(
                FakeGuild(),
                "<@1413925686267084863> earned **205 pennies** cash.",
            )
        )

        self.assertEqual("CraneMonkey earned **205 pennies** cash.", text)

    def test_money_feed_display_replaces_escaped_mentions_and_roles(self):
        text = asyncio.run(
            self.bot.money_feed_display_text(
                FakeGuild(),
                "<@\u200b1413925686267084863> can use <@&149182610664218715>.",
            )
        )

        self.assertEqual("CraneMonkey can use @Trader Admin.", text)


if __name__ == "__main__":
    unittest.main()
