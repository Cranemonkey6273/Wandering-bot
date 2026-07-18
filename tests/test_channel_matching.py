from __future__ import annotations

import os
import sys
import asyncio
import inspect
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from _bot_loader import import_bot_module  # noqa: E402

bot = import_bot_module()


class FakeRole:
    def __init__(self, name, role_id):
        self.name = name
        self.id = role_id
        self.position = int(role_id) if str(role_id).isdigit() else 1
        self.managed = False


class FakeMember:
    def __init__(self, roles=None, member_id=555):
        self.roles = roles or []
        self.id = member_id
        self.bot = False
        self.guild = None
        self.mention = f"<@{member_id}>"
        self.top_role = self.roles[-1] if self.roles else FakeRole("@everyone", 0)
        self.added_roles = []
        self.removed_roles = []

    async def add_roles(self, role, **_kwargs):
        self.added_roles.append(role)
        if role not in self.roles:
            self.roles.append(role)
            self.top_role = role

    async def remove_roles(self, role, **_kwargs):
        self.removed_roles.append(role)
        self.roles = [existing for existing in self.roles if str(existing.id) != str(role.id)]
        self.top_role = self.roles[-1] if self.roles else FakeRole("@everyone", 0)


class FakeChannel:
    def __init__(self, name, channel_id, category=None):
        self.name = name
        self.id = channel_id
        self.category = category
        self.category_id = getattr(category, "id", None)
        self.edit_calls = []

    async def edit(self, **kwargs):
        self.edit_calls.append(kwargs)
        if "name" in kwargs:
            self.name = kwargs["name"]
        if "category" in kwargs:
            self.category = kwargs["category"]
            self.category_id = getattr(kwargs["category"], "id", None)
        return self


class FakeCategory:
    def __init__(self, name, category_id=0):
        self.name = name
        self.id = category_id


class FakeFooter:
    def __init__(self, text=""):
        self.text = text


class FakeEmbed:
    def __init__(self, footer_text=""):
        self.footer = FakeFooter(footer_text)
        self.timestamp = None

    def set_footer(self, *, text=None, **_kwargs):
        self.footer = FakeFooter(text or "")
        return self


class FakeSendChannel:
    def __init__(self):
        self.sent = []
        self.id = 123
        self.name = "test-feed"

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return type("SentMessage", (), {"id": 123})()


class FakeReactionMessage:
    def __init__(self, message_id):
        self.id = int(message_id)
        self.reactions = []
        self.embeds = []
        self.content = "Configured onboarding message"
        self.jump_url = f"https://discord.test/messages/{message_id}"
        self.added_reactions = []

    async def add_reaction(self, emoji):
        self.added_reactions.append(str(emoji))


class FakeFetchChannel:
    def __init__(self, name, channel_id, messages):
        self.name = name
        self.id = int(channel_id)
        self._messages = {int(message.id): message for message in messages}
        self.sent = []

    async def fetch_message(self, message_id):
        return self._messages[int(message_id)]

    def permissions_for(self, _member):
        return type("Perms", (), {"send_messages": True})()

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return type("SentMessage", (), {"id": 999})()


class FakeOnboardingGuild:
    def __init__(self, channels, roles=None, member=None):
        self.channels = {int(channel.id): channel for channel in channels}
        self.text_channels = list(channels)
        self.roles = {int(role.id): role for role in (roles or [])}
        self.member = member
        self.id = 1234
        self.owner_id = 1
        self.me = FakeMember([FakeRole("Bot", 999999)], member_id=999)
        self.me.guild = self

    def get_channel(self, channel_id):
        return self.channels.get(int(channel_id))

    def get_role(self, role_id):
        return self.roles.get(int(role_id))

    def get_member(self, member_id):
        if self.member and int(self.member.id) == int(member_id):
            return self.member
        return None

    async def fetch_member(self, member_id):
        member = self.get_member(member_id)
        if member:
            return member
        raise RuntimeError("member not found")


class FakeReactionPayload:
    def __init__(self, *, message_id=222, channel_id=20, user_id=555, emoji="🔵"):
        self.guild_id = 1234
        self.message_id = int(message_id)
        self.channel_id = int(channel_id)
        self.user_id = int(user_id)
        self.emoji = emoji


class FlakySendChannel(FakeSendChannel):
    def __init__(self, failures=1, status=503):
        super().__init__()
        self.failures = failures
        self.status = status
        self.attempts = 0

    async def send(self, **kwargs):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise bot.discord.HTTPException("temporary Discord failure", status=self.status)
        return await super().send(**kwargs)


class FakeGuild:
    def __init__(self, channels, guild_id="guild-a", name="Guild A"):
        self.text_channels = channels
        self.id = guild_id
        self.name = name
        self.owner = "owner"

    def get_channel(self, channel_id):
        for channel in self.text_channels:
            if channel.id == channel_id:
                return channel
        return None


class FakeInteractionResponse:
    def __init__(self):
        self.deferred = False

    async def defer(self, **_kwargs):
        self.deferred = True


class FakeInteractionFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append((args, kwargs))


class FakeInteraction:
    def __init__(self, guild, channel, user=None):
        self.guild = guild
        self.channel = channel
        self.user = user or FakeMember([])
        self.response = FakeInteractionResponse()
        self.followup = FakeInteractionFollowup()


class ChannelMatchingTests(unittest.TestCase):
    def test_style_embed_replaces_legacy_alpha_footer(self):
        embed = FakeEmbed("Wandering Bot Alpha - Disconnect Feed")

        bot.style_embed(embed)

        self.assertEqual(bot.POWERED_BY_FOOTER_TEXT, embed.footer.text)

    def test_send_feed_embed_replaces_legacy_alpha_footer_without_style_flag(self):
        embed = FakeEmbed("Wandering Bot Alpha - Disconnect Feed")
        channel = FakeSendChannel()

        asyncio.run(bot.send_feed_embed("guild-1", "disconnects", channel, embed, context="disconnect"))

        self.assertEqual(bot.POWERED_BY_FOOTER_TEXT, channel.sent[0]["embed"].footer.text)

    def test_send_feed_embed_retries_transient_discord_failure(self):
        channel = FlakySendChannel(failures=1, status=503)

        async def run():
            with mock.patch.object(bot.asyncio, "sleep", new_callable=mock.AsyncMock):
                return await bot.send_feed_embed(
                    "guild-1",
                    "connections",
                    channel,
                    FakeEmbed(),
                    context="connect",
                )

        message = asyncio.run(run())

        self.assertIsNotNone(message)
        self.assertEqual(2, channel.attempts)
        self.assertEqual(1, len(channel.sent))

    def test_send_feed_embed_does_not_retry_permanent_discord_http_failure(self):
        channel = FlakySendChannel(failures=3, status=400)

        async def run():
            with mock.patch.object(bot.asyncio, "sleep", new_callable=mock.AsyncMock) as sleep:
                message = await bot.send_feed_embed(
                    "guild-1",
                    "connections",
                    channel,
                    FakeEmbed(),
                    context="connect",
                )
                sleep.assert_not_awaited()
                return message

        self.assertIsNone(asyncio.run(run()))
        self.assertEqual(1, channel.attempts)

    def test_core_presence_feed_survives_optional_dashboard_failure(self):
        guild_id = "guild-presence"
        channel = FakeSendChannel()
        bot.ensure_guild_runtime(guild_id)
        bot.online_players[guild_id] = {"PaleSr8"}

        async def run():
            with mock.patch.object(
                bot,
                "upsert_online_dashboard_message",
                new=mock.AsyncMock(side_effect=RuntimeError("optional dashboard failure")),
            ):
                return await bot.send_core_adm_presence_feed(
                    guild_id,
                    {},
                    "connect",
                    "PaleSr8",
                    bot.datetime.now(bot.UTC),
                    channel,
                )

        self.assertTrue(asyncio.run(run()))
        self.assertEqual(1, len(channel.sent))

    def test_parse_adm_delivers_presence_before_optional_processing(self):
        source = inspect.getsource(bot.parse_adm)
        presence_index = source.index("presence_sent = await send_core_adm_presence_feed")

        self.assertLess(presence_index, source.index('print(f"EVENT:', presence_index))
        self.assertLess(presence_index, source.index("schedule_link_enforcement_check", presence_index))
        self.assertLess(presence_index, source.index("note_player_alive", presence_index))

    def test_adm_parse_tail_window_is_configurable_above_old_limit(self):
        self.assertGreaterEqual(bot.adm_parse_tail_line_count(), 2000)
        with mock.patch.dict(os.environ, {"WANDERING_ADM_PARSE_TAIL_LINES": "500"}, clear=False):
            self.assertEqual(500, bot.adm_parse_tail_line_count())
        with mock.patch.dict(os.environ, {"WANDERING_ADM_PARSE_TAIL_LINES": "10"}, clear=False):
            self.assertEqual(250, bot.adm_parse_tail_line_count())

    def test_onboarding_repair_adds_rules_and_choice_reactions(self):
        rules_message = FakeReactionMessage(111)
        choice_message = FakeReactionMessage(222)
        rules_channel = FakeFetchChannel("rules", 10, [rules_message])
        choice_channel = FakeFetchChannel("pick-server", 20, [choice_message])
        guild = FakeOnboardingGuild([rules_channel, choice_channel])
        config = {
            "member_onboarding": {
                "enabled": True,
                "rules_channel_id": "10",
                "rules_message_id": "111",
                "reaction_emoji": "✅",
                "choice_channel_id": "20",
                "choice_message_id": "222",
                "choice_cherno_emoji": "🔴",
                "choice_cherno_role_id": "101",
                "choice_livo_emoji": "🔵",
                "choice_livo_role_id": "102",
                "choice_bot_emoji": "🤖",
                "choice_bot_role_id": "103",
            },
        }

        repaired = asyncio.run(bot.repair_member_onboarding_reactions_for_guild(guild, config))

        self.assertTrue(repaired)
        self.assertIn("✅", rules_message.added_reactions)
        self.assertEqual(["🔴", "🔵", "🤖"], choice_message.added_reactions)

    def test_onboarding_choice_welcome_refuses_feed_or_event_channel(self):
        event_channel = FakeFetchChannel("LiVo-eVeNt-sPAWNs", 30, [])
        guild = FakeOnboardingGuild([event_channel])
        config = {
            "member_onboarding": {
                "enabled": True,
                "choice_livo_welcome_channel_id": "30",
            }
        }
        settings = bot.member_onboarding_settings(config)

        channel = bot.resolve_onboarding_choice_welcome_channel(
            guild,
            config,
            settings,
            {"key": "livo", "label": "Livo"},
        )

        self.assertIsNone(channel)

    def test_onboarding_choice_welcome_finds_matching_safe_channel(self):
        event_channel = FakeFetchChannel("LiVo-eVeNt-sPAWNs", 30, [])
        welcome_channel = FakeFetchChannel("LiVo-welcome", 31, [])
        guild = FakeOnboardingGuild([event_channel, welcome_channel])
        config = {"member_onboarding": {"enabled": True}}
        settings = bot.member_onboarding_settings(config)

        channel = bot.resolve_onboarding_choice_welcome_channel(
            guild,
            config,
            settings,
            {"key": "livo", "label": "Livo"},
        )

        self.assertIs(channel, welcome_channel)

    def test_onboarding_choice_remove_bypasses_rules_gate(self):
        livo_role = FakeRole("Wandering Around Livo", 102)
        member = FakeMember([livo_role], member_id=555)
        guild = FakeOnboardingGuild(
            [FakeFetchChannel("pick-server", 20, [])],
            roles=[FakeRole("Rule Abider", 101), livo_role],
            member=member,
        )
        member.guild = guild
        config = {
            "member_onboarding": {
                "enabled": True,
                "choice_channel_id": "20",
                "choice_message_id": "222",
                "choice_require_rules": True,
                "rules_role_id": "101",
                "choice_livo_emoji": "🔵",
                "choice_livo_role_id": "102",
            }
        }

        handled = asyncio.run(
            bot.apply_member_onboarding_server_choice(
                guild,
                config,
                FakeReactionPayload(emoji="🔵"),
                remove=True,
            )
        )

        self.assertTrue(handled)
        self.assertEqual([livo_role], member.removed_roles)
        self.assertFalse(bot.member_has_role_id(member, "102"))

    def test_onboarding_rules_acceptance_reports_role_hierarchy_failure(self):
        rules_role = FakeRole("Rule Abider", 101)
        member = FakeMember([], member_id=555)
        next_channel = FakeFetchChannel("pick-server", 20, [])
        audit_channel = FakeFetchChannel("dashboard-audit", 99, [])
        guild = FakeOnboardingGuild(
            [next_channel, audit_channel],
            roles=[rules_role],
            member=member,
        )
        guild.me.top_role = FakeRole("Bot", 50)
        member.guild = guild
        config = {
            "channels": {"dashboard_audit": "99"},
            "member_onboarding": {
                "enabled": True,
                "rules_role_id": "101",
                "next_channel_id": "20",
            },
        }

        handled = asyncio.run(bot.apply_member_onboarding_rules_acceptance(guild, config, member))

        self.assertTrue(handled)
        self.assertFalse(bot.member_has_role_id(member, "101"))
        self.assertEqual(1, len(audit_channel.sent))
        self.assertEqual(0, len(next_channel.sent))

    def test_onboarding_choice_add_reports_role_hierarchy_failure_without_welcome(self):
        rules_role = FakeRole("Rule Abider", 101)
        livo_role = FakeRole("Wandering Around Livo", 102)
        member = FakeMember([rules_role], member_id=555)
        choice_channel = FakeFetchChannel("pick-server", 20, [])
        welcome_channel = FakeFetchChannel("LiVo-welcome", 31, [])
        audit_channel = FakeFetchChannel("dashboard-audit", 99, [])
        guild = FakeOnboardingGuild(
            [choice_channel, welcome_channel, audit_channel],
            roles=[rules_role, livo_role],
            member=member,
        )
        guild.me.top_role = FakeRole("Bot", 101)
        member.guild = guild
        config = {
            "channels": {"dashboard_audit": "99"},
            "member_onboarding": {
                "enabled": True,
                "choice_channel_id": "20",
                "choice_message_id": "222",
                "choice_require_rules": True,
                "rules_role_id": "101",
                "choice_livo_emoji": "ðŸ”µ",
                "choice_livo_role_id": "102",
                "choice_livo_welcome_channel_id": "31",
                "choice_livo_welcome_message": "Welcome to Livo.",
            },
        }

        handled = asyncio.run(
            bot.apply_member_onboarding_server_choice(
                guild,
                config,
                FakeReactionPayload(emoji="ðŸ”µ"),
                remove=False,
            )
        )

        self.assertTrue(handled)
        self.assertFalse(bot.member_has_role_id(member, "102"))
        self.assertEqual(1, len(audit_channel.sent))
        self.assertEqual(0, len(welcome_channel.sent))

    def test_onboarding_rules_remove_strips_dependent_roles(self):
        rules_role = FakeRole("Rule Abider", 101)
        linked_role = FakeRole("Linked Player", 104)
        pending_role = FakeRole("Pending", 105)
        livo_role = FakeRole("Wandering Around Livo", 102)
        member = FakeMember([rules_role, linked_role, livo_role], member_id=555)
        guild = FakeOnboardingGuild(
            [FakeFetchChannel("rules", 10, [])],
            roles=[rules_role, linked_role, pending_role, livo_role],
            member=member,
        )
        member.guild = guild
        config = {
            "member_onboarding": {
                "enabled": True,
                "rules_role_id": "101",
                "linked_role_id": "104",
                "pending_role_id": "105",
                "choice_require_rules": True,
                "choice_livo_role_id": "102",
                "require_rules_before_linked_role": True,
            }
        }

        handled = asyncio.run(bot.remove_member_onboarding_rules_acceptance(guild, config, member))

        self.assertTrue(handled)
        self.assertFalse(bot.member_has_role_id(member, "101"))
        self.assertFalse(bot.member_has_role_id(member, "102"))
        self.assertFalse(bot.member_has_role_id(member, "104"))
        self.assertTrue(bot.member_has_role_id(member, "105"))

    def test_rules_reaction_match_allows_variation_selector(self):
        guild = FakeOnboardingGuild([FakeFetchChannel("rules", 10, [])])
        config = {
            "member_onboarding": {
                "enabled": True,
                "rules_channel_id": "10",
                "rules_message_id": "111",
                "reaction_emoji": "\u2705",
            }
        }
        settings = bot.member_onboarding_settings(config)

        self.assertTrue(
            bot.payload_matches_onboarding_rules_reaction(
                guild,
                config,
                settings,
                FakeReactionPayload(message_id=111, channel_id=10, emoji="\u2705\ufe0f"),
            )
        )

    def test_onboarding_choice_add_posts_to_configured_welcome_channel(self):
        rules_role = FakeRole("Rule Abider", 101)
        livo_role = FakeRole("Wandering Around Livo", 102)
        member = FakeMember([rules_role], member_id=555)
        choice_channel = FakeFetchChannel("pick-server", 20, [])
        welcome_channel = FakeFetchChannel("LiVo-welcome", 31, [])
        guild = FakeOnboardingGuild(
            [choice_channel, welcome_channel],
            roles=[rules_role, livo_role],
            member=member,
        )
        member.guild = guild
        config = {
            "member_onboarding": {
                "enabled": True,
                "choice_channel_id": "20",
                "choice_message_id": "222",
                "choice_require_rules": True,
                "rules_role_id": "101",
                "choice_livo_emoji": "🔵",
                "choice_livo_role_id": "102",
                "choice_livo_welcome_channel_id": "31",
                "choice_livo_welcome_message": "Welcome to Livo.",
            }
        }

        handled = asyncio.run(
            bot.apply_member_onboarding_server_choice(
                guild,
                config,
                FakeReactionPayload(emoji="🔵"),
                remove=False,
            )
        )

        self.assertTrue(handled)
        self.assertTrue(bot.member_has_role_id(member, "102"))
        self.assertEqual(1, len(welcome_channel.sent))
        self.assertEqual(0, len(choice_channel.sent))

    def test_failed_adm_delivery_can_be_removed_from_both_dedupe_caches(self):
        guild_id = "guild-retry"
        line_hash = "line-hash"
        fingerprint = "event-fingerprint"
        bot.ensure_guild_runtime(guild_id)
        bot.processed_lines[guild_id][line_hash] = None
        bot.processed_adm_events[guild_id][fingerprint] = None

        with mock.patch.object(bot, "save_processed_adm_lines"), mock.patch.object(
            bot,
            "save_processed_adm_events",
        ):
            self.assertTrue(bot.forget_processed_line(guild_id, line_hash))
            self.assertTrue(bot.forget_processed_adm_event(guild_id, fingerprint))

        self.assertNotIn(line_hash, bot.processed_lines[guild_id])
        self.assertNotIn(fingerprint, bot.processed_adm_events[guild_id])

    def test_nitrado_ban_feed_matches_decorated_renamed_original(self):
        channel = FakeChannel("nitrado-ban", 100)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "nitrado_ban_logs"))

    def test_nitrado_ban_feed_prefers_decorated_original_over_plain_duplicate(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])

        self.assertIs(bot.preferred_existing_feed_channel(guild, "nitrado_ban_logs"), original)

    def test_discover_does_not_update_saved_route_without_explicit_auto_discovery(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])
        config = {"channels": {"nitrado_ban_logs": duplicate.id}}

        self.assertFalse(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["nitrado_ban_logs"], duplicate.id)

    def test_discover_updates_saved_route_when_auto_discovery_is_explicit(self):
        original = FakeChannel("nitrado-ban", 100)
        duplicate = FakeChannel("nitrado-ban-feed", 200)
        guild = FakeGuild([duplicate, original])
        config = {"allow_channel_auto_discovery": True, "channels": {"nitrado_ban_logs": duplicate.id}}

        self.assertTrue(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["nitrado_ban_logs"], original.id)

    def test_custom_feed_route_is_not_overwritten_by_default_channel(self):
        default = FakeChannel("🚨🏴・raids・🏴🚨", 100)
        custom = FakeChannel("airfield-pings", 200)
        guild = FakeGuild([default, custom])
        config = {"channels": {"raids": custom.id}, "custom_channel_routes": ["raids"]}

        self.assertFalse(bot.discover_existing_guild_channels(guild, config))
        self.assertEqual(config["channels"]["raids"], custom.id)

    def test_forced_create_does_not_rename_saved_dashboard_audit_channel(self):
        custom = FakeChannel("staff-change-log", 300)
        guild = FakeGuild([custom])
        config = {"channels": {"dashboard_audit": custom.id}}

        async def run():
            with mock.patch.object(bot, "ensure_bot_category", new_callable=mock.AsyncMock) as ensure_category:
                channel = await bot.get_or_create_feed_channel(
                    guild,
                    config,
                    "dashboard_audit",
                    bot.DEFAULT_CHANNEL_NAMES["dashboard_audit"],
                    private=True,
                    force=True,
                )
                ensure_category.assert_not_awaited()
                return channel

        channel = asyncio.run(run())

        self.assertIs(channel, custom)
        self.assertEqual("staff-change-log", custom.name)
        self.assertEqual([], custom.edit_calls)

    def test_get_or_create_feed_channel_resolves_dashboard_string_channel_id(self):
        routed = FakeChannel("LiVo-FLAg-FeeD", 1507886422521155644)
        guild = FakeGuild([routed])
        config = {"channels": {"flag_feed": "1507886422521155644"}}

        async def run():
            return await bot.get_or_create_feed_channel(
                guild,
                config,
                "flag_feed",
                bot.DEFAULT_CHANNEL_NAMES["flag_feed"],
                private=True,
            )

        channel = asyncio.run(run())

        self.assertIs(channel, routed)
        self.assertEqual([], routed.edit_calls)

    def test_server_profile_heatmap_mode_persists(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {
                            "profile_name": "Wandering Around Cherno",
                            "server_map": "chernarus",
                            "channels": {},
                        },
                    },
                }
            }

            config = bot.config_for_server_runtime("guild-a:cherno")
            config["heatmap_mode"] = "pvp"

            self.assertTrue(bot.persist_server_profile_runtime_config(config))
            self.assertEqual(
                "pvp",
                bot.guild_configs["guild-a"]["server_profiles"]["cherno"]["heatmap_mode"],
            )
            self.assertEqual("pvp", bot.guild_heatmap_mode("guild-a:cherno"))
        finally:
            bot.guild_configs = previous_configs

    def test_base_dashboard_scenario_event_migrates_to_matching_profile(self):
        config = {
            "guild_name": "Merged",
            "server_map": "chernarus",
            "scenario_events": [
                {
                    "id": 33,
                    "created_by": "dashboard",
                    "event_type": "airdrop",
                    "upload_status": "blocked",
                    "upload_attempts": 3,
                    "status": "Native CE source required",
                },
                {"id": 44, "created_by": "manual", "event_type": "airdrop"},
            ],
            "server_profiles": {
                "cherno": {"profile_name": "Wandering Around Cherno", "server_map": "chernarus"},
                "livo": {"profile_name": "Wandering Around Livo", "server_map": "livonia"},
            },
        }

        self.assertTrue(bot.migrate_base_dashboard_scenario_events_to_matching_profile(config))

        self.assertEqual([{"id": 44, "created_by": "manual", "event_type": "airdrop"}], config["scenario_events"])
        cherno_events = config["server_profiles"]["cherno"]["scenario_events"]
        self.assertEqual(1, len(cherno_events))
        self.assertEqual(33, cherno_events[0]["id"])
        self.assertEqual("waiting_for_bot_upload", cherno_events[0]["upload_status"])
        self.assertEqual(0, cherno_events[0]["upload_attempts"])
        self.assertIn("Wandering Around Cherno profile", cherno_events[0]["status"])
        self.assertNotIn("scenario_events", config["server_profiles"]["livo"])

    def test_dashboard_scenario_upload_loop_expands_server_profiles(self):
        previous_configs = bot.guild_configs
        previous_guilds = bot.bot.guilds
        previous_load = bot.load_guild_configs
        previous_save = bot.save_guild_configs
        previous_process = bot.process_dashboard_scenario_xml_upload
        previous_notices = bot.process_scenario_event_discord_notices
        calls = []

        async def fake_process(guild_id, config):
            calls.append(guild_id)
            config["scenario_events"] = [{"id": guild_id, "upload_status": "uploaded"}]
            config["scenario_event_discord_notices"] = [{"id": guild_id}]
            return True

        async def fake_notices(_guild_id, _config):
            return False

        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Wandering Around Cherno", "server_map": "chernarus"},
                        "livo": {"profile_name": "Wandering Around Livo", "server_map": "livonia"},
                    },
                },
            }
            bot.bot.guilds = [FakeGuild([], guild_id="guild-a", name="Merged")]
            bot.load_guild_configs = lambda: None
            bot.save_guild_configs = lambda: None
            bot.process_dashboard_scenario_xml_upload = fake_process
            bot.process_scenario_event_discord_notices = fake_notices

            asyncio.run(bot.dashboard_scenario_upload_loop())

            self.assertEqual(["guild-a:cherno", "guild-a:livo"], calls)
            self.assertEqual(
                "guild-a:cherno",
                bot.guild_configs["guild-a"]["server_profiles"]["cherno"]["scenario_events"][0]["id"],
            )
            self.assertEqual(
                "guild-a:livo",
                bot.guild_configs["guild-a"]["server_profiles"]["livo"]["scenario_event_discord_notices"][0]["id"],
            )
        finally:
            bot.guild_configs = previous_configs
            bot.bot.guilds = previous_guilds
            bot.load_guild_configs = previous_load
            bot.save_guild_configs = previous_save
            bot.process_dashboard_scenario_xml_upload = previous_process
            bot.process_scenario_event_discord_notices = previous_notices

    def test_live_leaderboard_uses_dashboard_route_key(self):
        config = {"channels": {"leaderboards": "300"}}

        self.assertEqual(("leaderboards", 300), bot.live_leaderboard_channel_route(config))

    def test_disabled_dashboard_leaderboard_route_does_not_post(self):
        config = {"channels": {"leaderboards": "300"}, "disabled_channels": ["leaderboards"]}

        self.assertEqual(("", None), bot.live_leaderboard_channel_route(config))

    def test_explicit_repair_can_rename_saved_dashboard_audit_channel(self):
        custom = FakeChannel("staff-change-log", 300)
        category = FakeCategory("Staff Ops", 900)
        guild = FakeGuild([custom])
        config = {"channels": {"dashboard_audit": custom.id}}

        async def run():
            with mock.patch.object(bot, "ensure_bot_category", new_callable=mock.AsyncMock, return_value=category):
                return await bot.get_or_create_feed_channel(
                    guild,
                    config,
                    "dashboard_audit",
                    bot.DEFAULT_CHANNEL_NAMES["dashboard_audit"],
                    private=True,
                    force=True,
                    repair_existing=True,
                )

        channel = asyncio.run(run())

        self.assertIs(channel, custom)
        self.assertEqual(bot.DEFAULT_CHANNEL_NAMES["dashboard_audit"], custom.name)
        self.assertEqual(category.id, custom.category_id)

    def test_feed_target_resolves_live_pack_and_raid_alias(self):
        keys, error = bot.resolve_feed_target_keys("live")
        self.assertIsNone(error)
        self.assertIn("raids", keys)

        keys, error = bot.resolve_feed_target_keys("raid events")
        self.assertIsNone(error)
        self.assertEqual(keys, ["raids"])

    def test_radar_channel_matches_plain_radars(self):
        channel = FakeChannel("Radars", 300)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "radar"))

    def test_radar_category_matches_plain_radars(self):
        category = FakeCategory("Radars")

        self.assertTrue(bot.category_matches_bot_spec(category, "radar_pings"))

    def test_clean_default_channel_names_match(self):
        killfeed_name = bot.styled_channel_name("kiLLFeeD") + "\U0001f480"
        leaderboard_name = bot.styled_channel_name("LeADeRBoARD") + "\U0001f4ca"

        self.assertEqual(killfeed_name, bot.DEFAULT_CHANNEL_NAMES["killfeed"])
        self.assertEqual(leaderboard_name, bot.DEFAULT_CHANNEL_NAMES["leaderboards"])
        self.assertNotEqual("kiLLFeeD\U0001f480", killfeed_name)
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel(killfeed_name, 501), "killfeed"))
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel(leaderboard_name, 502), "leaderboards"))

    def test_clean_defaults_do_not_add_server_prefixes(self):
        livo_config = {"server_map": "livonia", "profile_name": "Wandering Around Livo"}
        cherno_config = {"server_map": "chernarus", "profile_name": "Wandering Around Cherno"}

        flag_name = bot.styled_channel_name("FLAg-FeeD") + "\U0001f6a9"

        self.assertEqual(flag_name, bot.default_channel_name_for_config("flag_feed", livo_config))
        self.assertEqual(flag_name, bot.default_channel_name_for_config("flag_feed", cherno_config))

    def test_livo_trader_category_matches_plain_owner_category(self):
        category = FakeCategory("Livo Trader")

        self.assertTrue(bot.category_matches_bot_spec(category, "livo_trader"))

    def test_livo_trader_channels_match_plain_names(self):
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel("trader-log", 400), "livo_trader_log"))
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel("transactions", 401), "livo_trader_transactions"))
        self.assertTrue(bot.channel_matches_bot_default_name(FakeChannel("balance-feed", 402), "livo_trader_balance"))

    def test_livo_trader_pack_is_guild_local_not_in_all(self):
        self.assertIn("livo_trader_balance", bot.CHANNEL_RESTORE_PACKS["livo_trader"])
        self.assertNotIn("livo_trader_balance", bot.CHANNEL_RESTORE_PACKS["all"])

    def test_swear_jar_feed_is_managed_channel(self):
        channel = FakeChannel("swear-jar", 500)

        self.assertTrue(bot.channel_matches_bot_default_name(channel, "swear_jar_feed"))
        self.assertIn("swear_jar_feed", bot.CHANNEL_RESTORE_PACKS["economy"])

    def test_rpt_admin_is_routeable_private_staff_channel(self):
        self.assertEqual(bot.styled_channel_name("eVeNt-sPAWNs") + "\U0001f4cd", bot.DEFAULT_CHANNEL_NAMES["rpt_admin"])
        self.assertIn("rpt_admin", bot.PRIVATE_FEED_CHANNEL_KEYS)
        self.assertIn("rpt_admin", bot.CHANNEL_RESTORE_PACKS["staff"])
        self.assertEqual("staff_ops", bot.BOT_CHANNEL_CATEGORY_BY_KEY["rpt_admin"])

    def test_rpt_world_link_uses_server_profile_map(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "livo": {"profile_name": "Livo", "server_map": "livonia", "channels": {}},
                    },
                }
            }

            link = bot._rpt_world_link(5201, 6178, "guild-a:livo")

            self.assertIn("dayz.ginfo.gg/livonia/", link)
        finally:
            bot.guild_configs = previous_configs

    def test_dashboard_live_feed_mapping_records_dashboard_only_events(self):
        previous = bot.dashboard_live_feeds
        try:
            bot.dashboard_live_feeds = {}

            self.assertEqual("placed_feed", bot.dashboard_live_feed_key_for_event("placed"))
            self.assertEqual("building", bot.dashboard_live_feed_key_for_event("build"))
            changed = bot.record_dashboard_live_feed(
                "guild-1",
                "placed",
                '10:00:00 | Player "Crane" (pos=<1000,2000,10>) placed FenceKit',
            )
        finally:
            recorded = bot.dashboard_live_feeds
            bot.dashboard_live_feeds = previous

        self.assertTrue(changed)
        self.assertEqual("placed_feed", recorded["guild-1"][0]["feed_key"])
        self.assertIn("Crane", recorded["guild-1"][0]["summary"])

    def test_server_profile_runtime_ids_keep_guilds_isolated(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "A",
                    "nitrado_token": "shared-token",
                    "service_id": "base-service",
                    "server_profiles": {
                        "livo": {"profile_name": "Livo", "service_id": "111", "server_map": "livonia", "channels": {"building": "10"}},
                    },
                },
                "guild-b": {
                    "guild_name": "B",
                    "server_profiles": {
                        "livo": {"profile_name": "Other Livo", "service_id": "222", "server_map": "chernarus", "channels": {"building": "20"}},
                    },
                },
            }

            runtime_a = bot.server_profile_runtime_id("guild-a", "livo")
            runtime_b = bot.server_profile_runtime_id("guild-b", "livo")
            config_a = bot.config_for_server_runtime(runtime_a)
            config_b = bot.config_for_server_runtime(runtime_b)

            self.assertEqual("guild-a:livo", runtime_a)
            self.assertEqual("guild-b:livo", runtime_b)
            self.assertNotEqual(bot.adm_file_path(runtime_a), bot.adm_file_path(runtime_b))
            self.assertEqual("shared-token", config_a["nitrado_token"])
            self.assertEqual("111", config_a["service_id"])
            self.assertEqual("222", config_b["service_id"])
            self.assertNotIn("nitrado_token", config_b)
            self.assertEqual("10", config_a["channels"]["building"])
            self.assertEqual("20", config_b["channels"]["building"])
            self.assertEqual("livonia", bot.server_map_key(runtime_a))
            self.assertEqual("chernarus", bot.server_map_key(runtime_b))
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_uses_saved_feed_channel_id(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {"killfeed": "100"}},
                        "livo": {"profile_name": "Wandering Around Livo", "server_map": "livonia", "channels": {"killfeed": "200"}},
                    },
                }
            }
            channel = FakeChannel("killfeed", 200)
            guild = FakeGuild([channel])

            runtime_id, config, error = bot.runtime_config_for_command_context(guild, channel=channel, require_profile=True)

            self.assertIsNone(error)
            self.assertEqual("guild-a:livo", runtime_id)
            self.assertEqual("livonia", config["server_map"])
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_uses_category_name(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {}},
                        "livo": {"profile_name": "Livo", "server_map": "livonia", "channels": {}},
                    },
                }
            }
            category = FakeCategory("Wandering Around Cherno")
            channel = FakeChannel("leaderboards", 300, category=category)
            guild = FakeGuild([channel])

            runtime_id, _config, error = bot.runtime_config_for_command_context(guild, channel=channel, require_profile=True)

            self.assertIsNone(error)
            self.assertEqual("guild-a:cherno", runtime_id)
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_channel_name_beats_ambiguous_roles(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {}},
                        "livo": {"profile_name": "Livo", "server_map": "livonia", "channels": {}},
                    },
                }
            }
            member = FakeMember([FakeRole("Cherno Survivor", 10), FakeRole("Livo Survivor", 20)])
            channel = FakeChannel("livo-leaderboard", 400)
            guild = FakeGuild([channel])

            runtime_id, _config, error = bot.runtime_config_for_command_context(guild, channel=channel, member=member, require_profile=True)

            self.assertIsNone(error)
            self.assertEqual("guild-a:livo", runtime_id)
        finally:
            bot.guild_configs = previous_configs

    def test_server_profile_context_ambiguous_roles_require_choice(self):
        previous_configs = bot.guild_configs
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {}},
                        "livo": {"profile_name": "Livo", "server_map": "livonia", "channels": {}},
                    },
                }
            }
            member = FakeMember([FakeRole("Cherno Survivor", 10), FakeRole("Livo Survivor", 20)])
            guild = FakeGuild([])

            runtime_id, config, error = bot.runtime_config_for_command_context(guild, member=member, require_profile=True)

            self.assertIsNone(runtime_id)
            self.assertIsNone(config)
            self.assertIn("more than one possible", error)
        finally:
            bot.guild_configs = previous_configs

    def test_live_map_uses_server_profile_context(self):
        previous_configs = bot.guild_configs
        previous_online = bot.online_players
        previous_last_coords = bot.player_last_coords
        try:
            bot.guild_configs = {
                "guild-a": {
                    "guild_name": "Merged",
                    "server_profiles": {
                        "cherno": {"profile_name": "Cherno", "server_map": "chernarus", "channels": {"online": "100"}},
                        "livo": {"profile_name": "Wandering Around Livo", "server_map": "livonia", "channels": {"online": "200"}},
                    },
                }
            }
            bot.online_players = {"guild-a": {"BaseOnly"}, "guild-a:livo": set()}
            bot.player_last_coords = {}
            channel = FakeChannel("online-survivors", 200)
            guild = FakeGuild([channel])
            interaction = FakeInteraction(guild, channel)

            with mock.patch.object(bot, "has_interaction_admin_power", return_value=True):
                asyncio.run(bot.send_live_map_response(interaction))

            self.assertTrue(interaction.response.deferred)
            self.assertEqual(1, len(interaction.followup.sent))
            message = interaction.followup.sent[0][0][0]
            self.assertIn("Wandering Around Livo", message)
            self.assertNotIn("BaseOnly", message)
        finally:
            bot.guild_configs = previous_configs
            bot.online_players = previous_online
            bot.player_last_coords = previous_last_coords

    def test_player_stats_same_name_can_split_by_server_profile(self):
        previous_stats = bot.player_stats
        try:
            bot.player_stats = {
                "Crane": {
                    "guild_id": "guild-a:cherno",
                    "player_name": "Crane",
                    "kills": 5,
                }
            }

            stats = bot.ensure_player_stats_record("guild-a:livo", "Crane")
            stats["kills"] = 2
            again = bot.ensure_player_stats_record("guild-a:livo", "Crane")
            storage_key, found = bot.player_stats_for_guild_player("guild-a:livo", "Crane")

            self.assertIs(again, stats)
            self.assertEqual("Crane [guild-a_livo]", storage_key)
            self.assertEqual("Crane", bot.player_stats_display_name(storage_key, found))
            self.assertEqual("guild-a:livo", found["guild_id"])
            self.assertEqual(5, bot.player_stats["Crane"]["kills"])
        finally:
            bot.player_stats = previous_stats

    def test_setup_server_settings_preserve_existing_values_when_blank(self):
        config = {
            "server_platform": "playstation",
            "server_map": "livonia",
            "server_mode": "pve",
        }

        platform, server_map, server_mode = bot.resolve_setup_server_settings(config)

        self.assertEqual("playstation", platform)
        self.assertEqual("livonia", server_map)
        self.assertEqual("pve", server_mode)

    def test_setup_server_settings_can_change_only_server_mode(self):
        config = {
            "server_platform": "xbox",
            "server_map": "chernarus",
            "server_mode": "pve",
        }

        platform, server_map, server_mode = bot.resolve_setup_server_settings(config, server_mode="PVP only")

        self.assertEqual("xbox", platform)
        self.assertEqual("chernarus", server_map)
        self.assertEqual("pvp", server_mode)


if __name__ == "__main__":
    unittest.main()
