# =========================================================
# WANDERING BOT ALPHA - MULTI GUILD EDITION
# =========================================================

import os
import re
import json
import random
import hashlib
import base64
import io
import asyncio
import requests
import tempfile
import shutil
import xml.etree.ElementTree as ET
from ftplib import FTP_TLS
import discord
import socket

from datetime import datetime, UTC, timedelta
from collections import OrderedDict
from discord.ext import commands, tasks
from discord import app_commands

# =========================================================
# DISCORD
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TRANSLATE_API_URL = os.getenv("TRANSLATE_API_URL", "https://libretranslate.de/translate")
TRANSLATE_API_KEY = os.getenv("TRANSLATE_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents
)

# =========================================================
# GLOBAL CONFIG
# =========================================================

BOT_IMAGE = (
    "https://media.discordapp.net/"
    "attachments/1499787777636831324/"
    "1501685742433206342/"
    "7A382429-B666-4A9F-B890-17C0F7981709.png"
)

DEFAULT_MAP_IMAGE_SOURCES = {
    "chernarus": "https://i.redd.it/a2mn8bzx93gd1.jpeg",
    "livonia": "https://i.imgur.com/nzEp9wF.jpeg",
}

DATA_ROOT = (
    os.getenv("WANDERING_DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or os.getenv("RAILWAY_VOLUME_PATH")
    or "."
)


def data_path(*parts):
    return os.path.join(DATA_ROOT, *parts)


GUILD_CONFIG_FILE = data_path("guild_configs.json")
GUILD_DATA_FOLDER = data_path("guild_data")
GUILD_CONFIG_FOLDER = os.path.join(GUILD_DATA_FOLDER, "guilds")
PROCESSED_ADM_FILE = data_path("processed_adm_lines.json")
PLAYER_STATS_FILE = data_path("player_stats.json")
HEATMAP_FILE = data_path("heatmap.json")
SWEAR_JAR_FILE = data_path("swear_jar.json")
LINKED_PLAYERS_FILE = data_path("linked_players.json")
LONGSHOT_RECORDS_FILE = data_path("longshot_records.json")
RAMPAGE_TRACKER_FILE = data_path("rampage_tracker.json")
FIRST_BLOOD_FILE = data_path("first_blood.json")
DAILY_RECAP_FILE = data_path("daily_recap.json")
BOUNTIES_FILE = data_path("bounties.json")
SURVIVAL_STREAKS_FILE = data_path("survival_streaks.json")
RECAP_POSTED_FILE = data_path("recap_posted.json")
ACHIEVEMENTS_FILE = data_path("achievements.json")
NEMESIS_FILE = data_path("nemesis_log.json")
ALIVE_STREAKS_FILE = data_path("alive_streaks.json")
DAILY_CHALLENGE_FILE = data_path("daily_challenges.json")
SUPPORT_TICKETS_FILE = data_path("support_tickets.json")
WANDERING_EMOJIS_FILE = data_path("wandering_emojis.json")
FACTIONS_FILE = data_path("factions.json")
PVE_CHALLENGES_FILE = data_path("pve_challenges.json")
MAP_IMAGE_FOLDER = data_path("map_images")
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DAYZ_REFERENCE_FOLDER = os.getenv("DAYZ_REFERENCE_DIR", os.path.join(APP_ROOT, "dayz_reference"))

# =========================================================
# GLOBALS
# =========================================================

guild_configs = {}
processed_lines = {}
# Per-guild asyncio.Lock so two ADM scans for the same guild can never
# overlap (which used to cause the same log line to be posted twice).
adm_scan_locks = {}
# Maximum number of recently-seen ADM line hashes to keep per guild.
# Must be high enough that lines still inside the `lines[-250:]` parse
# window remain in cache between scans, even on a quiet server where
# the same lines linger in that window for a long time.
PROCESSED_ADM_CACHE_LIMIT = 5000
online_players = {}
player_last_coords = {}
player_online_times = {}
territory_heat = {}
zone_keywords = {
    "NWAF": ["nwaf", "airfield"],
    "Tisy": ["tisy"],
    "Zelenogorsk": ["zeleno"],
    "Chernogorsk": ["cherno"],
    "Elektrozavodsk": ["electro"],
    "Vybor": ["vybor"],
    "Berezino": ["berezino"],
    "Severograd": ["severo"]
}
player_stats = {}
longshot_records = {}              # {guild_id: [longshot_dict, ...] sorted by distance desc, max 50}
recent_kills_by_killer = {}        # {guild_id: {killer: [(timestamp, victim, weapon), ...]}} for rampage detection
first_blood_today = {}             # {guild_id: {"date": "YYYY-MM-DD", "killer": str, "victim": str, "weapon": str, "time": iso}}
final_kill_today = {}              # {guild_id: {"date": "YYYY-MM-DD", "killer": str, "victim": str, "weapon": str, "time": iso}}
daily_recap_data = {}              # {guild_id: {"YYYY-MM-DD": {kills, headshots, vehicle_kills, killers, weapons, zones, longshots, ...}}}
bounties = {}                      # {guild_id: {target_player_lower: {target, amount, posted_by, posted_at, currency}}}
survival_streaks = {}              # {guild_id: {player: {streak_start_date, last_alive_date, longest_days, current_days}}}
recap_posted = {}                  # {guild_id: "YYYY-MM-DD"} to prevent double-posting
recent_kill_events = {}            # {guild_id: deque of recent kill dicts} for squad detection
recent_connect_times = {}          # {guild_id: [(ts, player), ...]} for squad-inbound alerts
achievements_data = {}             # {guild_id: {player: {"unlocked": [badge_id], "unlocked_at": {badge_id: iso}}}}
nemesis_data = {}                  # {guild_id: {killer: {victim: count}}}
alive_streaks = {}                 # {guild_id: {player: {"current_spree": int, "best_spree": int, "last_kill_at": iso}}}
daily_challenges = {}              # {guild_id: {"date": "YYYY-MM-DD", "challenge": {...}, "completed_by": [players]}}
SQUAD_INBOUND_WINDOW_SECONDS = 60
SQUAD_INBOUND_MIN_PLAYERS = 5
NEMESIS_MILESTONES = (3, 5, 10, 25)
LONGSHOT_LEADERBOARD_LIMIT = 50    # max longshots stored per guild
RAMPAGE_WINDOW_SECONDS = 60        # kills within this window count as a streak
RAMPAGE_MIN_KILLS = 3              # min kills in the window to trigger a rampage embed
SQUAD_WINDOW_SECONDS = 90          # kills by different killers within this window in same zone = squad
SQUAD_MIN_MATES = 2                # min number of distinct killers to flag squad
RECAP_DAILY_HOUR_UTC = int(os.getenv("WANDERING_RECAP_HOUR_UTC", "0"))  # daily recap post hour (UTC)
NEWS_BULLETIN_ENABLED = str(os.getenv("WANDERING_NEWS_BULLETIN_ENABLED", "1")).lower() in {"1", "true", "yes", "on"}
SURVIVAL_STREAK_MILESTONES = (7, 14, 30, 60, 100)
BOUNTY_CURRENCY = os.getenv("WANDERING_BOUNTY_CURRENCY", "Rubles")
THREAD_ON_LONGSHOT_METERS = 500
THREAD_ON_RAMPAGE_KILLS = 5
swear_jar = {}
player_chat_tracker = {}
linked_players = {}
last_funny_message_time = {}
last_funny_index = {}
last_emoji_showcase_time = {}
support_tickets = {}
wandering_emojis = {}
factions = {}
pve_challenges = {}
last_ai_direct_response_time = {}
last_owner_mention_time = {}
last_ai_image_time = {}
recent_pvp_kill_signatures = {}
last_heatmap_render_status = {}
cheat_kill_chains = {}

# =========================================================
# AUTONOMOUS SHOWCASE GLOBALS
# =========================================================

DEFAULT_SHOWCASE_GUILD_ID = "1505197634951053404"
SHOWCASE_GUILD_ID = os.getenv("SHOWCASE_GUILD_ID", DEFAULT_SHOWCASE_GUILD_ID)
SHOWCASE_CHANNEL_ID = os.getenv("SHOWCASE_CHANNEL_ID", "1505197634951053404")
DEFAULT_BOT_INVITE_URL = os.getenv(
    "BOT_INVITE_URL",
    "https://discord.com/oauth2/authorize?client_id=1500819036026437662&permissions=8&integration_type=0&scope=bot+applications.commands"
)
DEFAULT_BOT_OWNER_ID = "1466097358713651220"
user_style_profiles = {}          # user_id -> style data
last_showcase_proactive_time = {} # guild_id -> timestamp
last_showcase_greeting_image = {} # guild_id -> timestamp
last_showcase_discussion_time = {} # guild_id -> timestamp
last_showcase_reaction_time = {}  # channel_id -> timestamp
owner_natural_language_cooldowns = {}

HEATMAP_MODES = [
    "pvp",
    "zombie",
    "cuts",
    "building",
    "raids",
    "flags",
    "suicide",
    "placed",
    "pve",
    "all"
]

LONGSHOT_ANNOUNCE_METERS = 300
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_IMAGE_MODEL = os.getenv("WANDERING_AI_IMAGE_MODEL", "gpt-image-1")
AI_IMAGE_DEFAULT_COOLDOWN_SECONDS = int(os.getenv("WANDERING_AI_IMAGE_COOLDOWN_SECONDS", "21600"))

# ── AI Death Roasts (Emergent Universal LLM Key) ─────────────
# Roasts are short, one-line bits of flavour text shown in the
# killfeed embed footer. They are OFF by default per-guild and
# admins must opt-in via /extra setroasts on.
EMERGENT_LLM_KEY = os.getenv("EMERGENT_LLM_KEY")
AI_ROAST_MODEL = os.getenv("WANDERING_AI_ROAST_MODEL", "gpt-5-nano")
AI_ROAST_PROVIDER = os.getenv("WANDERING_AI_ROAST_PROVIDER", "openai")
AI_ROAST_TIMEOUT_SECONDS = float(os.getenv("WANDERING_AI_ROAST_TIMEOUT_SECONDS", "8"))
AI_ROAST_TONE = os.getenv("WANDERING_AI_ROAST_TONE", "mixed")  # mixed|edgy|pg13|brutal_clean
AI_ROAST_SYSTEM_PROMPT = (
    "You are the announcer for a hardcore DayZ killfeed. Generate ONE single-line "
    "trash-talk one-liner about the kill, max 22 words. No quotes, no emojis, no "
    "hashtags, no preamble — just the roast. Vary the joke each time. Reference the "
    "weapon or distance if it fits. Tone: switch between dark/edgy, witty/sarcastic, "
    "and brutal-but-clean. Never use slurs, NSFW content, or real-world tragedies."
)

# Headshot detection — DayZ ADM hit lines look like:
#   '... into Head(0) for 95.50 damage (Brain) with M4-A1 from 250.5 meters'
# So either the "into <part>" segment OR the damage-type segment can
# tell us it's a headshot. Both are checked.
HEADSHOT_HIT_LOCATIONS = {"head", "brain", "skull"}
HEADSHOT_DAMAGE_TYPES = {"brain", "head"}


def bot_invite_url(override=""):
    override = str(override or "").strip()
    if override:
        return override

    client_id = getattr(getattr(bot, "user", None), "id", None) or os.getenv("DISCORD_CLIENT_ID")
    if client_id:
        return (
            "https://discord.com/oauth2/authorize?"
            f"client_id={client_id}&permissions=8&integration_type=0&scope=bot+applications.commands"
        )

    return DEFAULT_BOT_INVITE_URL

DEFAULT_ADMIN_ROLES = [
    "Admin",
    "Administrator",
    "Owner"
]

DEFAULT_CHANNEL_NAMES = {
    "killfeed": "🔥🔥・killfeed・🔥🔥",
    "raids": "🚨🏴・raids・🏴🚨",
    "building": "🔨🧱・building・🧱🔨",
    "connections": "🟢✅・connected・✅🟢",
    "disconnects": "🔴⛔・disconnects・⛔🔴",
    "zombie_feed": "🧟🧟・zombie-feed・🧟🧟",
    "unconscious_feed": "🩹⚠️・unconscious-feed・⚠️🩹",
    "cuts_feed": "🩸🩹・cuts-feed・🩹🩸",
    "suicide_feed": "💀🧠・suicide-feed・🧠💀",
    "flag_feed": "🚩🏴・flag-feed・🏴🚩",
    "placed_feed": "📦🧰・placed-feed・🧰📦",
    "pvp_intel": "⚔️📡・pvp-intel・📡⚔️",
    "online": "✅🎮・online-survivors・🎮✅",
    "leaderboards": "🏆📊・leaderboards・📊🏆",
    "heatmap": "🔥🗺️・heatmap・🗺️🔥",
    "longshots": "🎯🏹・longshots・🏹🎯",
    "restart_alerts": "📢⏰・restart-alerts・⏰📢",
    "bot_updates": "📢✨・bot-updates・✨📢",
    "welcome": "👋🟩・welcome・🟩👋",
    "public_shame": "🚫📣・wandering-in-shame・📣🚫",
    "linked_players": "🔗🎮・linked-players・🎮🔗",
    "general_chat": "💬🌲・survivor-chat・🌲💬",
    "ai_chat": "🧠📻・survivor-ai・📻🧠",
    "clips_channel": "🎬⭐・dayz-clips・⭐🎬",
    "factions_chat": "🏴⚔️・factions-chat・⚔️🏴",
    "faction_list": "📜🏴・faction-list・🏴📜",
    "faction_tickets": "🎫🏴・faction-tickets・🏴🎫",
    "faction_staff": "🛡️🏴・faction-staff・🏴🛡️",
    "help_channel": "❓📘・help-desk・📘❓",
    "economy": "💰🛒・black-market・🛒💰",
    "admin_logs": "🛡️📕・admin-logs・📕🛡️",
    "cheat_checks": "🕵️🚫・pc-cheat-check・🚫🕵️",
    "command_logs": "📜🛡️・command-logs・🛡️📜",
    "purchase_logs": "💳📦・purchase-logs・📦💳",
    "vehicle_rentals": "🚗💰・vehicle-rentals・💰🚗",
    "rental_logs": "🛻📒・rental-logs・📒🛻",
    "pve_quests": "🧭📜・pve-quests・📜🧭",
    "pve_hunting": "🦌🏹・pve-hunting・🏹🦌",
    "pve_collection": "🎒🥫・pve-collection・🥫🎒",
    "pve_fishing": "🎣🐟・pve-fishing・🐟🎣",
    "pve_crafting": "🪓🛠️・pve-crafting・🛠️🪓",
    "pve_expeditions": "🗺️⛺・pve-expeditions・⛺🗺️",
    "pve_info": "📘🌿・pve-info・🌿📘",
    "pve_help": "❔🌿・pve-help・🌿❔",
    "pve_heatmap": "🦌🗺️・pve-heatmap・🗺️🦌",
    "company_announcements": "📢・wandering-company-announcements・📢"
}

PVE_THEMED_QUEST_KINDS = {
    "pve_hunting": "Hunting",
    "pve_collection": "Collection",
    "pve_fishing": "Fishing",
    "pve_crafting": "Crafting",
    "pve_expeditions": "Explorer",
}

PVE_SLOT_DIFFICULTIES = ["Easy", "Medium", "Hard"]

CHANNEL_ALIASES = {
    "killfeed": ["killfeed", "kills", "pvpfeed", "playerkills"],
    "raids": ["raids", "raidfeed", "raiddetected", "raidalerts"],
    "building": ["building", "build", "buildfeed", "basebuilding"],
    "connections": ["connected", "connections", "connect", "joins", "playerjoins"],
    "disconnects": ["disconnects", "disconnect", "leftserver", "playerleaves"],
    "online": ["online", "onlinesurvivors", "liveonline", "survivorsonline"],
    "leaderboards": ["leaderboards", "leaderboard", "topkills", "rankings"],
    "heatmap": ["heatmap", "conflictheatmap", "pvpheatmap"],
    "longshots": ["longshots", "longshot", "snipes"],
    "restart_alerts": ["restartalerts", "restart", "restarts", "serverrestarts"],
    "bot_updates": ["botupdates", "updates", "changelog", "newfeatures", "patchnotes"],
    "welcome": ["welcome", "newsurvivor"],
    "public_shame": ["wanderinginshame", "publicshame", "nameandshame", "bans"],
    "linked_players": ["linkedplayers", "gamerlinks", "linkedgamers", "usernamelinks", "identitylinks"],
    "general_chat": ["survivorchat", "generalchat", "general", "chat"],
    "factions_chat": ["factionschat", "factions", "factionchat"],
    "faction_list": ["factionlist", "factionslist"],
    "help_channel": ["helpdesk", "help", "support"],
    "clips_channel": ["dayzclips", "clips", "media"],
    "economy": ["blackmarket", "economy", "shop", "market"],
    "ai_chat": ["survivorai", "aichat", "ai"],
    "admin_logs": ["adminlogs", "stafflogs"],
    "cheat_checks": ["cheatchecks", "anticheat", "pccheatcheck"],
    "command_logs": ["commandlogs", "commands"],
    "purchase_logs": ["purchaselogs", "purchases"],
    "vehicle_rentals": ["vehiclerentals", "rentvehicles", "rentals"],
    "rental_logs": ["rentallogs"],
    "pve_quests": ["pvequests", "quests", "missions", "pvemissions"],
    "pve_hunting": ["pvehunting", "hunting", "animalhunts"],
    "pve_collection": ["pvecollection", "collection", "scavenger", "gathering"],
    "pve_fishing": ["pvefishing", "fishing", "fish"],
    "pve_crafting": ["pvecrafting", "crafting", "bushcraft"],
    "pve_expeditions": ["pveexpeditions", "expeditions", "exploration", "survivalruns"],
    "pve_info": ["pveinfo", "survivalinfo", "huntinginfo"],
    "pve_heatmap": ["pveheatmap", "animalheatmap"],
    "faction_tickets": ["factiontickets", "factionrequests"],
    "faction_staff": ["factionstaff"],
    "zombie_feed": ["zombiefeed", "infectedfeed", "zmbfeed", "zombies"],
    "unconscious_feed": ["unconsciousfeed", "medicalfeed", "unconscious"],
    "cuts_feed": ["cutsfeed", "cuts", "damagefeed", "survivordamage"],
    "suicide_feed": ["suicidefeed", "suicides", "suicide"],
    "flag_feed": ["flagfeed", "flags", "territoryflags", "flagactivity"],
    "placed_feed": ["placedfeed", "placements", "placed", "packed", "itemactivity"],
    "pvp_intel": ["pvpintel", "pvptips", "pvpinfo"],
    "company_announcements": ["wanderingcompanyannouncements", "companyannouncements"]
}

BOT_UPDATE_NOTES = [
    {
        "id": "2026-05-16-showcase-mode",
        "title": "Showcase Server Mode",
        "summary": "Owner showcase setup now creates an advertising/demo Discord instead of normal DayZ server feeds. The bot can greet visitors, answer feature questions, suggest commands, and show off AI image/chat abilities.",
        "commands": "`/ownerbotshowcase`, `/showcasestatus`",
        "audience": "Bot owner and showcase visitors",
    },
    {
        "id": "2026-05-16-pve-quest-ids",
        "title": "PVE Quest IDs and Difficulty Slots",
        "summary": "PVE quests now show a stable quest ID like `PVE-123456`. Each themed PVE feed keeps one Easy, one Medium, and one Hard quest active, and completing a quest replaces the same difficulty slot.",
        "commands": "`/pvequests`, `/pvecomplete`, `/pvesetup`, `/pveconfig`",
        "audience": "Admins and PVE players",
    },
    {
        "id": "2026-05-16-restart-cancel",
        "title": "Restart Schedule Controls",
        "summary": "Admins can now disable recurring scheduled restarts and turn them back on by setting the restart interval or start hour again.",
        "commands": "`/cancelrestarts`, `/setrestartinterval`, `/setrestartstart`, `/listrestarts`",
        "audience": "Admins",
    },
    {
        "id": "2026-05-16-command-log-repair",
        "title": "Command Log Feed Repair",
        "summary": "Command usage logging now creates or repairs the command-log feed more reliably, so staff can see command activity in the correct private channel.",
        "commands": "`/command-logs` feed, slash command logging",
        "audience": "Staff",
    },
    {
        "id": "2026-05-16-cheat-check",
        "title": "Private PC Cheat Check",
        "summary": "A private staff feed can now flag suspicious PC kill events from ADM logs, including impossible weapon distances and rapid snap-kill chains, with evidence and map links where available.",
        "commands": "`/cheatchecksetup`, `/cheatcheckconfig`, `/cheatcheckstatus`",
        "audience": "Admins and staff",
    },
    {
        "id": "2026-05-16-wandering-shame",
        "title": "Wandering in Shame Moderation Feed",
        "summary": "Admins can ban, temp-ban, and unban Discord members with public notices showing who, when, duration, moderator, and reason.",
        "commands": "`/shamesetup`, `/adminban`, `/admintempban`, `/adminunban`",
        "audience": "Admins and community members",
    },
    {
        "id": "2026-05-16-bot-updates",
        "title": "Public Bot Updates Feed",
        "summary": "Servers now get a public bot-updates channel for safe changelog posts. It explains new commands and features without exposing tokens, setup secrets, private logs, or sensitive server data.",
        "commands": "`/botupdates`",
        "audience": "Everyone",
    },
    {
        "id": "2026-05-16-channel-restore-options",
        "title": "Owner Channel Restore Choices",
        "summary": "If a server owner deletes bot-made channels, the bot now remembers that choice and will not recreate those channels on normal restart or update. Admins can review deleted channel keys and restore one channel, all channels, or a pack such as PVE, live feeds, staff, economy, factions, or community.",
        "commands": "`/tools channelstatus`, `/tools channelpacks`, `/tools restorechannels`, `/tools restorechannelpack`, `/setup restore_deleted_channels:true`",
        "audience": "Server owners and admins",
    },
    {
        "id": "2026-05-16-full-command-guide",
        "title": "Full Command Guide Pages",
        "summary": "The help page now posts a live, paged command guide that lists every slash command, what it does, and how to type its required and optional options. New setup runs seed the full guide into the help desk, showcase setup posts it in the commands guide channel, and existing servers can run /helpme to refresh it.",
        "commands": "`/helpme`, `/setup`, `/ownerbotshowcase`",
        "audience": "Everyone",
    },
]

SWEAR_REWARD_MIN = 300
SWEAR_REWARD_MAX = 800
SWEAR_REDEMPTION_MESSAGES_REQUIRED = 15
SWEAR_REDEMPTION_THRESHOLD = 20

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "bollocks",
    "wanker"
]

# =========================================================
# PERMISSION SYSTEM
# =========================================================

def has_staff_permissions(ctx):

    if is_global_bot_owner_id(getattr(getattr(ctx, "author", None), "id", "")):
        return True

    if getattr(getattr(ctx, "author", None), "guild_permissions", None):
        if ctx.author.guild_permissions.administrator:
            return True

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    allowed_roles = config.get(
        "admin_roles",
        DEFAULT_ADMIN_ROLES
    )

    user_roles = [
        role.name for role in ctx.author.roles
    ]

    return any(
        role in allowed_roles
        for role in user_roles
    )

# =========================================================
# HELPERS
# =========================================================

def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    return embed


def discord_safe_content(text, limit=1900):
    text = str(text or "")
    if len(text) <= limit:
        return text

    suffix = "\n\n...trimmed to fit Discord's message limit."
    return text[: max(0, limit - len(suffix))].rstrip() + suffix


def resolve_guild_role(guild, role_name):
    wanted = str(role_name).strip().lower()

    for role in guild.roles:
        if role.name.lower() == wanted:
            return role

    return None


def extract_player_name(line):
    match = re.search(r'Player "([^"]+)"', line)
    if match:
        return match.group(1)

    fallback_patterns = [
        r'"([^"]+)"\s+\(DEAD\)',
        r'"([^"]+)"\s+is connected',
        r'"([^"]+)"\s+has connected',
        r'"([^"]+)"\s+has disconnected',
        r'"([^"]+)"\s+hit by',
        r'"([^"]+)"\s+killed by',
    ]
    for pattern in fallback_patterns:
        fallback = re.search(pattern, line, re.IGNORECASE)
        if fallback:
            return fallback.group(1)

    return "Unknown"


def extract_adm_player_names(line):
    names = []

    for match in re.finditer(r'Player "([^"]+)"', line, re.IGNORECASE):
        names.append(match.group(1))

    for pattern in [
        r'"([^"]+)"\s+\(DEAD\)',
        r'"([^"]+)"\s+is connected',
        r'"([^"]+)"\s+has connected',
        r'"([^"]+)"\s+has disconnected',
        r'"([^"]+)"\s+hit by',
        r'"([^"]+)"\s+killed by',
    ]:
        for match in re.finditer(pattern, line, re.IGNORECASE):
            names.append(match.group(1))

    clean = []
    seen = set()
    for name in names:
        key = normalize_discord_name(name)
        if not key or key in seen:
            continue
        clean.append(name)
        seen.add(key)

    return clean


def extract_adm_coords(line):
    match = re.search(r"pos=<([^>]+)>", line)
    return match.group(1) if match else None


def build_adm_map_link(line, guild_id=None):
    coords = extract_adm_coords(line)
    return build_izurvive_link(coords, guild_id) if coords else None


def heatmap_mode_for_event(event_type):
    return {
        "kill": "pvp",
        "zombie_hit": "zombie",
        "zombie_kill": "zombie",
        "cut": "cuts",
        "bleedout": "cuts",
        "build": "building",
        "raid": "raids",
        "flag_raise": "flags",
        "flag_lower": "flags",
        "suicide": "suicide",
        "packed": "placed",
        "placed": "placed",
        "animal_kill": "pve",
    }.get(event_type)


def guild_heatmap_mode(guild_id):
    mode = guild_configs.get(str(guild_id), {}).get("heatmap_mode", "all")
    return mode if mode in HEATMAP_MODES else "all"


def heat_counts_for_mode(guild_id, mode):
    heat_data = territory_heat.get(str(guild_id), {})

    if mode == "pvp":
        return {
            key: value
            for key, value in heat_data.items()
            if not str(key).startswith("__") and isinstance(value, int)
        }

    if mode == "all":
        combined = {}
        for mode_counts in heat_data.get("__modes__", {}).values():
            for zone, count in mode_counts.items():
                combined[zone] = combined.get(zone, 0) + count
        return combined

    return heat_data.get("__modes__", {}).get(mode, {})


def server_map_key(guild_id):
    config = guild_configs.get(str(guild_id), {})
    configured = config.get("server_map")
    if not configured:
        guild_name_key = normalize_discord_name(config.get("guild_name", ""))
        if any(term in guild_name_key for term in ["livonia", "livo", "enoch"]):
            configured = "livonia"
        elif any(term in guild_name_key for term in ["sakhal", "sakhalplus"]):
            configured = "sakhal"
        else:
            configured = "chernarus"

    key = normalize_discord_name(configured)

    if key in ["livonia", "enoch"]:
        return "livonia"

    if key in ["sakhal", "sakhalplus"]:
        return "sakhal"

    return "chernarus"


def server_map_size(guild_id):
    map_key = server_map_key(guild_id)

    if map_key == "livonia":
        return 12800, 12800

    if map_key == "sakhal":
        return 15360, 15360

    return 15360, 15360


def map_coords_to_pixel(coords, guild_id=None, width=512, height=384):
    try:
        x_text, y_text = coords.split(",")[:2]
        x = float(x_text.strip())
        y = float(y_text.strip())
    except Exception:
        return None

    map_width, map_height = server_map_size(guild_id) if guild_id else (15360, 15360)
    px = int(max(0, min(width - 1, (x / map_width) * width)))
    py = int(max(0, min(height - 1, height - ((y / map_height) * height))))
    return px, py


def heat_points_for_mode(guild_id, mode):
    heat_data = territory_heat.get(str(guild_id), {})
    points = heat_data.get("__points__", {})

    if mode == "all":
        merged = []
        for mode_points in points.values():
            merged.extend(mode_points)
        return merged[-300:]

    return points.get(mode, [])[-300:]


async def get_or_create_feed_channel(guild, config, key, name, private=False, force=False):
    channels = config.setdefault("channels", {})
    if is_channel_key_disabled(config, key) and not force:
        return None

    if force:
        set_channel_key_disabled(config, key, False)

    existing_id = channels.get(key)

    if existing_id:
        existing = guild.get_channel(existing_id)
        if existing:
            if existing.name != name:
                try:
                    await existing.edit(name=name)
                except Exception:
                    pass
            return existing

    for channel in guild.text_channels:
        if normalize_discord_name(channel.name) == normalize_discord_name(name):
            channels[key] = channel.id
            save_guild_configs()
            return channel

    overwrites = {}
    if private:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }
        for role in guild.roles:
            if role.permissions.administrator or role.name in config.get("admin_roles", DEFAULT_ADMIN_ROLES):
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    category = None
    category_key = "live"
    if key.startswith("pve_"):
        category_key = "pve"

    for existing_category in guild.categories:
        normalized = normalize_discord_name(existing_category.name)
        if category_key == "pve" and ("pve" in normalized or "pvemissions" in normalized):
            category = existing_category
            break
        if category_key == "live" and ("livefeeds" in normalized or "liveserverfeeds" in normalized):
            category = existing_category
            break

    channel = await guild.create_text_channel(name, overwrites=overwrites, category=category)
    channels[key] = channel.id
    save_guild_configs()
    return channel


def split_adm_coords(coords):
    if not coords:
        return None, None, None

    parts = [part.strip() for part in str(coords).split(",")]
    x = parts[0] if len(parts) > 0 else None
    z = parts[1] if len(parts) > 1 else None
    y = parts[2] if len(parts) > 2 else None
    return x, z, y


def extract_placed_object(line):
    match = re.search(r"\bplaced\s+([^<]+)", line, re.IGNORECASE)
    if match:
        return match.group(1).strip().replace("_", " ")
    return "Unknown item"


def extract_packed_object(line):
    match = re.search(r"\bpacked\s+([^<]+)", line, re.IGNORECASE)
    if match:
        return match.group(1).strip().replace("_", " ")
    return "Unknown item"


def extract_pvp_kill_details(line):
    direct = re.search(r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)', line)
    reverse = re.search(r'Player "([^"]+)".* killed by Player "([^"]+)".* with ([^ ]+)', line)
    hit_death = re.search(
        r'"([^"]+)"\s+\(DEAD\).*?hit by Player "([^"]+)".*?for ([0-9]+\.?[0-9]*) damage \(([^)]+)\) with ([^ ]+) from ([0-9]+\.?[0-9]*) meters?',
        line,
        re.IGNORECASE
    )

    details = None
    if direct:
        details = {
            "killer": direct.group(1),
            "victim": direct.group(2),
            "weapon": direct.group(3),
        }
    elif reverse:
        details = {
            "victim": reverse.group(1),
            "killer": reverse.group(2),
            "weapon": reverse.group(3),
        }
    elif hit_death:
        details = {
            "victim": hit_death.group(1),
            "killer": hit_death.group(2),
            "damage": hit_death.group(3),
            "ammo": hit_death.group(4),
            "weapon": hit_death.group(5),
            "distance": float(hit_death.group(6)),
        }

    if not details:
        return None

    distance_match = re.search(r'from ([0-9]+\.?[0-9]*)\s*m(?:eters?)?', line, re.IGNORECASE)
    if distance_match:
        details["distance"] = float(distance_match.group(1))
    else:
        details.setdefault("distance", 0)

    coords = extract_adm_coords(line)
    if coords:
        details["coords"] = coords

    # Headshot detection — DayZ ADM exposes both the hit-zone
    # ("into Head(0)") and the damage type ("(Brain)"). Either is
    # enough to flag a headshot.
    headshot = False
    hit_location_match = re.search(r'into\s+([A-Za-z]+)', line)
    if hit_location_match and hit_location_match.group(1).lower() in HEADSHOT_HIT_LOCATIONS:
        headshot = True
        details["hit_location"] = hit_location_match.group(1)
    ammo_value = (details.get("ammo") or "").strip().lower()
    if ammo_value in HEADSHOT_DAMAGE_TYPES:
        headshot = True
    details["headshot"] = headshot

    return details


def extract_vehicle_kill_details(line):
    """Parse vehicle kill events like:
       Player "X" (DEAD) (pos=<...>) hit by Transport_PickupTruck for 250 damage
       Player "X" (DEAD) (pos=<...>) hit by Vehicle Sedan_01 from ..."""
    if "(dead)" not in line.lower():
        return None
    victim_match = re.search(r'"([^"]+)"\s+\(DEAD\)', line)
    vehicle_match = re.search(
        r'hit by (?:Vehicle\s+([A-Za-z0-9_\-]+)|(Transport[A-Za-z0-9_\-]*))',
        line,
        re.IGNORECASE,
    )
    if not victim_match:
        return None
    vehicle_name = "Vehicle"
    if vehicle_match:
        vehicle_name = vehicle_match.group(1) or vehicle_match.group(2) or "Vehicle"
    vehicle_clean = re.sub(r'^Transport_?', '', vehicle_name).replace("_", " ") or vehicle_name
    details = {
        "victim": victim_match.group(1),
        "vehicle": vehicle_clean,
    }
    coords = extract_adm_coords(line)
    if coords:
        details["coords"] = coords
    distance_match = re.search(r'from ([0-9]+\.?[0-9]*)\s*m', line, re.IGNORECASE)
    if distance_match:
        try:
            details["distance"] = float(distance_match.group(1))
        except Exception:
            pass
    return details


def pvp_kill_signature(guild_id, details):
    distance = int(round(float(details.get("distance", 0) or 0)))
    return (
        str(guild_id),
        normalize_discord_name(details.get("killer", "")),
        normalize_discord_name(details.get("victim", "")),
        normalize_discord_name(details.get("weapon", "")),
        distance,
    )


def is_duplicate_pvp_kill(guild_id, details, ttl_seconds=45):
    signature = pvp_kill_signature(guild_id, details)
    now_ts = datetime.now(UTC).timestamp()
    last_seen = recent_pvp_kill_signatures.get(signature, 0)
    recent_pvp_kill_signatures[signature] = now_ts

    for key, seen_ts in list(recent_pvp_kill_signatures.items()):
        if now_ts - seen_ts > ttl_seconds:
            recent_pvp_kill_signatures.pop(key, None)

    return now_ts - last_seen < ttl_seconds


CHEAT_WEAPON_LIMITS = {
    "Pistol": 400,
    "SMG": 600,
    "Shotgun": 600,
    "Rifle": 1000,
    "Sniper": 1300,
}

CHEAT_SNAP_RULES = [
    {"kills": 2, "span": 1.5, "angle": 85, "distance": 350},
    {"kills": 3, "span": 4.0, "angle": 60, "distance": 250},
    {"kills": 4, "span": 7.0, "angle": 40, "distance": 175},
]


def cheat_check_config(config):
    settings = config.setdefault("cheat_check", {})
    settings.setdefault("enabled", True)
    settings.setdefault("auto_ban", False)
    settings.setdefault("clear_chain_on_teleport", True)
    settings.setdefault("chain_window_seconds", 8)
    return settings


def classify_cheat_weapon(weapon):
    weapon_key = normalize_discord_name(weapon)
    if any(term in weapon_key for term in ["mosin", "svd", "vss", "vs89", "m70", "winchester", "cz550", "ssg", "lrs", "sniper"]):
        return "Sniper"
    if any(term in weapon_key for term in ["ij70", "makarov", "mkii", "fx45", "colt", "deagle", "p1", "pistol", "derringer"]):
        return "Pistol"
    if any(term in weapon_key for term in ["ump", "mp5", "sg5", "ak74u", "scorpion", "vikhr", "smg"]):
        return "SMG"
    if any(term in weapon_key for term in ["bk12", "bk133", "saiga", "vaiga", "shotgun"]):
        return "Shotgun"
    return "Rifle"


def parse_coord_tuple(coords):
    try:
        x, z, y = split_adm_coords(coords)
        return float(x), float(z), float(y or 0)
    except Exception:
        return None


def coord_distance(a, b):
    if not a or not b:
        return 0
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def angle_between_vectors(a, b):
    import math
    mag_a = (a[0] ** 2 + a[1] ** 2) ** 0.5
    mag_b = (b[0] ** 2 + b[1] ** 2) ** 0.5
    if mag_a <= 0 or mag_b <= 0:
        return 0
    dot = a[0] * b[0] + a[1] * b[1]
    cosine = max(-1, min(1, dot / (mag_a * mag_b)))
    return math.degrees(math.acos(cosine))


def extract_all_adm_coords(line):
    return re.findall(r"pos=<([^>]+)>", str(line))


def enrich_kill_coords(guild_id, kill_details, line):
    coords = extract_all_adm_coords(line)
    if coords:
        kill_details.setdefault("coords", coords[-1])
        if len(coords) >= 2:
            kill_details["killer_coords"] = coords[0]
            kill_details["victim_coords"] = coords[-1]
        else:
            kill_details["victim_coords"] = coords[0]

    killer = kill_details.get("killer")
    if killer and not kill_details.get("killer_coords"):
        last_seen = player_last_coords.get(str(guild_id), {}).get(killer, {})
        if isinstance(last_seen, dict) and last_seen.get("coords"):
            kill_details["killer_coords"] = last_seen["coords"]

    if not kill_details.get("victim_coords") and kill_details.get("coords"):
        kill_details["victim_coords"] = kill_details.get("coords")

    return kill_details


async def ensure_cheat_check_channel(guild, config, force=False):
    channels = config.setdefault("channels", {})
    if is_channel_key_disabled(config, "cheat_checks") and not force:
        return None

    if force:
        set_channel_key_disabled(config, "cheat_checks", False)

    channel = bot.get_channel(channels.get("cheat_checks"))
    if channel:
        return channel

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    for role in guild.roles:
        if role.permissions.administrator or role.name in config.get("admin_roles", DEFAULT_ADMIN_ROLES):
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    category_name = "🕵️🚫┃PRIVATE CHEAT CHECK┃🚫🕵️"
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        category = await guild.create_category(category_name, overwrites=overwrites)

    channel = await guild.create_text_channel(
        DEFAULT_CHANNEL_NAMES["cheat_checks"],
        overwrites=overwrites,
        category=category
    )
    channels["cheat_checks"] = channel.id
    save_guild_configs()
    return channel


async def post_cheat_check_intro(channel, config):
    settings = cheat_check_config(config)
    embed = discord.Embed(
        title="PC CHEAT CHECK",
        description=(
            "This private feed watches ADM kill events for impossible shot distances and rapid snap-kill chains. "
            "It is designed as staff evidence first, with optional auto-action only if you enable it."
        ),
        color=0xE74C3C
    )
    embed.add_field(
        name="Impossible Shot Distance",
        value="\n".join(f"`{weapon}` hard limit: `{limit}m`" for weapon, limit in CHEAT_WEAPON_LIMITS.items()),
        inline=False
    )
    embed.add_field(
        name="Rapid & Snap Kills",
        value=(
            "`2 kills`: 1.5s or less, 85 degrees+, 350m+ between victims\n"
            "`3 kills`: 4s or less, 60 degrees+, 250m+ between victims\n"
            "`4+ kills`: 7s or less, 40 degrees+, 175m+ between victims"
        ),
        inline=False
    )
    embed.add_field(
        name="Admin Commands",
        value=(
            "`/cheatchecksetup` creates/repairs this private category.\n"
            "`/cheatcheckconfig enabled:true auto_ban:false` changes detection settings.\n"
            "`/cheatcheckstatus` shows the current mode."
        ),
        inline=False
    )
    embed.add_field(
        name="Current Mode",
        value=f"Detection: `{'on' if settings.get('enabled') else 'off'}` | Auto-ban: `{'on' if settings.get('auto_ban') else 'off'}`",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Private PC Cheat Check")
    await channel.send(embed=style_embed(embed))


async def send_cheat_check_alert(guild_id, config, kill_details, reason, evidence, action_text):
    guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if not guild:
        return

    channel = await ensure_cheat_check_channel(guild, config)
    if not channel:
        return

    embed = discord.Embed(
        title="CHEAT CHECK FLAGGED",
        description=reason,
        color=0xE74C3C
    )
    embed.add_field(name="Player", value=kill_details.get("killer", "Unknown"), inline=True)
    embed.add_field(name="Victim", value=kill_details.get("victim", "Unknown"), inline=True)
    embed.add_field(name="Weapon", value=kill_details.get("weapon", "Unknown"), inline=True)
    embed.add_field(name="Distance", value=f"{float(kill_details.get('distance', 0) or 0):.1f}m", inline=True)
    embed.add_field(name="Action", value=action_text, inline=False)

    if evidence:
        embed.add_field(name="Evidence", value=evidence[:1000], inline=False)

    for label, coords in [("Attacker Position", kill_details.get("killer_coords")), ("Victim/Kill Position", kill_details.get("victim_coords") or kill_details.get("coords"))]:
        if coords:
            map_link = build_izurvive_link(coords, guild_id)
            value = f"[Open iZurvive](<{map_link}>)\n`{coords}`" if map_link else f"`{coords}`"
            embed.add_field(name=label, value=value, inline=False)

    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - PC Cheat Check")
    embed.timestamp = datetime.now(UTC)
    await channel.send(embed=style_embed(embed))


def build_snap_chain_evidence(guild_id, chain):
    if len(chain) < 2:
        return None

    victim_points = [parse_coord_tuple(item.get("victim_coords") or item.get("coords")) for item in chain]
    if any(point is None for point in victim_points):
        return None

    killer_points = [parse_coord_tuple(item.get("killer_coords")) for item in chain]
    angles = []
    victim_distances = []

    for idx in range(1, len(chain)):
        victim_distances.append(coord_distance(victim_points[idx - 1], victim_points[idx]))
        origin = killer_points[idx] or killer_points[idx - 1]
        if origin:
            previous_vector = (victim_points[idx - 1][0] - origin[0], victim_points[idx - 1][1] - origin[1])
            current_vector = (victim_points[idx][0] - origin[0], victim_points[idx][1] - origin[1])
            angles.append(angle_between_vectors(previous_vector, current_vector))

    if not angles or not victim_distances:
        return None

    avg_angle = sum(angles) / len(angles)
    avg_distance = sum(victim_distances) / len(victim_distances)
    span = float(chain[-1]["ts"] - chain[0]["ts"])
    kill_count = len(chain)
    rule = CHEAT_SNAP_RULES[-1] if kill_count >= 4 else CHEAT_SNAP_RULES[kill_count - 2]

    if span <= rule["span"] and avg_angle >= rule["angle"] and avg_distance >= rule["distance"]:
        map_lines = []
        for idx, item in enumerate(chain, start=1):
            coords = item.get("victim_coords") or item.get("coords")
            map_link = build_izurvive_link(coords, guild_id) if coords else None
            map_lines.append(f"{idx}. {item.get('victim')} at [map](<{map_link}>)" if map_link else f"{idx}. {item.get('victim')} at `{coords or 'unknown'}`")
        return {
            "span": span,
            "avg_angle": avg_angle,
            "avg_distance": avg_distance,
            "rule": rule,
            "map_lines": map_lines,
        }

    return None


async def process_cheat_check_from_kill(guild_id, config, kill_details, line):
    settings = cheat_check_config(config)
    if not settings.get("enabled", True):
        return

    kill_details = enrich_kill_coords(guild_id, dict(kill_details), line)
    killer = kill_details.get("killer")
    if not killer:
        return

    action_text = "Alert only. Review the evidence before taking action."
    if settings.get("auto_ban"):
        action_text = "Auto-ban is enabled in config, but this build records evidence only unless you wire a trusted DayZ ban backend."

    weapon_type = classify_cheat_weapon(kill_details.get("weapon", ""))
    hard_limit = CHEAT_WEAPON_LIMITS.get(weapon_type, 1000)
    distance = float(kill_details.get("distance", 0) or 0)

    if distance > hard_limit:
        evidence = f"`{weapon_type}` hard limit is `{hard_limit}m`; this kill was `{distance:.1f}m`."
        await send_cheat_check_alert(
            guild_id,
            config,
            kill_details,
            "Impossible shot distance detected.",
            evidence,
            action_text
        )

    now_ts = datetime.now(UTC).timestamp()
    chain_key = f"{guild_id}:{normalize_discord_name(killer)}"
    chain = cheat_kill_chains.setdefault(chain_key, [])
    chain.append({
        "ts": now_ts,
        "victim": kill_details.get("victim"),
        "weapon": kill_details.get("weapon"),
        "distance": distance,
        "killer_coords": kill_details.get("killer_coords"),
        "victim_coords": kill_details.get("victim_coords") or kill_details.get("coords"),
    })
    window = float(settings.get("chain_window_seconds", 8) or 8)
    chain = [item for item in chain if now_ts - item["ts"] <= window]
    cheat_kill_chains[chain_key] = chain[-6:]

    for size in [4, 3, 2]:
        if len(chain) < size:
            continue
        candidate = chain[-size:]
        snap = build_snap_chain_evidence(guild_id, candidate)
        if not snap:
            continue
        evidence = (
            f"`{size}` kills in `{snap['span']:.2f}s`.\n"
            f"Average angle: `{snap['avg_angle']:.1f}` degrees.\n"
            f"Average victim spacing: `{snap['avg_distance']:.1f}m`.\n"
            + "\n".join(snap["map_lines"])
        )
        await send_cheat_check_alert(
            guild_id,
            config,
            kill_details,
            "Rapid snap-kill chain detected.",
            evidence,
            action_text
        )
        cheat_kill_chains[chain_key] = []
        break


def parse_duration_to_seconds(duration):
    text = str(duration or "").strip().lower()
    if not text:
        return None
    total = 0
    matches = re.findall(r"(\d+)\s*(d|day|days|h|hr|hour|hours|m|min|mins|minute|minutes)", text)
    for amount_text, unit in matches:
        amount = int(amount_text)
        if unit.startswith("d"):
            total += amount * 86400
        elif unit.startswith("h"):
            total += amount * 3600
        else:
            total += amount * 60
    if total:
        return total
    if text.isdigit():
        return int(text) * 3600
    return None


def format_duration_seconds(seconds):
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "permanent"
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


async def ensure_public_shame_channel(guild, config, force=False):
    channels = config.setdefault("channels", {})
    if is_channel_key_disabled(config, "public_shame") and not force:
        return None

    if force:
        set_channel_key_disabled(config, "public_shame", False)

    channel = bot.get_channel(channels.get("public_shame"))
    if channel:
        return channel

    category_name = "🚫📣┃WANDERING JUSTICE┃📣🚫"
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        category = await guild.create_category(category_name)

    channel = await guild.create_text_channel(
        DEFAULT_CHANNEL_NAMES["public_shame"],
        category=category
    )
    channels["public_shame"] = channel.id
    save_guild_configs()

    embed = discord.Embed(
        title="WANDERING IN SHAME",
        description=(
            "Public moderation notices appear here when staff ban, temp-ban, or unban someone through Wandering Bot. "
            "Each notice shows who took the action, who it affected, the duration, and the reason."
        ),
        color=0xE74C3C
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Public Moderation Feed")
    await channel.send(embed=style_embed(embed))
    return channel


async def send_public_shame_notice(guild, config, title, member_text, moderator, reason, duration_text=None):
    channel = await ensure_public_shame_channel(guild, config)
    if not channel:
        return

    when = datetime.now(UTC)
    embed = discord.Embed(
        title=title,
        color=0xE74C3C
    )
    embed.add_field(name="Member", value=member_text, inline=False)
    embed.add_field(name="Moderator", value=f"{moderator.mention}\n`{moderator}`", inline=True)
    embed.add_field(name="When", value=when.strftime("%Y-%m-%d %H:%M UTC"), inline=True)
    if duration_text:
        embed.add_field(name="Duration", value=duration_text, inline=True)
    embed.add_field(name="Reason", value=reason[:1000] or "No reason supplied.", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Wandering in Shame")
    embed.timestamp = when
    await channel.send(embed=style_embed(embed))


async def process_temp_ban_expiries():
    now_ts = datetime.now(UTC).timestamp()
    changed = False

    for guild_id, config in active_guild_config_items():
        temp_bans = config.get("temp_bans", [])
        remaining = []
        guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None

        for ban_record in temp_bans:
            until_ts = float(ban_record.get("until_ts", 0) or 0)
            if until_ts > now_ts:
                remaining.append(ban_record)
                continue

            changed = True
            if not guild:
                continue

            try:
                user = await bot.fetch_user(int(ban_record["user_id"]))
                await guild.unban(user, reason="Temporary ban expired")
                await send_public_shame_notice(
                    guild,
                    config,
                    "TEMP BAN EXPIRED",
                    f"{user.mention if hasattr(user, 'mention') else user} (`{user}`)",
                    guild.me,
                    "Temporary ban duration expired.",
                    "expired"
                )
            except Exception as error:
                print(f"TEMP BAN EXPIRY ERROR {guild_id}: {error}")

        config["temp_bans"] = remaining

    if changed:
        save_guild_configs()


async def send_special_adm_feed(guild_id, config, event_type, line, event_time=None):
    guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if not guild:
        return

    # Anchor every embed to the in-game time the event was logged, not
    # when the bot got around to processing it. Falls back to "now" if
    # the ADM line has no parseable HH:MM:SS prefix.
    if event_time is None:
        event_time = extract_adm_event_time(line) or datetime.now(UTC)

    feed_map = {
        "flag_raise": ("flag_feed", DEFAULT_CHANNEL_NAMES["flag_feed"], True, "🚩 FLAG RAISED", 0x2ECC71),
        "flag_lower": ("flag_feed", DEFAULT_CHANNEL_NAMES["flag_feed"], True, "🏴 FLAG LOWERED", 0xE67E22),
        "cut": ("cuts_feed", DEFAULT_CHANNEL_NAMES["cuts_feed"], True, "🩸 SURVIVOR DAMAGE", 0xE74C3C),
        "bleedout": ("cuts_feed", DEFAULT_CHANNEL_NAMES["cuts_feed"], True, "🩹 SURVIVOR BLED OUT", 0x992D22),
        "suicide": ("suicide_feed", DEFAULT_CHANNEL_NAMES["suicide_feed"], True, "💀 SUICIDE EVENT", 0x8E44AD),
        "respawn": ("cuts_feed", DEFAULT_CHANNEL_NAMES["cuts_feed"], True, "🔵 RESPAWN CHOSEN", 0x3498DB),
        "packed": ("placed_feed", DEFAULT_CHANNEL_NAMES["placed_feed"], True, "🧰 ITEM PACKED", 0xF1C40F),
        "placed": ("placed_feed", DEFAULT_CHANNEL_NAMES["placed_feed"], True, "📦 ITEM PLACED", 0x00D1B2),
    }

    if event_type not in feed_map:
        return

    key, channel_name, private, title, color = feed_map[event_type]
    channel = await get_or_create_feed_channel(guild, config, key, channel_name, private)
    if not channel:
        return
    player = extract_player_name(line)
    coords = extract_adm_coords(line)
    map_link = build_adm_map_link(line, guild_id)

    if event_type in ["packed", "placed"]:
        item_name = extract_packed_object(line) if event_type == "packed" else extract_placed_object(line)
        x, z, _ = split_adm_coords(coords)
        embed = discord.Embed(
            title="🧰 ITEM PACKED" if event_type == "packed" else "📦 ITEM PLACED",
            color=color
        )
        embed.add_field(name="Player", value=player, inline=False)
        embed.add_field(name="Item", value=item_name, inline=False)

        if x or z:
            coord_lines = []
            if x:
                coord_lines.append(f"X: {x}")
            if z:
                coord_lines.append(f"Z: {z}")
            embed.add_field(name="Coordinates", value="\n".join(coord_lines), inline=False)

        if map_link:
            embed.add_field(name="Map", value=f"[Open Map](<{map_link}>)", inline=False)

        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - Placement Intelligence")
        embed.timestamp = event_time
        await channel.send(embed=style_embed(embed))
        return

    if event_type == "suicide":
        method = "Unknown"
        lower = line.lower()
        if "emotesuicide" in lower:
            method = "Emote suicide"
        elif "committed suicide" in lower:
            method = "Committed suicide"

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Survivor", value=player, inline=True)
        embed.add_field(name="Method", value=method, inline=True)

        if coords:
            x, z, y = split_adm_coords(coords)
            coord_lines = []
            if x:
                coord_lines.append(f"X: {x}")
            if z:
                coord_lines.append(f"Z: {z}")
            if y:
                coord_lines.append(f"Height: {y}")
            embed.add_field(name="Location", value="\n".join(coord_lines), inline=False)

        if map_link:
            embed.add_field(name="Map", value=f"[Open Map](<{map_link}>)", inline=False)

        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - Private Suicide Feed")
        embed.timestamp = event_time
        await channel.send(embed=style_embed(embed))
        return

    if event_type in ["cut", "bleedout", "respawn"]:
        attacker_match = re.search(r'hit by Player "([^"]+)"', line, re.IGNORECASE)
        weapon_match = re.search(r" with ([^ ]+) from ", line, re.IGNORECASE)
        damage_match = re.search(r" for ([0-9]+\.?[0-9]*) damage", line, re.IGNORECASE)
        body_match = re.search(r" into ([^(]+)\(", line, re.IGNORECASE)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Survivor", value=player, inline=True)

        if attacker_match:
            embed.add_field(name="Attacker", value=attacker_match.group(1), inline=True)

        if body_match:
            embed.add_field(name="Body Part", value=body_match.group(1).strip(), inline=True)

        if damage_match:
            embed.add_field(name="Damage", value=damage_match.group(1), inline=True)

        if weapon_match:
            embed.add_field(name="Weapon", value=weapon_match.group(1), inline=True)

        if coords:
            x, z, _ = split_adm_coords(coords)
            coord_text = "\n".join(part for part in [f"X: {x}" if x else "", f"Z: {z}" if z else ""] if part)
            if coord_text:
                embed.add_field(name="Location", value=coord_text, inline=False)

        if map_link:
            embed.add_field(name="Map", value=f"[Open Map](<{map_link}>)", inline=False)

        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - Survivor Damage Feed")
        embed.timestamp = event_time
        await channel.send(embed=style_embed(embed))
        return

    embed = discord.Embed(
        title=title,
        description=f"```{line[:1000]}```",
        color=color
    )
    embed.add_field(name="Survivor", value=player, inline=True)
    if map_link:
        embed.add_field(name="Map", value=f"[Open Location](<{map_link}>)", inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Private ADM Feed")
    embed.timestamp = event_time
    await channel.send(embed=style_embed(embed))


async def send_swear_jar_feed(message, found_words, fine, pennies_total):
    guild_id = str(message.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": message.guild.name, "channels": {}})
    channel = await get_or_create_feed_channel(message.guild, config, "swear_jar_feed", "swear-jar")
    if not channel:
        return

    lines = [
        "Language crime detected. The swear jar has been fed.",
        "Another beautiful donation to the bad words retirement fund.",
        "The bot heard that. The bot judged it. The bot invoiced it.",
        "Fine issued with unnecessary confidence.",
    ]

    embed = discord.Embed(
        title="SWEAR JAR INCIDENT",
        description=random.choice(lines),
        color=0xE67E22
    )
    embed.add_field(name="Offender", value=message.author.mention, inline=True)
    embed.add_field(name="Evidence", value=", ".join(f"`{word}`" for word in sorted(set(found_words))), inline=True)
    embed.add_field(name="Fine", value=f"{fine} pennies", inline=True)
    embed.add_field(name="Total Debt", value=f"{pennies_total} pennies", inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Public Shame Department")
    await channel.send(embed=style_embed(embed))


async def maybe_reply_to_bot_mention(message, lower):
    if not message.guild:
        return

    guild_id = str(message.guild.id) if message.guild else None
    channels = guild_configs.get(guild_id, {}).get("channels", {}) if guild_id else {}
    ai_channel_id = channels.get("ai_chat") if guild_id else None
    in_ai_channel = bool(ai_channel_id and message.channel.id == ai_channel_id)
    pve_channel_ids = {
        channels.get(key)
        for key in [
            "pve_quests",
            "pve_hunting",
            "pve_collection",
            "pve_fishing",
            "pve_crafting",
            "pve_expeditions",
            "pve_info",
            "pve_heatmap"
        ]
    }
    in_pve_channel = message.channel.id in pve_channel_ids
    pve_help_request = in_pve_channel and any(
        word in lower
        for word in ["quest", "mission", "where", "find", "hunt", "fish", "craft", "help", "reward"]
    )

    if bot.user not in message.mentions and not in_ai_channel and not pve_help_request:
        return

    now_ts = datetime.now(UTC).timestamp()
    key = f"{message.guild.id}:{message.author.id}"

    reply_cooldown = int(owner_behavior_config(guild_id).get("reply_cooldown_seconds", 45))
    if now_ts - last_ai_direct_response_time.get(key, 0) < max(5, reply_cooldown):
        return

    last_ai_direct_response_time[key] = now_ts

    topic_lines = []

    if any(word in lower for word in ["loot", "where find", "where to find", "guns", "weapon"]):
        topic_lines = [
            "Loot advice: hit hunting camps, military tents, police stations, medical buildings, then get out before someone turns you into a cautionary tale.",
            "If you need weapons, stop licking coastal sheds and move inland. Police for basics, hunting spots for rifles, military zones for proper trouble.",
            "Best loot route is simple: food first, blade second, meds third, ego last. Most people die because they reverse that list like absolute wankers.",
        ]
    elif any(word in lower for word in ["base", "build", "raid"]):
        topic_lines = [
            "Base advice: small, ugly, hidden and boring survives longer than a giant castle screaming 'please raid me'.",
            "Raid tip: screenshots, clips, timestamps. Evidence first, angry shouting second. I know, tragic.",
            "Build low-profile and stash smart. Big obvious bases are just community piñatas with doors.",
        ]
    elif any(word in lower for word in ["sick", "ill", "blood", "health", "medicine", "meds"]):
        topic_lines = [
            "Medical advice: disinfect wounds, keep tetra/charcoal/vitamins, and stop drinking mystery pond water like it owes you money.",
            "If your survivor is coughing, bleeding and seeing grey, congratulations, you have discovered consequences. Bandage, eat, hydrate, warm up.",
        ]
    elif any(word in lower for word in ["car", "truck", "drive", "vehicle"]):
        topic_lines = [
            "Vehicle advice: if the server stutters, slow down. DayZ cars punish optimism with aerospace engineering.",
            "Check plug, battery, radiator and fuel. Then pray, because the car still has a personality problem.",
        ]
    elif any(word in lower for word in ["quest", "mission", "reward"]):
        topic_lines = [
            "Quest advice: pick a route, bring food, screenshot proof for anything the logs cannot track, and link your gamertag so I can pay you when the server catches your heroics.",
            "Mission board wisdom: easy quests are for relaxing, hard quests are for stories, and expedition chains are where the shiny rewards live.",
            "If the quest is hunting, infected, building, or placement based, I can often track it from ADM logs. If it is exploration or collection, staff can approve it with `/pvecomplete`.",
        ]
    elif any(word in lower for word in ["fish", "fishing"]):
        topic_lines = [
            "Fishing advice: bones for hooks, rope for the rod, worms if you are feeling fancy. Cook the fish. Raw fish is just regret with scales.",
            "Find quiet water, stop sprinting, and let the apocalypse become a camping trip for five minutes. Weirdly healing, honestly.",
        ]
    elif any(word in lower for word in ["craft", "crafting"]):
        topic_lines = [
            "Crafting advice: bark, sticks, stones, bones, rope and rags are the holy little pile of survival nonsense. Keep a blade and you can improvise half your life back.",
            "If a quest asks for crafting, screenshot the finished kit unless the ADM logs catch the event. Staff can approve the rest.",
        ]

    help_lines = topic_lines or [
        "I am awake. Unfortunately for everyone, I have opinions. Ask me about raids, loot, bases, sickness, cars, or why your last plan was bollocks.",
        "Yes, survivor? I can help with bot commands, DayZ advice, or emotional support after another deeply avoidable death.",
        "Radio check received. Tell me what you need and I will pretend we are all making sensible choices.",
    ]

    await message.channel.send(
        wb_text("ai", apply_owner_voice_to_text(guild_id, random.choice(help_lines)))
    )


async def maybe_owner_mention_remark(message):
    if not message.guild or not message.guild.owner:
        return

    if message.guild.owner not in message.mentions:
        return

    now_ts = datetime.now(UTC).timestamp()
    guild_id = str(message.guild.id)

    if now_ts - last_owner_mention_time.get(guild_id, 0) < 900:
        return

    last_owner_mention_time[guild_id] = now_ts
    lines = [
        "Owner ping detected. They may respond shortly, or they may be staring at Nitrado like it personally wronged them.",
        "You have summoned the owner. Please allow three to five business panics.",
        "Owner mention logged. If they do not reply, assume they are doing highly important owner things, like fighting settings menus.",
    ]
    await message.channel.send(wb_text("radio", random.choice(lines)))


def faction_key(name):
    return normalize_discord_name(name)


def faction_display_lines(faction):
    members = faction.get("members", [])
    return [
        f"Name: {faction.get('name', 'Unknown')}",
        f"Leader: <@{faction.get('leader_id')}>",
        f"Members: {len(members)}",
        f"Flag: {faction.get('flag', 'Not set')}",
        f"Role: <@&{faction.get('role_id')}>" if faction.get("role_id") else "Role: Not set",
    ]


def ensure_player_stats_record(guild_id, player_name):
    if not player_name or player_name == "Unknown":
        return None

    now_text = str(datetime.now(UTC))
    stats = player_stats.setdefault(player_name, {})
    stats.setdefault("guild_id", str(guild_id))
    stats.setdefault("first_adm_seen", now_text)
    stats.setdefault("kills", 0)
    stats.setdefault("headshots", 0)
    stats.setdefault("vehicle_kills", 0)
    stats.setdefault("vehicle_deaths", 0)
    stats.setdefault("rampages", 0)
    stats.setdefault("multikill_best", 0)
    stats.setdefault("longest_shot_distance", 0)
    stats.setdefault("longest_shot_weapon", "")
    stats.setdefault("longest_shot_victim", "")
    stats.setdefault("bounty_claims", 0)
    stats.setdefault("bounty_earnings", 0)
    stats.setdefault("current_streak_days", 0)
    stats.setdefault("longest_streak_days", 0)
    stats.setdefault("streak_start_date", "")
    stats.setdefault("last_alive_date", "")
    stats.setdefault("deaths", 0)
    stats.setdefault("zombie_deaths", 0)
    stats.setdefault("suicides", 0)
    stats.setdefault("cuts", 0)
    stats.setdefault("bleedouts", 0)
    stats.setdefault("builds", 0)
    stats.setdefault("placements", 0)
    stats.setdefault("packed", 0)
    stats.setdefault("raids", 0)
    stats.setdefault("animals_hunted", 0)
    stats.setdefault("animal_deaths", 0)
    stats.setdefault("flags_raised", 0)
    stats.setdefault("flags_lowered", 0)
    stats.setdefault("time_online_seconds", 0)
    stats["last_seen"] = now_text
    stats["last_adm_seen"] = now_text
    return stats


def add_player_stat(guild_id, player_name, key, amount=1):
    stats = ensure_player_stats_record(guild_id, player_name)
    if not stats:
        return
    stats[key] = stats.get(key, 0) + amount


def update_player_stats_from_adm(guild_id, event_type, line):
    player_name = extract_player_name(line)

    if event_type == "kill":
        kill_details = extract_pvp_kill_details(line)
        if kill_details:
            add_player_stat(guild_id, kill_details["killer"], "kills")
            add_player_stat(guild_id, kill_details["victim"], "deaths")
            if kill_details.get("headshot"):
                add_player_stat(guild_id, kill_details["killer"], "headshots")
            return

    if event_type == "disconnect":
        stats = ensure_player_stats_record(guild_id, player_name)
        started = player_online_times.get(str(guild_id), {}).get(player_name)
        if stats and started:
            stats["time_online_seconds"] = stats.get("time_online_seconds", 0) + int(
                (datetime.now(UTC) - started).total_seconds()
            )
        return

    if event_type == "cut" and "killed by" in line.lower():
        add_player_stat(guild_id, player_name, "cuts")
        add_player_stat(guild_id, player_name, "deaths")
        return

    # Animal kill events may be either a hunt (player killed animal) or
    # a death-by-animal (animal killed player). Disambiguate using the
    # "(DEAD)" + "killed by" + animal-term pattern.
    if event_type == "animal_kill":
        lower = line.lower()
        animal_terms_local = ("wolf", "bear", "cow", "pig", "goat", "sheep",
                              "chicken", "deer", "boar", "rooster", "hen")
        if "(dead)" in lower and "killed by" in lower and any(t in lower for t in animal_terms_local):
            add_player_stat(guild_id, player_name, "animal_deaths")
            add_player_stat(guild_id, player_name, "deaths")
            return

    stat_map = {
        "zombie_kill": ("zombie_deaths", "deaths"),
        "suicide": ("suicides", "deaths"),
        "bleedout": ("bleedouts", "deaths"),
        "cut": ("cuts",),
        "build": ("builds",),
        "placed": ("placements",),
        "packed": ("packed",),
        "raid": ("raids",),
        "animal_kill": ("animals_hunted",),
        "flag_raise": ("flags_raised",),
        "flag_lower": ("flags_lowered",),
    }

    for stat_key in stat_map.get(event_type, []):
        add_player_stat(guild_id, player_name, stat_key)


def format_duration(seconds):
    seconds = int(seconds or 0)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


LEADERBOARD_RANK_ICONS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def leaderboard_rank_icon(index):
    if 1 <= index <= len(LEADERBOARD_RANK_ICONS):
        return LEADERBOARD_RANK_ICONS[index - 1]
    return f"{index}."


def trim_table_text(value, width):
    text = str(value or "Unknown").replace("\n", " ").strip()
    if len(text) <= width:
        return text.ljust(width)
    return (text[: max(1, width - 1)] + "…").ljust(width)


def stat_int(stats, key):
    try:
        return int(stats.get(key, 0) or 0)
    except Exception:
        return 0


def build_kill_leaderboard_rows(rows, limit=10):
    lines = ["#  Survivor              Kills  Deaths  K/D   Online"]

    for index, (player, stats) in enumerate(rows[:limit], start=1):
        kills = stat_int(stats, "kills")
        deaths = stat_int(stats, "deaths")
        kd = kills if deaths == 0 else round(kills / max(1, deaths), 2)
        kd_text = f"{kd:.2f}" if isinstance(kd, float) else str(kd)
        lines.append(
            f"{index:<2} {trim_table_text(player, 21)} {kills:>5}  {deaths:>6}  {kd_text:>4}  {format_duration(stats.get('time_online_seconds', 0)):>6}"
        )

    return "```text\n" + "\n".join(lines) + "\n```"


def build_simple_leaderboard_table(rows, stat_key, heading, limit=5, formatter=None):
    lines = [f"#  Survivor              {heading}"]

    for index, (player, stats) in enumerate(rows[:limit], start=1):
        value = stats.get(stat_key, 0)
        if formatter:
            value = formatter(value)
        lines.append(f"{index:<2} {trim_table_text(player, 21)} {str(value):>8}")

    if len(lines) == 1:
        return "No data yet. ADM activity will fill this in."

    return "```text\n" + "\n".join(lines) + "\n```"


def build_topkills_grid_embed(guild):
    guild_id = str(guild.id)
    guild_players = [
        (player, stats)
        for player, stats in player_stats.items()
        if str(stats.get("guild_id", "")) == guild_id
    ]
    rows = guild_players or list(player_stats.items())

    sorted_players = sorted(
        rows,
        key=lambda row: row[1].get("kills", 0),
        reverse=True
    )

    total_kills = sum(stat_int(stats, "kills") for _, stats in rows)
    total_deaths = sum(stat_int(stats, "deaths") for _, stats in rows)

    embed = discord.Embed(
        title="☠️ SERVER TOP KILLS",
        description=(
            "Clear combat grid: kills, deaths, K/D, and tracked online time.\n"
            + build_kill_leaderboard_rows(sorted_players, 10)
        ),
        color=0x992D22
    )
    embed.add_field(name="☠️ Total Kills", value=str(total_kills), inline=True)
    embed.add_field(name="💀 Total Deaths", value=str(total_deaths), inline=True)
    embed.add_field(name="👥 Survivors Ranked", value=str(len(rows)), inline=True)
    embed.add_field(
        name="📍 Scope",
        value="This server" if guild_players else "Global fallback until this server has ADM stats",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    return style_embed(embed)


def build_longshots_grid_embed():
    """Top 10 longshots across all guilds — flat, ranked, with podium
    icons, weapon, victim, distance and source server."""
    flat = []
    for guild_id, records in longshot_records.items():
        if isinstance(records, list):
            for entry in records:
                if not isinstance(entry, dict):
                    continue
                flat.append((guild_id, entry))
        elif isinstance(records, dict) and records.get("killer"):
            flat.append((guild_id, records))

    flat.sort(
        key=lambda row: float(row[1].get("distance", 0) or 0),
        reverse=True,
    )

    embed = discord.Embed(
        title="🎯 GLOBAL LONGSHOT LEADERBOARD",
        color=0xF1C40F,
    )

    if not flat:
        embed.description = (
            "No 300m+ shots recorded yet.\n\n"
            "Once your ADM feed sees one, it'll show up here automatically and "
            "persist across bot restarts."
        )
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha — Longshot Intelligence")
        return style_embed(embed)

    description_lines = []
    for index, (guild_id, entry) in enumerate(flat[:10], start=1):
        icon = leaderboard_rank_icon(index)
        killer = str(entry.get("killer", "Unknown"))[:24]
        victim = str(entry.get("victim", "Unknown"))[:22]
        weapon = str(entry.get("weapon", "Unknown"))[:24]
        distance = float(entry.get("distance", 0) or 0)
        guild_name = guild_configs.get(guild_id, {}).get("guild_name", "Server")
        description_lines.append(
            f"{icon} **`{distance:>5.1f}m`** — **{killer}** → {victim}\n"
            f"      🔫 {weapon}  ·  🌍 *{guild_name[:24]}*"
        )

    embed.description = "\n\n".join(description_lines)
    # Show #1 record-holder prominently in a field
    top = flat[0][1]
    embed.add_field(
        name="🏆 Current Server Record-Holder",
        value=(
            f"**{top.get('killer', 'Unknown')}** at **{float(top.get('distance', 0) or 0):.1f}m**\n"
            f"with **{top.get('weapon', 'Unknown')}** on *{top.get('victim', 'Unknown')}*"
        ),
        inline=False,
    )
    embed.add_field(
        name="📊 Total Longshots Tracked",
        value=str(len(flat)),
        inline=True,
    )
    embed.add_field(
        name="🎯 Threshold",
        value=f"{LONGSHOT_ANNOUNCE_METERS}m+",
        inline=True,
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha — Longshot Intelligence")
    embed.timestamp = datetime.now(UTC)
    return style_embed(embed)


def build_showcase_topkills_embed(guild):
    guild_id = str(guild.id)
    guild_players = [
        (player, stats)
        for player, stats in player_stats.items()
        if str(stats.get("guild_id", "")) == guild_id
    ]
    rows = guild_players or list(player_stats.items())
    sorted_players = sorted(rows, key=lambda row: row[1].get("kills", 0), reverse=True)
    total_kills = sum(stat_int(stats, "kills") for _, stats in rows)
    total_deaths = sum(stat_int(stats, "deaths") for _, stats in rows)

    embed = discord.Embed(
        title="☠️ SERVER TOP KILLS",
        description="Combat board with podium highlights plus a clean stat grid.\n" + build_kill_leaderboard_rows(sorted_players, 10),
        color=0x992D22
    )
    embed.add_field(name="☠️ Total Kills", value=str(total_kills), inline=True)
    embed.add_field(name="💀 Total Deaths", value=str(total_deaths), inline=True)
    embed.add_field(name="👥 Survivors Ranked", value=str(len(rows)), inline=True)

    for index, (player, stats) in enumerate(sorted_players[:3], start=1):
        icon = leaderboard_rank_icon(index)
        kills = stat_int(stats, "kills")
        deaths = stat_int(stats, "deaths")
        kd = kills if deaths == 0 else round(kills / max(1, deaths), 2)
        embed.add_field(
            name=f"{icon} {player}",
            value=f"☠️ `{kills}` kills\n💀 `{deaths}` deaths\n⚖️ `{kd}` K/D",
            inline=True
        )

    embed.add_field(
        name="📍 Scope",
        value="This server" if guild_players else "Global fallback until this server has ADM stats",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    return style_embed(embed)


def build_showcase_longshots_embed():
    sorted_records = sorted(
        longshot_records.items(),
        key=lambda row: row[1].get("distance", 0),
        reverse=True
    )
    lines = ["#  Shooter               Dist   Server"]
    for index, (guild_id, data) in enumerate(sorted_records[:10], start=1):
        guild_name = guild_configs.get(guild_id, {}).get("guild_name", "Unknown Server")
        lines.append(
            f"{index:<2} {trim_table_text(data.get('killer'), 21)} {str(data.get('distance', 0)) + 'm':>6}  {trim_table_text(guild_name, 18).strip()}"
        )

    embed = discord.Embed(
        title="🎯 GLOBAL LONGSHOT LEADERBOARD",
        description="Longest confirmed shots across all connected servers.\n```text\n" + "\n".join(lines) + "\n```",
        color=0xF1C40F
    )
    for index, (guild_id, data) in enumerate(sorted_records[:3], start=1):
        guild_name = guild_configs.get(guild_id, {}).get("guild_name", "Unknown Server")
        embed.add_field(
            name=f"{leaderboard_rank_icon(index)} {data.get('killer', 'Unknown')}",
            value=f"🎯 `{data.get('distance', 0)}m`\n🌍 `{guild_name}`",
            inline=True
        )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Longshot Intelligence")
    return style_embed(embed)


def parse_saved_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def edit_distance(left, right):
    left = str(left)
    right = str(right)

    if left == right:
        return 0

    distances = [
        [0 for _ in range(len(right) + 1)]
        for _ in range(len(left) + 1)
    ]

    for left_index in range(len(left) + 1):
        distances[left_index][0] = left_index

    for right_index in range(len(right) + 1):
        distances[0][right_index] = right_index

    for left_index, left_char in enumerate(left, start=1):
        for right_index, right_char in enumerate(right, start=1):
            replace_cost = 0 if left_char == right_char else 1
            distances[left_index][right_index] = min(
                distances[left_index - 1][right_index] + 1,
                distances[left_index][right_index - 1] + 1,
                distances[left_index - 1][right_index - 1] + replace_cost,
            )

            if (
                left_index > 1
                and right_index > 1
                and left[left_index - 1] == right[right_index - 2]
                and left[left_index - 2] == right[right_index - 1]
            ):
                distances[left_index][right_index] = min(
                    distances[left_index][right_index],
                    distances[left_index - 2][right_index - 2] + 1,
                )

    return distances[-1][-1]


def closest_adm_player_name(guild_id, typed_name):
    wanted = normalize_discord_name(typed_name)
    if not wanted:
        return None

    best_name = None
    best_distance = None

    for player_name, stats in player_stats.items():
        if str(stats.get("guild_id", "")) != str(guild_id):
            continue

        candidate = normalize_discord_name(player_name)
        if not candidate:
            continue

        distance = edit_distance(wanted, candidate)
        allowed_distance = 1 if len(candidate) <= 5 else 2 if len(candidate) <= 12 else 3
        if distance > allowed_distance:
            continue

        if best_distance is None or distance < best_distance:
            best_name = player_name
            best_distance = distance

    return best_name


def learn_recent_adm_players_for_linking(guild_id, config, hours=168, max_logs=40):
    ensure_guild_runtime(str(guild_id))

    adm_logs = list_adm_logs(config, hours)
    if not adm_logs:
        latest_log = ping_latest_adm_log(config)
        adm_logs = [latest_log] if latest_log else []

    adm_logs = [adm_log for adm_log in adm_logs if adm_log][:max(1, int(max_logs or 40))]

    learned = 0
    scanned_logs = 0

    for adm_log in adm_logs:
        if not adm_log:
            continue

        if not download_latest_adm(guild_id, config, adm_log):
            continue

        adm_path = os.path.join(GUILD_DATA_FOLDER, f"{guild_id}.ADM")
        if not os.path.exists(adm_path):
            continue

        scanned_logs += 1
        log_seen_at = parse_saved_datetime(adm_log.get("_adm_datetime")) or adm_log_datetime(adm_log)
        log_seen_text = str(log_seen_at or (datetime.now(UTC) - timedelta(hours=hours)))

        with open(adm_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]

        for line in lines:
            for player_name in extract_adm_player_names(line):
                if not player_name or player_name == "Unknown":
                    continue

                stats = ensure_player_stats_record(guild_id, player_name)
                if not stats:
                    continue

                existing_first_seen = parse_saved_datetime(stats.get("first_adm_seen"))
                if not existing_first_seen or (log_seen_at and log_seen_at < existing_first_seen):
                    stats["first_adm_seen"] = log_seen_text

                stats["last_adm_seen"] = log_seen_text
                learned += 1

            remember_player_location_from_adm(guild_id, line)

    if learned:
        save_player_stats()

    return learned, scanned_logs


def find_adm_verified_player(guild_id, typed_name, minimum_age_seconds=300):
    wanted = normalize_discord_name(typed_name)
    if not wanted:
        return None, "Type the exact gamertag that appears in the server ADM logs."

    matches = []
    for player_name, stats in player_stats.items():
        if str(stats.get("guild_id", "")) != str(guild_id):
            continue

        if normalize_discord_name(player_name) == wanted:
            matches.append((player_name, stats))

    if not matches:
        suggestion = closest_adm_player_name(guild_id, typed_name)
        if suggestion:
            return None, f"That gamertag has not appeared exactly in ADM. Did you mean `{suggestion}`? Try `/linkgamer gamertag:{suggestion}`."

        return None, "That gamertag has not appeared in this server's ADM logs yet. Join the server first, wait at least 5 minutes, then try again."

    player_name, stats = matches[0]
    first_seen = parse_saved_datetime(stats.get("first_adm_seen") or stats.get("last_adm_seen") or stats.get("last_seen"))
    if not first_seen:
        return None, "That gamertag was found, but its ADM timestamp is missing. Wait for the next ADM scan, then try again."

    age_seconds = (datetime.now(UTC) - first_seen).total_seconds()
    if age_seconds < minimum_age_seconds:
        wait_minutes = max(1, int((minimum_age_seconds - age_seconds + 59) // 60))
        return None, f"That gamertag was just seen in ADM. Wait about `{wait_minutes}` more minute(s), then try again."

    return player_name, None


def gamertag_linked_to_other_user(gamertag, user_id):
    wanted = normalize_discord_name(gamertag)
    for linked_user_id, data in linked_players.items():
        if str(linked_user_id) == str(user_id):
            continue
        if normalize_discord_name(data.get("gamertag", "")) == wanted:
            return linked_user_id, data
    return None, None


async def announce_verified_gamer_link(guild, config, member, gamertag):
    channel = await get_or_create_feed_channel(
        guild,
        config,
        "linked_players",
        DEFAULT_CHANNEL_NAMES["linked_players"],
        private=False
    )

    embed = discord.Embed(
        title="VERIFIED GAMERTAG LINKED",
        description=f"{member.mention} is now verified as `{gamertag}`.",
        color=0x2ECC71
    )
    embed.add_field(name="Discord", value=str(member), inline=True)
    embed.add_field(name="ADM Verified Gamertag", value=gamertag, inline=True)
    embed.add_field(name="Recognition", value="Identity confirmed from ADM history and ready for economy rewards.", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Verified Identity")
    await channel.send(embed=style_embed(embed))


def build_linkgamer_confirmation_embed(member, gamertag):
    embed = discord.Embed(
        title="VERIFIED GAMERTAG LINKED",
        description=f"{member.mention} has linked an ADM verified survivor name.",
        color=0x2ECC71
    )
    embed.add_field(name="Discord User", value=f"{member.mention}\n`{member}`", inline=False)
    embed.add_field(name="ADM Verified Gamertag", value=f"`{gamertag}`", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Identity System")
    return embed


async def link_verified_gamertag_for_member(guild, member, gamertag):
    guild_id = str(guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": guild.name, "channels": {}})
    verified_name, error = find_adm_verified_player(guild_id, gamertag, minimum_age_seconds=0)
    learned = 0
    scanned_logs = 0

    if error:
        required_keys = ["nitrado_token", "service_id", "nitrado_user"]
        if all(config.get(key) for key in required_keys):
            try:
                learned, scanned_logs = await asyncio.to_thread(
                    learn_recent_adm_players_for_linking,
                    guild_id,
                    config,
                    168,
                    40
                )
                verified_name, error = find_adm_verified_player(guild_id, gamertag, minimum_age_seconds=0)
            except Exception as scan_error:
                print(f"LINK ADM LOOKBACK ERROR {guild_id}: {scan_error}")

    if error:
        suggestion = closest_adm_player_name(guild_id, gamertag)
        suggestion_text = f"\nClosest ADM name I know: `{suggestion}`." if suggestion else ""
        return False, (
            f"{error}\n\n"
            f"I searched saved stats and scanned `{scanned_logs}` recent ADM log(s), learning `{learned}` player name entry/entries.{suggestion_text}\n"
            "If the name has spaces or symbols, type it exactly as it appears in the ADM log. Staff can run `/admplayers` to see names I have learned."
        )

    linked_user_id, linked_data = gamertag_linked_to_other_user(verified_name, member.id)
    if linked_user_id:
        return False, f"`{verified_name}` is already linked to `{linked_data.get('discord_name', linked_user_id)}`. Ask staff if this needs correcting."

    user_id = str(member.id)
    linked_players[user_id] = {
        "discord_name": str(member),
        "discord_id": user_id,
        "guild_id": guild_id,
        "gamertag": verified_name,
        "verified_by": "ADM",
        "linked_at": str(datetime.now(UTC))
    }

    save_linked_players()
    await announce_verified_gamer_link(guild, config, member, verified_name)
    return True, verified_name

# =========================================================
# AUTONOMOUS SHOWCASE ENGINE
# =========================================================

SHOWCASE_GREETING_TRIGGERS = {"hi", "hello", "hey", "sup", "yo", "hiya", "howdy", "greetings", "ello", "heya"}

SHOWCASE_IMAGE_REQUEST_TRIGGERS = [
    "generate", "make me", "create", "draw", "show me", "give me", "post",
    "art", "image", "picture", "pic", "photo", "visual", "artwork", "illustration"
]

SHOWCASE_STYLE_TRIGGERS = {
    "cinematic": "gritty",
    "gritty": "gritty",
    "dark": "gritty",
    "horror": "gritty",
    "moody": "gritty",
    "atmospheric": "gritty",
    "funny": "funny",
    "humor": "funny",
    "comedy": "funny",
    "meme": "funny",
    "silly": "funny",
    "survival": "funny",
    "pinup": "pinup",
    "glamour": "pinup",
    "stylish": "pinup",
}

SHOWCASE_DISCUSSION_STARTERS = [
    ("🔥 DAILY QUESTION", "What's the most embarrassing way you've died in DayZ? I'll start: someone once died to a chicken. The chicken won."),
    ("🧠 SURVIVAL DEBATE", "Hottest take: the coast is actually the most dangerous zone on the map. Change my mind."),
    ("🎯 TACTICS CORNER", "What's your go-to first 10 minutes strategy when you spawn? Inland rush? Coastal loot? Straight to military?"),
    ("🏕️ BASE BUILDING POLL", "Small hidden stash vs. big fortified compound — which actually survives longer on your server?"),
    ("⚔️ PVP PHILOSOPHY", "Do you KOS on sight or try to talk first? What's your personal code of conduct in the apocalypse?"),
    ("🗺️ MAP KNOWLEDGE", "Which location on Chernarus do you think is criminally underrated for loot? Drop your secret spots."),
    ("🤝 FACTION TALK", "Would you rather run solo or roll with a faction? What's the ideal squad size for DayZ?"),
    ("🧟 ZOMBIE THREAT LEVEL", "Real talk: how much of a threat are infected to you at this point? Nuisance or genuine danger?"),
    ("🚗 VEHICLE CHAOS", "Best DayZ vehicle story. Go. Bonus points if it ended in a fireball."),
    ("🌧️ WEATHER SURVIVAL", "Rain, fog, night — which weather condition do you find most dangerous and why?"),
    ("🎒 LOADOUT FLEX", "Describe your ideal DayZ loadout in three items. No cheating with 'everything'."),
    ("📻 RADIO CHATTER", "If you could add one feature to DayZ that doesn't exist yet, what would it be?"),
]

SHOWCASE_TIPS = [
    ("💡 SURVIVAL TIP", "Disinfect every wound, even small cuts. Infection kills slower than bullets but just as dead."),
    ("💡 LOOT ROUTE TIP", "Police stations respawn faster than military. Hit them early, hit them often."),
    ("💡 BASE TIP", "The best base is one nobody knows exists. Small, ugly, and hidden beats big and obvious every time."),
    ("💡 PVP TIP", "Sound is your best intel. Footsteps, doors, and gunshots tell you everything before you see anything."),
    ("💡 MEDICAL TIP", "Carry charcoal tablets. Cholera from dirty water is one of the most common silent killers."),
    ("💡 NAVIGATION TIP", "Learn to navigate by landmarks, not the compass. The compass tells you direction; the map tells you where you are."),
    ("💡 VEHICLE TIP", "Always check the spark plug, battery, and radiator before assuming a car is broken. It's usually one of those three."),
    ("💡 FOOD TIP", "Hunting is more reliable than looting for food mid-game. Animals respawn; canned goods don't."),
    ("💡 STEALTH TIP", "Walk, don't sprint, through towns. Sprinting is loud and you miss loot. Patience is a survival skill."),
    ("💡 FACTION TIP", "Establish a radio frequency with your squad before you split up. Communication wins fights."),
]

SHOWCASE_FEATURE_SPOTLIGHTS = [
    ("🔥 FEATURE: LIVE KILLFEED", "Wandering Bot tracks every PvP kill in real time from your server's ADM logs and posts them to a dedicated killfeed channel — killer, victim, weapon, distance, and map coordinates."),
    ("🗺️ FEATURE: HEATMAPS", "The bot generates live heatmap images showing where PvP, zombie kills, base building, and raids are happening most on your map. Updated automatically."),
    ("🏆 FEATURE: LEADERBOARDS", "Automatic kill leaderboards, longshot records, and player stat tracking — all pulled from ADM logs with zero manual input required."),
    ("💰 FEATURE: ECONOMY SYSTEM", "A full in-game economy: pennies, a shop, item deliveries, vehicle rentals, recurring wages, and a swear jar. All Discord-native."),
    ("🏴 FEATURE: FACTION SYSTEM", "Players can create, join, and manage factions directly in Discord. Faction roles, member lists, and dedicated channels — all bot-managed."),
    ("🧭 FEATURE: PVE QUEST BOARD", "Automated PVE quest channels with hunting, fishing, crafting, collection, and expedition missions. Quests rotate automatically when completed."),
    ("🌍 FEATURE: AUTO TRANSLATION", "The bot can automatically translate messages in any channel to a target language, making international communities seamless."),
    ("🎫 FEATURE: SUPPORT TICKETS", "Built-in support ticket system. Players open tickets, staff respond, everything is logged. No third-party bots needed."),
    ("🔗 FEATURE: GAMERTAG LINKING", "Players link their Xbox/PC gamertag to their Discord account via ADM verification. The bot confirms identity from server logs automatically."),
    ("🤖 FEATURE: AI CHAT", "A dedicated AI channel where survivors can ask the bot for loot tips, base advice, medical help, and DayZ strategy — all with personality."),
]

SHOWCASE_WELCOME_MESSAGES_EXTENDED = [
    "Welcome to the showcase, survivor. I run this place. The owner's around somewhere but honestly I've got it handled.",
    "Fresh arrival detected. I'm Wandering Bot — I manage this server, generate content, track stats, and occasionally roast bad decisions. Welcome.",
    "Hey! You made it. This server is proof that a bot can run a community. Pull up a chair and see what I can do.",
    "Welcome in. I'm the host, the moderator, the entertainer, and the AI. The owner just watches and nods approvingly.",
    "New survivor spotted. I'm Wandering Bot — autonomous community manager, DayZ intelligence system, and reluctant philosopher. Ask me anything.",
    "Welcome to the showcase. I'm demonstrating that a Discord server can be fully managed by a bot. You're part of the experiment now.",
    "Ah, a new face. I'm Wandering Bot. I handle the channels, the content, the conversations, and the chaos. The owner handles the coffee.",
    "Welcome! This server runs itself — well, I run it. Same thing. Grab a channel and see what autonomous bot management looks like.",
]

SHOWCASE_REACTION_MAP = {
    "kill": ["💀", "🎯", "🔥"],
    "die": ["💀", "😬", "🩸"],
    "base": ["🏕️", "🔨", "🛡️"],
    "loot": ["🎒", "✨", "🥫"],
    "raid": ["🚨", "💥", "🏴"],
    "beans": ["🥫", "😂", "🙏"],
    "wolf": ["🐺", "😱", "💀"],
    "car": ["🚗", "💥", "😬"],
    "snipe": ["🎯", "😤", "🔥"],
    "help": ["🤝", "📻", "🧠"],
    "nice": ["✨", "🔥", "👏"],
    "good": ["✨", "👍", "🔥"],
    "wow": ["😮", "🔥", "✨"],
    "haha": ["😂", "💀", "🔥"],
    "lol": ["😂", "💀", "🔥"],
}

SHOWCASE_FOLLOW_UP_QUESTIONS = [
    "What's your usual playstyle — PvP, PvE, or somewhere in between?",
    "Have you tried the faction system yet? It changes the whole dynamic.",
    "What server are you playing on right now?",
    "What feature would you want to see in a bot like this?",
    "How long have you been playing DayZ?",
    "Solo player or squad runner?",
    "What's your most memorable DayZ moment?",
    "What do you think makes a good DayZ community server?",
]

SHOWCASE_CHANNEL_SUGGESTIONS = {
    "loot": "ai_chat",
    "help": "ai_chat",
    "quest": "pve_quests",
    "mission": "pve_quests",
    "hunt": "pve_hunting",
    "fish": "pve_fishing",
    "craft": "pve_crafting",
    "expedition": "pve_expeditions",
    "kill": "killfeed",
    "pvp": "pvp_intel",
    "base": "general_chat",
    "faction": "factions_chat",
    "economy": "economy",
    "shop": "economy",
    "buy": "economy",
}

# Extended AI image prompts for showcase styles
AI_IMAGE_PROMPTS_SHOWCASE = {
    "cinematic": [
        "A dramatic cinematic wide-angle photo of a lone adult DayZ survivor silhouetted against a burning horizon in a ruined Eastern European city, golden hour light, smoke rising, survival atmosphere, no logos, no text, no game UI",
        "A cinematic aerial-style photo of an adult survivor crossing a misty valley between two ruined villages in Chernarus, backpack visible, rifle slung, moody overcast sky, no logos, no text",
        "A cinematic close-up portrait of a weathered adult survivor in tactical gear looking into the distance from a rooftop, ruined city below, dramatic lighting, no logos, no text",
    ],
    "horror": [
        "A dark atmospheric photo of an adult DayZ survivor cautiously moving through a fog-filled abandoned hospital corridor, flashlight beam cutting through darkness, tense survival horror mood, no logos, no text, non-graphic",
        "A moody night-time photo of an adult survivor crouching behind a ruined wall while infected shamble past in the background, moonlight, tension, survival horror atmosphere, no logos, no text, non-graphic",
        "A haunting photo of an abandoned Chernarus village at dusk, empty streets, broken windows, a lone adult survivor visible in the distance, eerie silence, no logos, no text",
    ],
    "survival": [
        "A realistic documentary-style photo of an adult DayZ survivor setting up a woodland camp at dusk, small fire, improvised shelter, backpack and gear laid out, peaceful survival moment, no logos, no text",
        "A realistic photo of an adult survivor carefully tending to a wound beside a stream in a Chernarus forest, first aid kit open, calm focus, survival realism, no logos, no text, non-graphic",
        "A realistic photo of two adult survivors sharing a meal of canned food beside a campfire in a ruined barn, camaraderie, post-apocalyptic warmth, no logos, no text",
    ],
}


def is_showcase_guild(guild_id):
    """Return True if this guild is the designated showcase server."""
    guild_key = str(guild_id)
    if SHOWCASE_GUILD_ID and guild_key == str(SHOWCASE_GUILD_ID):
        return True
    config = guild_configs.get(guild_key, {})
    return bool(config.get("is_showcase_guild") or config.get("showcase_mode"))


def update_user_style_profile(user_id, message_content):
    """Track communication style signals for a user."""
    profile = user_style_profiles.setdefault(str(user_id), {
        "message_count": 0,
        "casual_signals": 0,
        "technical_signals": 0,
        "meme_signals": 0,
        "formal_signals": 0,
        "question_count": 0,
        "last_seen": 0,
    })

    lower = message_content.lower()
    profile["message_count"] += 1
    profile["last_seen"] = datetime.now(UTC).timestamp()

    # Casual signals
    if any(w in lower for w in ["lol", "lmao", "haha", "bruh", "ngl", "tbh", "imo", "omg", "wtf", "rip"]):
        profile["casual_signals"] += 1
    # Meme signals
    if any(w in lower for w in ["kek", "based", "cope", "seethe", "ratio", "w ", "l ", "no cap", "fr fr", "bussin"]):
        profile["meme_signals"] += 1
    # Technical signals
    if any(w in lower for w in ["config", "setup", "api", "token", "nitrado", "ftp", "adm", "log", "command", "slash"]):
        profile["technical_signals"] += 1
    # Formal signals
    if len(message_content) > 80 and message_content[0].isupper() and message_content.endswith("."):
        profile["formal_signals"] += 1
    # Questions
    if "?" in message_content:
        profile["question_count"] += 1


def get_user_style(user_id):
    """Return the dominant communication style for a user."""
    profile = user_style_profiles.get(str(user_id), {})
    if not profile or profile.get("message_count", 0) < 3:
        return "neutral"

    scores = {
        "casual": profile.get("casual_signals", 0),
        "meme": profile.get("meme_signals", 0),
        "technical": profile.get("technical_signals", 0),
        "formal": profile.get("formal_signals", 0),
    }
    dominant = max(scores, key=scores.get)
    if scores[dominant] == 0:
        return "neutral"
    return dominant


def adapt_response_to_style(base_response, user_style):
    """Lightly adapt a response to match the user's communication style."""
    if user_style == "casual":
        return base_response.rstrip(".") + " lol"
    if user_style == "meme":
        return base_response.rstrip(".") + " (based survival tip ngl)"
    if user_style == "technical":
        return base_response  # Keep it clean and precise
    if user_style == "formal":
        return base_response  # Already formal enough
    return base_response


async def showcase_generate_and_post_image(channel, style, caption_prefix=""):
    """Generate an AI image and post it to the given channel."""
    if not OPENAI_API_KEY:
        return False

    resolved_style = SHOWCASE_STYLE_TRIGGERS.get(style, style)
    if resolved_style not in AI_IMAGE_PROMPTS_SHOWCASE and resolved_style not in AI_IMAGE_PROMPTS:
        resolved_style = "gritty"

    # Use showcase prompts if available, else fall back to main prompts
    prompts = AI_IMAGE_PROMPTS_SHOWCASE.get(resolved_style) or AI_IMAGE_PROMPTS.get(resolved_style, AI_IMAGE_PROMPTS["funny"])
    prompt = random.choice(prompts)

    image_bytes, error = await asyncio.to_thread(generate_ai_image_bytes, resolved_style)
    if error or not image_bytes:
        print(f"[SHOWCASE IMAGE ERROR] {error}")
        return False

    captions = [
        f"{caption_prefix}Field sketch from the Wandering Bot imagination department.",
        f"{caption_prefix}Little apocalypse postcard, freshly generated.",
        f"{caption_prefix}I made art. Whether it's good art is a separate question.",
        f"{caption_prefix}Visual morale support, delivered with questionable confidence.",
        f"{caption_prefix}Freshly hallucinated survivor content. You're welcome.",
    ]

    file = discord.File(io.BytesIO(image_bytes), filename="wandering_showcase.png")
    embed = discord.Embed(
        title="🎨 WANDERING BOT — AI GENERATED ART",
        description=random.choice(captions),
        color=0x9B59B6
    )
    embed.set_image(url="attachment://wandering_showcase.png")
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text=f"Wandering Bot • Autonomous Showcase • Style: {resolved_style}")
    embed.timestamp = datetime.now(UTC)
    await channel.send(embed=style_embed(embed), file=file)
    return True


async def showcase_handle_greeting(message, guild_id):
    """Respond to greetings with personality and optionally generate an image."""
    now_ts = datetime.now(UTC).timestamp()
    cooldown_key = guild_id

    # Greeting response
    user_style = get_user_style(str(message.author.id))
    greeting_lines = [
        f"Hey {message.author.mention}! Welcome to the showcase. I'm Wandering Bot — I run this place. Ask me anything, or just hang out.",
        f"Oi, {message.author.mention}! Good to see you. This server is proof a bot can manage a community. Feel free to poke around.",
        f"Hey {message.author.mention}! I'm the host here. The owner's watching from the sidelines — I've got the actual running of things covered.",
        f"Welcome {message.author.mention}! Pull up a channel. I'm Wandering Bot: autonomous community manager, DayZ intelligence system, and occasional artist.",
        f"Hey {message.author.mention}! You've arrived at the showcase server. I manage everything here — channels, content, conversations. Ask me what I can do.",
    ]
    response = apply_owner_voice_to_text(
        guild_id,
        adapt_response_to_style(random.choice(greeting_lines), user_style)
    )
    await message.channel.send(response)

    # Generate a greeting image if cooldown allows
    last_img = last_showcase_greeting_image.get(cooldown_key, 0)
    greeting_image_cooldown = int(os.getenv("SHOWCASE_GREETING_IMAGE_COOLDOWN", "1800"))
    if now_ts - last_img >= greeting_image_cooldown:
        last_showcase_greeting_image[cooldown_key] = now_ts
        await asyncio.sleep(1.5)
        await showcase_generate_and_post_image(
            message.channel,
            "gritty",
            caption_prefix="Welcome postcard — "
        )


async def showcase_handle_image_request(message, lower, guild_id):
    """Handle explicit image/art generation requests."""
    # Detect style from message
    detected_style = "gritty"
    for trigger, style in SHOWCASE_STYLE_TRIGGERS.items():
        if trigger in lower:
            detected_style = style
            break

    await message.channel.send(
        f"📸 On it, {message.author.mention}. Generating a `{detected_style}` DayZ image now — give me a moment..."
    )

    now_ts = datetime.now(UTC).timestamp()
    last_showcase_greeting_image[guild_id] = now_ts

    success = await showcase_generate_and_post_image(message.channel, detected_style)
    if not success:
        await message.channel.send(
            "📻 Image generation is offline right now — `OPENAI_API_KEY` may not be configured. Ask the owner to check the env vars."
        )


async def showcase_handle_smart_response(message, lower, guild_id):
    """Provide context-aware, smart responses in the showcase server."""
    user_style = get_user_style(str(message.author.id))
    channels = guild_configs.get(guild_id, {}).get("channels", {})

    response = None
    channel_suggestion = None

    # Feature questions
    if any(w in lower for w in ["what can you do", "what do you do", "features", "capabilities", "show me what"]):
        spotlight = random.choice(SHOWCASE_FEATURE_SPOTLIGHTS)
        embed = discord.Embed(title=spotlight[0], description=spotlight[1], color=0x3498DB)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot • Autonomous Showcase — ask me about any feature")
        await message.channel.send(embed=style_embed(embed))
        # Follow up with a question
        await asyncio.sleep(2)
        await message.channel.send(
            wb_text("ai", apply_owner_voice_to_text(
                guild_id,
                adapt_response_to_style(random.choice(SHOWCASE_FOLLOW_UP_QUESTIONS), user_style)
            ))
        )
        return

    # Setup/technical questions
    if any(w in lower for w in ["how do i set up", "how to setup", "how to install", "how to configure", "nitrado", "ftp", "api key"]):
        response = (
            "Setup is straightforward: invite the bot, run `/setup` with your Nitrado token, service ID, and FTP credentials, "
            "then run `/restartadm force` once to kick off the ADM feed. "
            "The bot auto-creates all channels and starts tracking immediately. "
            "Want me to walk through any specific part?"
        )

    # Economy questions
    elif any(w in lower for w in ["economy", "pennies", "shop", "buy", "wallet", "money"]):
        response = "The economy system runs on pennies — earned through activity, spent in the shop on in-game item deliveries. Try `/wallet` to check your balance or `/shop` to browse items."
        channel_suggestion = channels.get("economy")

    # Faction questions
    elif any(w in lower for w in ["faction", "group", "clan", "team"]):
        response = "Factions are Discord-native groups with roles, member lists, and dedicated channels. Create one with `/createfaction` or join an existing one. Full faction management, all in Discord."
        channel_suggestion = channels.get("factions_chat")

    # PVE questions
    elif any(w in lower for w in ["pve", "quest", "mission", "hunting", "fishing", "crafting"]):
        response = "The PVE quest board runs automatically — hunting, fishing, crafting, collection, and expedition missions rotate through dedicated channels. Check the PVE section for active quests."
        channel_suggestion = channels.get("pve_quests")

    # Leaderboard questions
    elif any(w in lower for w in ["leaderboard", "top kills", "stats", "ranking", "best player"]):
        response = "Kill leaderboards, longshot records, and player stats are all tracked automatically from ADM logs. Try `/topkills` or `/toplongshots` to see the boards."

    # Heatmap questions
    elif any(w in lower for w in ["heatmap", "hot zone", "where is pvp", "where do people fight"]):
        response = "The heatmap shows real-time conflict zones — PvP, zombie kills, raids, base building — all plotted on the map image. It updates automatically from ADM data."

    # General DayZ advice
    elif any(w in lower for w in ["tip", "advice", "help", "how do i", "where do i", "what should i"]):
        tip = random.choice(SHOWCASE_TIPS)
        embed = discord.Embed(title=tip[0], description=tip[1], color=0x1ABC9C)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot • Autonomous Showcase")
        await message.channel.send(embed=style_embed(embed))
        return

    if response:
        adapted = apply_owner_voice_to_text(guild_id, adapt_response_to_style(response, user_style))
        msg = wb_text("ai", adapted)
        if channel_suggestion:
            channel_obj = message.guild.get_channel(channel_suggestion)
            if channel_obj:
                msg += f"\n\n📍 Head to {channel_obj.mention} for that."
        await message.channel.send(msg)

        # Occasionally ask a follow-up
        if random.random() < 0.4:
            await asyncio.sleep(2)
            await message.channel.send(
                wb_text("spark", apply_owner_voice_to_text(
                    guild_id,
                    adapt_response_to_style(random.choice(SHOWCASE_FOLLOW_UP_QUESTIONS), user_style)
                ))
            )


async def showcase_maybe_react(message, lower):
    """Add relevant emoji reactions to messages in the showcase server."""
    now_ts = datetime.now(UTC).timestamp()
    channel_key = str(message.channel.id)

    if now_ts - last_showcase_reaction_time.get(channel_key, 0) < 30:
        return

    for keyword, emojis in SHOWCASE_REACTION_MAP.items():
        if keyword in lower:
            try:
                await message.add_reaction(random.choice(emojis))
                last_showcase_reaction_time[channel_key] = now_ts
            except Exception:
                pass
            break


async def showcase_handle_message(message, lower, guild_id, now_ts):
    """
    Main entry point for autonomous showcase message handling.
    Called from on_message when the guild is the showcase server.
    """
    # Always update style profile
    update_user_style_profile(str(message.author.id), message.content)

    # React to messages
    await showcase_maybe_react(message, lower)

    # Check for greeting triggers (hi/hello/hey etc.)
    words = set(lower.split())
    if words & SHOWCASE_GREETING_TRIGGERS:
        await showcase_handle_greeting(message, guild_id)
        return

    # Check for explicit image/art requests
    is_image_request = any(trigger in lower for trigger in SHOWCASE_IMAGE_REQUEST_TRIGGERS)
    is_dayz_context = any(w in lower for w in ["dayz", "survivor", "chernarus", "image", "art", "picture", "pic", "photo"])
    if is_image_request and (is_dayz_context or any(style in lower for style in SHOWCASE_STYLE_TRIGGERS)):
        # Respect a per-guild image cooldown for on-demand requests (shorter than random)
        last_img = last_showcase_greeting_image.get(guild_id, 0)
        on_demand_cooldown = int(os.getenv("SHOWCASE_ON_DEMAND_IMAGE_COOLDOWN", "300"))
        if now_ts - last_img >= on_demand_cooldown:
            await showcase_handle_image_request(message, lower, guild_id)
            return

    # Smart context-aware responses (only if bot is mentioned OR in ai_chat channel)
    channels = guild_configs.get(guild_id, {}).get("channels", {})
    ai_channel_id = channels.get("ai_chat")
    in_ai_channel = bool(ai_channel_id and message.channel.id == ai_channel_id)
    bot_mentioned = bot.user in message.mentions
    looks_like_question = (
        "?" in message.content
        or any(
            phrase in lower
            for phrase in [
                "how do i",
                "how to",
                "what is",
                "what can",
                "can you",
                "does it",
                "setup",
                "command",
                "feature",
                "invite",
                "help",
            ]
        )
    )

    if bot_mentioned or in_ai_channel or looks_like_question:
        await showcase_handle_smart_response(message, lower, guild_id)


@tasks.loop(minutes=20)
async def showcase_autonomous_loop():
    """
    Proactive autonomous loop for the showcase server.
    Initiates conversations, posts tips, spotlights features,
    and keeps the server active without waiting for user messages.
    """
    now_ts = datetime.now(UTC).timestamp()

    for guild in bot.guilds:
        guild_id = str(guild.id)
        if not is_showcase_guild(guild_id):
            continue

        config = guild_configs.get(guild_id, {})
        channels_cfg = config.get("channels", {})

        # Find the best channel to post in (general_chat, ai_chat, or help_channel)
        target_channel = None
        for key in ("general_chat", "ai_chat", "help_channel"):
            ch_id = channels_cfg.get(key)
            if ch_id:
                target_channel = guild.get_channel(ch_id)
                if target_channel:
                    break

        if not target_channel:
            # Fall back to first available text channel
            for ch in guild.text_channels:
                if not ch.permissions_for(guild.me).send_messages:
                    continue
                target_channel = ch
                break

        if not target_channel:
            continue

        # Proactive discussion starter (every ~60 min)
        last_discussion = last_showcase_discussion_time.get(guild_id, 0)
        discussion_interval = int(config.get(
            "owner_behavior",
            {}
        ).get("showcase_interval_seconds", os.getenv("SHOWCASE_DISCUSSION_INTERVAL", "3600")))
        if now_ts - last_discussion < discussion_interval:
            continue

        roll = random.random()

        if roll < 0.45:
            # Post a discussion starter
            title, body = random.choice(SHOWCASE_DISCUSSION_STARTERS)
            embed = discord.Embed(title=title, description=body, color=0xE67E22)
            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot • Autonomous Host • Drop your answer below 👇")
            embed.timestamp = datetime.now(UTC)
            await target_channel.send(embed=style_embed(embed))
            last_showcase_discussion_time[guild_id] = now_ts

        elif roll < 0.70:
            # Post a survival tip
            tip = random.choice(SHOWCASE_TIPS)
            embed = discord.Embed(title=tip[0], description=tip[1], color=0x1ABC9C)
            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot • Autonomous Host")
            embed.timestamp = datetime.now(UTC)
            await target_channel.send(embed=style_embed(embed))
            last_showcase_discussion_time[guild_id] = now_ts

        elif roll < 0.88:
            # Spotlight a feature
            spotlight = random.choice(SHOWCASE_FEATURE_SPOTLIGHTS)
            embed = discord.Embed(title=spotlight[0], description=spotlight[1], color=0x3498DB)
            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot • Autonomous Host • Ask me anything about this feature")
            embed.timestamp = datetime.now(UTC)
            await target_channel.send(embed=style_embed(embed))
            last_showcase_discussion_time[guild_id] = now_ts

        else:
            # Post a proactive AI image
            last_img = last_showcase_greeting_image.get(guild_id, 0)
            proactive_img_cooldown = int(os.getenv("SHOWCASE_PROACTIVE_IMAGE_COOLDOWN", "7200"))
            if now_ts - last_img >= proactive_img_cooldown:
                style = random.choice(["gritty", "funny", "cinematic", "survival"])
                await target_channel.send(
                    wb_text("spark", f"Quiet in here. Let me fix that with some AI art — generating a `{style}` DayZ scene...")
                )
                success = await showcase_generate_and_post_image(target_channel, style)
                if success:
                    last_showcase_greeting_image[guild_id] = now_ts
                last_showcase_discussion_time[guild_id] = now_ts


@bot.tree.command(name="showcasesetup", description="Owner: initialise the autonomous showcase server")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(secret_code="Owner secret code", invite_url="Bot invite URL to display in start-here")
async def showcasesetup(interaction: discord.Interaction, secret_code: str, invite_url: str = ""):
    """
    Sets up the showcase server with all required channels and posts
    an introduction embed explaining the autonomous bot concept.
    """
    if not owner_secret_valid(interaction, secret_code):
        await reject_owner_command(interaction)
        return

    await interaction.response.defer(ephemeral=True)
    invite_link = bot_invite_url(invite_url)

    guild = interaction.guild
    guild_id = str(guild.id)

    # Mark this guild as the showcase guild in config
    config = guild_configs.setdefault(guild_id, {"guild_name": guild.name, "channels": {}})
    config["showcase_mode"] = True
    save_guild_configs()

    # Create or find the showcase category
    category_name = "🤖🌲┃WANDERING BOT SHOWCASE┃🌲🤖"
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        category = await guild.create_category(category_name)

    # Channel specs: (slug, display_name, description)
    channel_specs = [
        ("showcase-start-here", "🚀 START HERE", (
            "**This server is run by Wandering Bot.**\n\n"
            "The owner is here as backup only. The bot manages channels, generates content, "
            "welcomes members, starts discussions, creates AI art, and adapts to how you communicate.\n\n"
            f"**Invite the bot to your server:** {invite_link}\n\n"
            "Say `hi` in any channel to see the bot respond. Ask it to generate an image. "
            "Ask it about features. Watch it run the server."
        )),
        ("showcase-general", "💬 GENERAL CHAT", (
            "The main chat channel. The bot actively participates here — starting discussions, "
            "dropping tips, reacting to messages, and generating AI art. Say hello."
        )),
        ("showcase-ai-art", "🎨 AI ART GALLERY", (
            "AI-generated DayZ art, posted by the bot automatically and on request. "
            "Ask for a `cinematic`, `horror`, `survival`, `funny`, or `gritty` image."
        )),
        ("showcase-features", "⚙️ FEATURES", (
            "**What Wandering Bot can do:**\n"
            "• Live ADM killfeed, raids, building, and connection feeds\n"
            "• PvP heatmaps and leaderboards\n"
            "• Economy system (pennies, shop, deliveries, vehicle rentals)\n"
            "• Faction system with Discord roles\n"
            "• PVE quest board (hunting, fishing, crafting, expeditions)\n"
            "• Auto translation for international communities\n"
            "• Support ticket system\n"
            "• Gamertag linking via ADM verification\n"
            "• AI chat with DayZ personality\n"
            "• Autonomous showcase mode (what you're seeing right now)"
        )),
        ("showcase-questions", "❓ QUESTIONS", (
            "Ask anything about the bot, setup, features, or DayZ. "
            "The bot monitors this channel and will answer."
        )),
        ("showcase-reviews", "⭐ REVIEWS", (
            "Server owners: leave your feedback here. "
            "What features do you use most? What would you add?"
        )),
    ]

    made_channels = {}
    for slug, _, _ in channel_specs:
        existing = discord.utils.get(guild.text_channels, name=slug)
        if not existing:
            existing = await guild.create_text_channel(slug, category=category)
        elif existing.category != category:
            try:
                await existing.edit(category=category)
            except Exception:
                pass
        made_channels[slug] = existing

    # Register general and ai_chat channels in config
    channels_cfg = config.setdefault("channels", {})
    if "showcase-general" in made_channels:
        channels_cfg["general_chat"] = made_channels["showcase-general"].id
    if "showcase-ai-art" in made_channels:
        channels_cfg["ai_chat"] = made_channels["showcase-ai-art"].id
    if "showcase-questions" in made_channels:
        channels_cfg["help_channel"] = made_channels["showcase-questions"].id

    # Enable AI images for the showcase
    ai_settings = ai_image_config(config)
    ai_settings["enabled"] = True
    ai_settings["style"] = "gritty"
    ai_settings["cooldown_seconds"] = 3600
    if "showcase-ai-art" in made_channels:
        ai_settings["channel_id"] = made_channels["showcase-ai-art"].id

    save_guild_configs()

    # Post content to each channel
    for slug, title, body in channel_specs:
        channel = made_channels.get(slug)
        if not channel:
            continue
        try:
            await channel.purge(limit=5)
        except Exception:
            pass

        color = 0x2ECC71 if "start-here" in slug else 0x3498DB
        embed = discord.Embed(title=f"WANDERING BOT — {title}", description=body, color=color)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot • Autonomous Showcase Server")
        embed.timestamp = datetime.now(UTC)
        await channel.send(embed=style_embed(embed))

    # Post an initial AI image to the art gallery
    art_channel = made_channels.get("showcase-ai-art")
    if art_channel and OPENAI_API_KEY:
        await art_channel.send(wb_text("spark", "Showcase initialised. Here's the first AI postcard:"))
        await showcase_generate_and_post_image(art_channel, "gritty")

    await interaction.followup.send(
        f"Showcase server initialised with {len(made_channels)} channels. "
        f"Set `SHOWCASE_GUILD_ID={guild_id}` in your environment to enable the autonomous loop.",
        ephemeral=True
    )


@bot.tree.command(name="showcasestatus", description="Show autonomous showcase server status")
@app_commands.default_permissions(administrator=True)
async def showcasestatus(interaction: discord.Interaction):
    """Show the current state of the autonomous showcase engine."""
    guild_id = str(interaction.guild.id)
    is_showcase = is_showcase_guild(guild_id)
    config = guild_configs.get(guild_id, {})
    ai_settings = ai_image_config(config)

    now_ts = datetime.now(UTC).timestamp()
    last_discussion = last_showcase_discussion_time.get(guild_id, 0)
    last_img = last_showcase_greeting_image.get(guild_id, 0)
    tracked_users = len(user_style_profiles)

    embed = discord.Embed(
        title="🤖 AUTONOMOUS SHOWCASE STATUS",
        color=0x9B59B6 if is_showcase else 0x95A5A6
    )
    embed.add_field(name="Showcase Mode", value="✅ Active" if is_showcase else "❌ Not the showcase guild", inline=True)
    embed.add_field(name="Loop Running", value="✅ Yes" if showcase_autonomous_loop.is_running() else "❌ No", inline=True)
    embed.add_field(name="AI Images", value="✅ Enabled" if ai_settings.get("enabled") else "❌ Disabled", inline=True)
    embed.add_field(name="OpenAI Key", value="✅ Set" if OPENAI_API_KEY else "❌ Missing", inline=True)
    embed.add_field(name="Style Profiles Tracked", value=str(tracked_users), inline=True)
    embed.add_field(
        name="Last Discussion Post",
        value=f"{int((now_ts - last_discussion) / 60)}m ago" if last_discussion else "Never",
        inline=True
    )
    embed.add_field(
        name="Last Image Post",
        value=f"{int((now_ts - last_img) / 60)}m ago" if last_img else "Never",
        inline=True
    )
    embed.add_field(
        name="SHOWCASE_GUILD_ID",
        value=f"`{SHOWCASE_GUILD_ID}`" if SHOWCASE_GUILD_ID else "❌ Not set",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot • Autonomous Showcase Engine")
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


# =========================================================
# WANDERING BOT EMOJI PERSONALITY
# =========================================================

DEFAULT_WANDERING_EMOJIS = {
    "ai": "🧠",
    "alert": "🚨",
    "beans": "🥫",
    "bot": "🤖",
    "coin": "🪙",
    "dead": "💀",
    "fire": "🔥",
    "map": "🗺️",
    "radio": "📻",
    "spark": "✨",
    "warning": "⚠️"
}

WANDERING_EMOJI_SHOWCASE_LINES = [
    "Look at me. I have my own face now. Absolutely terrifying brand development.",
    "Official Wandering Bot emoji sighting. Please clap, or at least pretend this is normal.",
    "Custom bot emoji flex detected. Tiny picture, massive attitude.",
    "This emoji is mine. I licked it first. Digitally. Probably.",
    "Wandering Bot branding department says this emoji is important as hell."
]

WANDERING_SWEAR_LINES = [
    "Bloody hell, this server has more drama than a badly parked Ada.",
    "I leave you lot alone for five minutes and somehow the apocalypse gets stupider.",
    "That was some Grade-A DayZ nonsense. Beautiful, honestly.",
    "I swear this radio is powered by panic and questionable decisions.",
    "Someone tell Chernarus to calm the hell down."
]

AI_IMAGE_CAPTIONS = [
    "Field sketch from the Wandering Bot imagination department.",
    "I made art. This is either culture or a warning sign.",
    "Little apocalypse postcard for the chat.",
    "Visual morale support, because apparently words were not enough.",
    "Freshly hallucinated survivor nonsense, delivered with questionable confidence."
]

AI_IMAGE_PROMPTS = {
    "funny": [
        "A realistic cinematic photo-style image of an adult DayZ-style survivor trying to cook beans over a tiny campfire while wearing mismatched improvised gear, post-apocalyptic forest village, subtle humor, natural lighting, high-detail survival photography look, non-graphic, no logos, no game UI, no text",
        "A realistic cinematic photo-style image of an adult survivor proudly standing beside a badly repaired off-road car in a Chernarus-inspired wasteland, duct tape, light smoke, awkward confidence, grounded survival realism, natural colors, non-graphic, no logos, no text",
        "A realistic cinematic photo-style image of an adult survivor in rugged apocalypse clothing sprinting through a ruined village while stubbornly holding a can of beans, tense but funny survival moment, documentary realism, non-graphic, no text"
    ],
    "gritty": [
        "A realistic cinematic photo-style image of an adult DayZ-inspired survivor at dusk beside a small woodland camp, worn tactical jacket, moody survival atmosphere, ruined Eastern European village in the distance, natural film grain, non-graphic, no logos, no text",
        "A realistic cinematic photo-style image of an adult survivor overlooking a rainy post-apocalyptic valley from a radio tower, backpack, rifle slung safely, dramatic clouds, grounded survival realism, non-graphic, no text",
        "A tense but non-violent realistic photo-style scene of two adult survivors trading supplies beside a hidden forest stash, post-apocalyptic Eastern European woodland, muted natural colors, no logos, no text"
    ],
    "pinup": [
        "A realistic cinematic photo-style portrait of a glamorous adult female post-apocalyptic survivor, age 25, confident pose, rugged DayZ-inspired tactical outfit with crop jacket and cargo pants, tasteful fashion-editorial style, non-nude, no explicit sexual content, ruined campsite background, no logos, no text",
        "A realistic cinematic photo-style portrait of a stylish adult female wasteland mechanic, age 25, repairing a battered off-road car, fitted survival outfit, playful confident expression, tasteful non-nude editorial poster style, no explicit sexual content, no logos, no text",
        "A realistic cinematic photo-style portrait of a confident adult female survivor, age 25, holding a radio beside a campfire, tactical boots and weathered jacket, tasteful post-apocalyptic editorial style, non-nude, no explicit sexual content, no logos, no text"
    ]
}


def load_wandering_emojis():
    global wandering_emojis

    loaded = {}
    env_value = os.getenv("WANDERING_EMOJIS_JSON", "").strip()

    if env_value:
        try:
            loaded.update(json.loads(env_value))
        except Exception as error:
            print(f"WANDERING EMOJI CONFIG ERROR: {error}")

    file_value = load_json(WANDERING_EMOJIS_FILE)
    if isinstance(file_value, dict):
        loaded.update(file_value)

    wandering_emojis = {
        str(key): str(value)
        for key, value in loaded.items()
        if value
    }


def wb_emoji(key, fallback=None):
    return wandering_emojis.get(
        key,
        fallback if fallback is not None else DEFAULT_WANDERING_EMOJIS.get(key, "")
    )


def wb_text(key, text, fallback=None):
    icon = wb_emoji(key, fallback)
    return f"{icon} {text}" if icon else text


def random_wandering_emoji():
    if wandering_emojis:
        return random.choice(list(wandering_emojis.values()))
    return random.choice(list(DEFAULT_WANDERING_EMOJIS.values()))


def configured_bot_owner_ids():
    raw_ids = ",".join([
        DEFAULT_BOT_OWNER_ID,
        os.getenv("BOT_OWNER_ID", ""),
        os.getenv("BOT_OWNER_IDS", ""),
    ])
    return {
        owner_id.strip()
        for owner_id in str(raw_ids or "").split(",")
        if owner_id.strip()
    }


async def is_global_bot_owner(user):
    if not user:
        return False

    user_id = str(getattr(user, "id", ""))
    if user_id in configured_bot_owner_ids():
        return True

    try:
        return await bot.is_owner(user)
    except Exception:
        return False


def is_global_bot_owner_id(user_id):
    return str(user_id or "") in configured_bot_owner_ids()


def has_member_admin_power(member):
    if not member:
        return False

    if is_global_bot_owner_id(getattr(member, "id", "")):
        return True

    guild = getattr(member, "guild", None)
    if guild is not None and getattr(guild, "owner_id", None) == getattr(member, "id", None):
        return True

    permissions = getattr(member, "guild_permissions", None)
    if bool(getattr(permissions, "administrator", False)):
        return True

    # Check configured bot `admin_roles` for this guild (alternate admin role system).
    if guild is not None:
        config = guild_configs.get(str(guild.id), {}) or {}
        admin_roles = config.get("admin_roles", DEFAULT_ADMIN_ROLES)
        if admin_roles:
            admin_role_set = {str(name).strip().lower() for name in admin_roles if str(name).strip()}
            member_roles = getattr(member, "roles", []) or []
            for role in member_roles:
                if str(getattr(role, "name", "")).strip().lower() in admin_role_set:
                    return True

    return False


def has_interaction_admin_power(interaction):
    return has_member_admin_power(getattr(interaction, "user", None))


def can_modify_admin_roles(member):
    """Strict gate for editing the bot's admin_roles list.

    Only the global bot owner, the Discord guild owner, or a member with the
    native Discord `Administrator` permission may add/remove bot admin roles.
    A member who only has bot admin power via the `admin_roles` config CANNOT
    use this to escalate themselves or others.
    """
    if not member:
        return False

    if is_global_bot_owner_id(getattr(member, "id", "")):
        return True

    guild = getattr(member, "guild", None)
    if guild is not None and getattr(guild, "owner_id", None) == getattr(member, "id", None):
        return True

    permissions = getattr(member, "guild_permissions", None)
    return bool(getattr(permissions, "administrator", False))


def can_modify_admin_roles_interaction(interaction):
    return can_modify_admin_roles(getattr(interaction, "user", None))


def owner_voice_config(guild_id):
    config = guild_configs.setdefault(str(guild_id), {"guild_name": "Unknown", "channels": {}})
    settings = config.setdefault("owner_voice", {})
    settings.setdefault("tone", "default")
    settings.setdefault("directness", "normal")
    settings.setdefault("swearing", "normal")
    return settings


def describe_owner_voice(guild_id):
    settings = owner_voice_config(guild_id)
    return (
        f"tone `{settings.get('tone', 'default')}`, "
        f"detail `{settings.get('directness', 'normal')}`, "
        f"swearing `{settings.get('swearing', 'normal')}`"
    )


def owner_behavior_config(guild_id):
    config = guild_configs.setdefault(str(guild_id), {"guild_name": "Unknown", "channels": {}})
    settings = config.setdefault("owner_behavior", {})
    settings.setdefault("reply_cooldown_seconds", 45)
    settings.setdefault("fun_chatter_cooldown_seconds", 1800)
    settings.setdefault("fun_chatter_chance", 0.04)
    settings.setdefault("showcase_interval_seconds", 3600)
    return settings


def describe_owner_behavior(guild_id):
    settings = owner_behavior_config(guild_id)
    return (
        f"reply cooldown `{int(settings.get('reply_cooldown_seconds', 45))}s`, "
        f"chatter cooldown `{int(settings.get('fun_chatter_cooldown_seconds', 1800))}s`, "
        f"chatter chance `{float(settings.get('fun_chatter_chance', 0.04)):.3f}`"
    )


def message_addresses_bot(message, lower):
    if not message.guild:
        return True

    if bot.user and bot.user in message.mentions:
        return True

    bot_name = normalize_discord_name(getattr(getattr(bot, "user", None), "name", ""))
    compact = normalize_discord_name(lower[:80])
    prefixes = [
        "wandering",
        "wanderingbot",
        "wb",
        "bot",
    ]
    if bot_name:
        prefixes.append(bot_name)

    return any(compact.startswith(prefix) for prefix in prefixes)


def apply_owner_voice_to_text(guild_id, text):
    settings = owner_voice_config(guild_id)
    tone = settings.get("tone", "default")
    directness = settings.get("directness", "normal")
    swearing = settings.get("swearing", "normal")
    result = str(text)

    if swearing == "low":
        replacements = {
            "bollocks": "nonsense",
            "wankers": "muppets",
            "wanker": "muppet",
            "hell": "heck",
            "damn": "darn",
            "shit": "mess",
        }
        for bad, clean in replacements.items():
            result = re.sub(rf"\b{re.escape(bad)}\b", clean, result, flags=re.IGNORECASE)

    if directness == "concise" and len(result) > 220:
        sentences = re.split(r"(?<=[.!?])\s+", result.strip())
        result = " ".join(sentences[:2]).strip() or result[:220].rstrip() + "..."
    elif directness == "detailed" and len(result) < 180:
        result = result.rstrip() + " I can break that down further if needed."

    if tone == "professional":
        result = result.replace("Oi,", "Hello,").replace("lol", "").strip()
    elif tone == "friendly":
        result = result.rstrip(".") + ". Happy to help."
    elif tone == "soft":
        result = result.rstrip(".") + ". No pressure, we can take it step by step."
    elif tone == "funny":
        result = result.rstrip(".") + ". Very official, obviously."
    elif tone == "savage":
        result = result.rstrip(".") + ". Brutal, but fair."

    return result


def set_owner_voice_from_message(guild_id, lower):
    settings = owner_voice_config(guild_id)
    before = dict(settings)

    talks_about_voice = any(word in lower for word in [
        "talk", "speak", "spesk", "voice", "tone", "respond", "reply", "sound"
    ])

    if "reset" in lower and talks_about_voice:
        settings["tone"] = "default"
        settings["directness"] = "normal"
        settings["swearing"] = "normal"

    if any(phrase in lower for phrase in ["professional", "serious", "polite", "less banter"]):
        settings["tone"] = "professional"
    elif any(phrase in lower for phrase in ["friendlier", "friendly", "warmer", "helpful"]):
        settings["tone"] = "friendly"
    elif any(phrase in lower for phrase in ["softer", "kinder", "gentler", "less harsh"]):
        settings["tone"] = "soft"
    elif any(phrase in lower for phrase in ["funny", "banter", "cheeky", "sarcastic"]):
        settings["tone"] = "funny"
    elif any(phrase in lower for phrase in ["savage", "roast", "meaner"]):
        settings["tone"] = "savage"

    if any(phrase in lower for phrase in ["shorter", "more concise", "less chatty", "brief"]):
        settings["directness"] = "concise"
    elif any(phrase in lower for phrase in ["more detail", "detailed", "explain more", "longer"]):
        settings["directness"] = "detailed"

    if any(phrase in lower for phrase in ["no swearing", "less swearing", "stop swearing", "clean language"]):
        settings["swearing"] = "low"
    elif any(phrase in lower for phrase in ["normal swearing", "swear normally", "swearing normal"]):
        settings["swearing"] = "normal"

    changed = before != dict(settings)
    if changed:
        save_guild_configs()
    return changed


def owner_say_payload(content):
    lowered = content.lower()
    markers = ["say:", "post:", "announce:", "tell everyone:"]
    for marker in markers:
        index = lowered.find(marker)
        if index >= 0:
            payload = content[index + len(marker):].strip()
            return payload[:1800] if payload else None
    return None


def parse_owner_interval_minutes(lower, default_minutes=60):
    match = re.search(
        r"(?:every|each|once every|interval|for)\s+(\d+)\s*(minute|minutes|min|mins|m|hour|hours|hr|hrs|h|day|days|d)\b",
        lower
    )
    if not match:
        match = re.search(r"\b(\d+)\s*(minute|minutes|min|mins|m|hour|hours|hr|hrs|h|day|days|d)\b", lower)
    if not match:
        return default_minutes

    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("h"):
        amount *= 60
    elif unit.startswith("d"):
        amount *= 1440
    return max(5, min(10080, amount))


def owner_feed_type_from_text(lower):
    if "heatmap" in lower or "hot zone" in lower:
        return "heatmap"
    if "restart" in lower:
        return "restart"
    if "base damage" in lower or "basedamage" in lower:
        return "basedamage"
    if "server status" in lower or "status feed" in lower or "online" in lower:
        return "serverstatus"
    return "text"


def owner_feed_message_from_text(content):
    for pattern in [
        r"\bmessage\s*:\s*(.+)$",
        r"\bregarding\s+(.+)$",
        r"\babout\s+(.+)$",
    ]:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:1800]
    return ""


async def maybe_create_owner_feed_from_message(message, lower, guild_id):
    if not message.guild:
        return False

    wants_feed = "feed" in lower or "feeds" in lower
    wants_create = any(word in lower for word in ["add", "create", "make", "give", "post", "send", "more"])
    if not wants_feed or not wants_create:
        return False

    config = guild_configs.setdefault(guild_id, {"guild_name": message.guild.name, "channels": {}})
    interval_minutes = parse_owner_interval_minutes(lower, 30 if "more" in lower else 60)
    feed_type = owner_feed_type_from_text(lower)
    feed_message = owner_feed_message_from_text(message.content)
    feed = {
        "id": next_custom_feed_id(config),
        "channel_id": message.channel.id,
        "feed_type": feed_type,
        "interval_minutes": interval_minutes,
        "message": feed_message,
        "enabled": True,
        "created_by": str(message.author.id),
        "created_by_owner_language": True,
        "last_post_ts": 0,
    }
    custom_feeds_for_config(config).append(feed)
    save_guild_configs()

    await message.channel.send(
        wb_text(
            "bot",
            f"Owner recognised: created feed `{feed['id']}` as `{feed_type}` in this channel every `{interval_minutes}` minutes."
        )
    )
    return True


def generic_discord_rules_embed(guild_name):
    embed = discord.Embed(
        title="SERVER RULES",
        description=(
            f"Welcome to **{guild_name}**. Keep the server clean, fair, and easy for everyone to enjoy."
        ),
        color=0x2ECC71
    )
    embed.add_field(
        name="1. Respect Everyone",
        value="No harassment, hate speech, threats, bullying, targeted abuse, or personal attacks.",
        inline=False
    )
    embed.add_field(
        name="2. Keep Chat Safe",
        value="No NSFW content, gore, illegal content, scams, malicious links, or doxxing.",
        inline=False
    )
    embed.add_field(
        name="3. No Spam",
        value="Avoid repeated messages, excessive caps, channel flooding, unwanted pings, or advertising without permission.",
        inline=False
    )
    embed.add_field(
        name="4. Use The Right Channels",
        value="Post in the correct channels and keep support requests, clips, trading, and general chat where they belong.",
        inline=False
    )
    embed.add_field(
        name="5. Follow Staff Direction",
        value="Staff decisions are there to keep the community stable. If you disagree, raise it calmly in the right place.",
        inline=False
    )
    embed.add_field(
        name="6. Play Fair",
        value="No cheating, exploiting, ban evasion, alt abuse, or attempts to bypass server systems.",
        inline=False
    )
    embed.add_field(
        name="7. Use Common Sense",
        value="If something harms the community, creates drama, or makes staff clean up a mess, do not do it.",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Community Rules")
    return style_embed(embed)


async def maybe_post_owner_rules_from_message(message, lower):
    if not message.guild:
        return False

    wants_rules = "rule" in lower or "rules" in lower
    wants_setup = any(word in lower for word in ["set up", "setup", "create", "make", "post", "put", "add"])
    here = any(word in lower for word in ["here", "ere", "this chat", "this channel", "in here"])

    if not wants_rules or not wants_setup:
        return False

    embed = generic_discord_rules_embed(message.guild.name)
    await message.channel.send(embed=embed)

    if here:
        await message.channel.send(
            wb_text("bot", "Owner recognised: generic Discord rules have been posted in this channel.")
        )
    else:
        await message.channel.send(
            wb_text("bot", "Owner recognised: generic Discord rules posted. Tell me `in here` next time if you want me to be extra literal about the channel.")
        )
    return True


def set_owner_behavior_from_message(guild_id, lower):
    settings = owner_behavior_config(guild_id)
    before = dict(settings)
    talks_about_replies = any(word in lower for word in ["reply", "replies", "respond", "answer", "chat"])
    talks_about_chatter = any(word in lower for word in ["chatter", "random", "proactive", "talk", "post"])

    if talks_about_replies and any(phrase in lower for phrase in ["more often", "reply more", "respond more", "answer more"]):
        settings["reply_cooldown_seconds"] = 15
    elif talks_about_replies and any(phrase in lower for phrase in ["less often", "reply less", "respond less", "answer less"]):
        settings["reply_cooldown_seconds"] = 120
    elif talks_about_replies and any(phrase in lower for phrase in ["normal", "default"]):
        settings["reply_cooldown_seconds"] = 45

    if talks_about_chatter and any(phrase in lower for phrase in ["more often", "post more", "talk more"]):
        settings["fun_chatter_cooldown_seconds"] = 600
        settings["fun_chatter_chance"] = 0.08
    elif talks_about_chatter and any(phrase in lower for phrase in ["less often", "post less", "talk less"]):
        settings["fun_chatter_cooldown_seconds"] = 3600
        settings["fun_chatter_chance"] = 0.01

    if "showcase" in lower and any(phrase in lower for phrase in ["more often", "post more"]):
        settings["showcase_interval_seconds"] = 1800
    elif "showcase" in lower and any(phrase in lower for phrase in ["less often", "post less"]):
        settings["showcase_interval_seconds"] = 7200

    changed = before != dict(settings)
    if changed:
        save_guild_configs()
    return changed


async def maybe_handle_owner_natural_language(message, lower, now_ts):
    if not await is_global_bot_owner(message.author):
        return False

    if not message_addresses_bot(message, lower):
        return False

    guild_id = str(message.guild.id) if message.guild else "global"
    cooldown_key = f"{guild_id}:{message.author.id}"
    if now_ts - owner_natural_language_cooldowns.get(cooldown_key, 0) < 2:
        return True

    owner_natural_language_cooldowns[cooldown_key] = now_ts

    if any(phrase in lower for phrase in ["owner status", "voice status", "behavior status", "behaviour status", "how are you set"]):
        await message.channel.send(
            wb_text("bot", f"Owner recognised: Cranemonkey6273. Voice: {describe_owner_voice(guild_id)}. Behaviour: {describe_owner_behavior(guild_id)}.")
        )
        return True

    payload = owner_say_payload(message.content)
    if payload:
        await message.channel.send(apply_owner_voice_to_text(guild_id, payload))
        return True

    if message.guild and any(phrase in lower for phrase in [
        "fix emoji",
        "fix emojis",
        "repair emoji",
        "repair emojis",
        "fix channel names",
        "repair channel names",
        "fix mojibake",
        "repair mojibake",
    ]):
        config = guild_configs.setdefault(guild_id, {"guild_name": message.guild.name, "channels": {}})
        repaired = await repair_guild_display_names(message.guild, config)
        config["last_display_name_repair_ts"] = datetime.now(UTC).timestamp()
        save_guild_configs()
        await message.channel.send(
            wb_text("bot", f"Owner recognised: repaired `{repaired}` Discord category/channel name(s) for this server.")
        )
        return True

    if await maybe_post_owner_rules_from_message(message, lower):
        return True

    if await maybe_create_owner_feed_from_message(message, lower, guild_id):
        return True

    if set_owner_behavior_from_message(guild_id, lower):
        await message.channel.send(
            wb_text("bot", f"Owner recognised: Cranemonkey6273. Behaviour updated for this server: {describe_owner_behavior(guild_id)}.")
        )
        return True

    if set_owner_voice_from_message(guild_id, lower):
        await message.channel.send(
            wb_text("bot", f"Owner recognised: Cranemonkey6273. Voice updated for this server: {describe_owner_voice(guild_id)}.")
        )
        return True

    return False


async def maybe_send_wandering_personality(message, now_ts):
    if not message.guild:
        return

    guild_id = str(message.guild.id)

    # Showcase guilds use their own proactive messaging — skip DayZ personality here
    if guild_configs.get(guild_id, {}).get("is_showcase_guild"):
        return

    last_seen = last_emoji_showcase_time.get(guild_id, 0)

    behavior = owner_behavior_config(guild_id)
    chatter_cooldown = int(behavior.get("fun_chatter_cooldown_seconds", 1800))
    if now_ts - last_seen < max(300, chatter_cooldown):
        return

    roll = random.random()
    chatter_chance = max(0.001, min(0.2, float(behavior.get("fun_chatter_chance", 0.04))))

    if roll < chatter_chance * 0.67:
        last_emoji_showcase_time[guild_id] = now_ts
        await message.channel.send(
            f"{random_wandering_emoji()} {random.choice(WANDERING_EMOJI_SHOWCASE_LINES)}"
        )

    elif roll < chatter_chance:
        last_emoji_showcase_time[guild_id] = now_ts
        await message.channel.send(
            wb_text("radio", apply_owner_voice_to_text(guild_id, random.choice(WANDERING_SWEAR_LINES)))
        )


# =========================================================
# SHOWCASE GUILD BEHAVIOUR
# =========================================================

SHOWCASE_COMMAND_HINTS = [
    "💡 Have you tried `/linkgamer`? Link your Discord to your in-game name and unlock leaderboards, economy rewards, and quest tracking.",
    "💡 Did you know `/topkills` shows a live leaderboard of PvP kills across the server? Give it a go.",
    "💡 The `/wallet` command shows your penny balance. Earn pennies by chatting, completing quests, and avoiding the swear jar.",
    "💡 Try `/pveinfo` to see active PVE quests — hunting, fishing, crafting, and expedition challenges with real rewards.",
    "💡 `/shop` opens the server shop. Spend your pennies on items, perks, and more.",
    "💡 Ask me anything by mentioning me directly — I can help with bot commands, setup questions, and DayZ advice.",
    "💡 `/admstatus` shows whether the live feed reader is running and when it last processed your server logs.",
    "💡 The `/heatmap` command renders a visual map of PvP hotspots, raid locations, and more on your actual server map.",
    "💡 `/radarstatus` shows all active radar zones. When a player enters a zone, the bot fires an alert automatically.",
    "💡 Want AI-generated DayZ art in your server? Ask an admin to enable it with `/aiimageconfig`.",
    "💡 `/toplongshots` is the sniper hall of fame — every kill over 300m gets automatically logged.",
    "💡 `/mylink` shows your linked gamertag and personal stats. Run it any time to check your progress.",
    "💡 The `/events airdrop` command lets admins spawn an airdrop loot crate anywhere on the map.",
    "💡 `/createfaction` starts your own faction. Recruit members, claim territory, and fight rival factions.",
    "💡 `/translationconfig` enables auto-translation for international survivors. Everyone chats in their own language and still understands each other.",
    "💡 Power tip: `/setup` walks you through the whole bot configuration in under 5 minutes.",
    "💡 `/welcomeconfig` lets admins customise the new-member welcome message — make a great first impression.",
    "💡 `/vehiclerentals` adds a paid vehicle rental economy to your DayZ server. Players pay pennies, get keys, return for refunds.",
    "💡 `/aiimageconfig` enables periodic AI-generated DayZ art. Cinematic, gritty, funny — your choice of style.",
    "💡 `/serverinfo` posts a public server-info embed any visitor can read for IP, mods, and player count.",
]

SHOWCASE_FEATURE_PROMOS = [
    "🤖 Wandering Bot reads your DayZ server's ADM logs in real time — killfeed, raids, base building, connections, and more, all posted to Discord automatically.",
    "🗺️ Heatmaps, iZurvive map links, and coordinate tracking are all built in. Every kill and raid event includes a clickable map link.",
    "🏴 The faction system lets your community create, manage, and battle factions entirely inside Discord — no external tools needed.",
    "💰 The economy system rewards active players with pennies they can spend in the server shop. Fully configurable by admins.",
    "🧭 PVE quests rotate automatically on a schedule. Hunting, fishing, crafting, collection, and expedition chains — all tracked via ADM logs.",
    "📡 Radar zones alert your team the moment a player enters a high-value area like NWAF, Tisy, or any custom coordinate zone you define.",
    "🌍 Automatic translation means international players can chat in their own language and everyone still understands each other.",
    "🎨 AI-generated DayZ art drops into your server periodically — cinematic, funny, or survival horror styles, all created on demand.",
    "🚨 Real-time raid alerts: the moment someone destroys a wall, Wandering Bot fires a Discord notification — no more silent raids.",
    "🏆 Leaderboards update live: kills, longshots, deaths, K/D ratios, session time — every stat tracked automatically from ADM.",
    "🎯 Longshot detector flags every kill over 300m automatically and adds it to the sniper hall of fame.",
    "👋 Custom welcome messages greet new survivors when they join Discord — make a great first impression instantly.",
    "📊 Full player stat tracking pulled live from ADM logs. No manual data entry, no spreadsheets, no fuss.",
    "🪙 The swear jar economy: every time someone swears in chat, pennies move from their wallet to the community pot. Light moderation with a sense of humour.",
    "⏰ Automated scheduled restart announcements + countdown warnings (30/15/5/1 minute) keep players from losing loot when the server reboots.",
    "💥 Airdrop events: admins can spawn a loot crate anywhere on the map with a single command — XML pushed to Nitrado automatically.",
]

SHOWCASE_QUESTION_RESPONSES = {
    # ── Setup & onboarding ─────────────────────────────────
    "how do i": [
        "Great question! Check out **#🎮✨・COMMANDS・✨🎮** for a full breakdown of every command with examples.",
        "Head to **#🌟🎉・GET STARTED NOW・🎉🌟** for a step-by-step walkthrough, or ask me directly and I'll do my best to help.",
    ],
    "what can": [
        "Wandering Bot does a lot — live feeds, economy, factions, PVE quests, heatmaps, radar zones, AI chat, and more. Check **#🎯🚀・FEATURES GALORE・🚀🎯** for the full list.",
        "The short answer: everything your DayZ server needs in one bot. The long answer is in **#🎯🚀・FEATURES GALORE・🚀🎯**.",
    ],
    "invite": [
        "🔗 The bot invite link is in **#🔗💥・INVITE ME!・💥🔗**. Add it to your server and run `/setup` to get started.",
        "Want me on your server? Grab the link from **#🔗💥・INVITE ME!・💥🔗** — setup takes under 5 minutes!",
    ],
    "setup": [
        "⚙️ Setup takes about 5 minutes. Invite the bot, run `/setup` with your Nitrado token and service ID, and you're live. Full guide in **#🌟🎉・GET STARTED NOW・🎉🌟**.",
        "🚀 To get started: 1) invite me, 2) run `/setup`, 3) run `/restartadm force` once. The bot does the rest automatically!",
    ],
    "install": [
        "Installation is just inviting me to your server and running `/setup`. No file uploads, no config files, no headaches.",
    ],
    "configure": [
        "Most config happens via slash commands: `/setup`, `/welcomeconfig`, `/translationconfig`, `/aiimageconfig`, `/economyconfig`. Each one is interactive.",
    ],
    "begin": [
        "Brand new? Head to **#🌟🎉・GET STARTED NOW・🎉🌟** for the 5-minute getting-started guide.",
    ],
    # ── Commands ──────────────────────────────────────────
    "command": [
        "🎮 Every command is documented in **#🎮✨・COMMANDS・✨🎮** with plain-English explanations. The most important ones are `/setup`, `/linkgamer`, and `/pveinfo`.",
        "Key commands: `/setup` (admin), `/linkgamer` (everyone), `/wallet`, `/topkills`, `/heatmap`, `/pveinfo`. Full list in **#🎮✨・COMMANDS・✨🎮**.",
    ],
    "slash": [
        "🎮 I respond to 30+ slash commands! Check **#🎮✨・COMMANDS・✨🎮** for the complete guide.",
    ],
    # ── Reviews / feedback ────────────────────────────────
    "review": [
        "⭐ We'd love to hear your thoughts! Drop a message in **#⭐💫・REVIEWS & LOVE・💫⭐** — all feedback goes directly to the developer.",
        "Love the bot? Hate the bot? Either way, drop a line in **#⭐💫・REVIEWS & LOVE・💫⭐** and help other server owners find us.",
    ],
    "love": [
        "Drop the love in **#⭐💫・REVIEWS & LOVE・💫⭐** 💜",
    ],
    "feedback": [
        "Real talk welcome — leave feedback in **#⭐💫・REVIEWS & LOVE・💫⭐**.",
    ],
    # ── Questions ─────────────────────────────────────────
    "question": [
        "❓ Post it in **#❓🔥・ASK ANYTHING・🔥❓** and either the bot or a community member will respond. No question is too basic.",
    ],
    "help": [
        "Need help? Drop your question in **#❓🔥・ASK ANYTHING・🔥❓** or mention me directly anywhere and I'll do my best!",
    ],
    # ── AI / smart features ───────────────────────────────
    "ai": [
        "🧠 The AI layer is always on — mention me in any channel and I'll respond with context-aware advice. Admins can also enable AI-generated DayZ art with `/aiimageconfig`.",
        "🤖 I'm powered by AI for: smart kill alerts, radar anomaly detection, AI-generated DayZ artwork, intelligent chat responses, and pattern recognition from ADM logs.",
        "💡 The **#🤖🧠・AI MAGIC・🧠🤖** channel shows off everything I can do with artificial intelligence!",
    ],
    "smart": [
        "🧠 Smart features include: pattern recognition from ADM logs, AI image generation, anomaly detection, and context-aware mention replies.",
    ],
    "gpt": [
        "🤖 I use modern LLMs for smart responses. Mention me anywhere and I'll do my best to answer.",
    ],
    # ── Killfeed / kills / PvP ────────────────────────────
    "killfeed": [
        "⚔️ The killfeed reads your DayZ server's ADM logs in real time and posts every PvP kill to Discord with player names, weapons, distances, and a map link. Set it up with `/setup`.",
    ],
    "kill": [
        "⚔️ Every kill gets tracked automatically — weapon, distance, location, with a map link. Use `/linkgamer` to make sure YOUR kills count on the leaderboard.",
        "🎯 Killfeed updates live from your ADM logs. Check `/topkills` for the leaderboard!",
    ],
    "snipe": [
        "🎯 Longshot detector active! Every kill over 300m gets flagged automatically. Hall of fame: `/toplongshots`.",
    ],
    "longshot": [
        "🏹 Run `/toplongshots` to see the sniper hall of fame — every kill 300m+ logged automatically from ADM.",
    ],
    # ── Economy ───────────────────────────────────────────
    "economy": [
        "💰 The economy system gives players pennies for chatting, completing quests, and good behaviour. They spend them in `/shop`. Admins configure rewards with `/addreward`.",
        "🪙 Full Discord-side economy: earn pennies by playing, spend them in `/shop`, get fined by the swear jar, earn bonuses from PVE quests.",
    ],
    "money": [
        "💸 Check your balance with `/wallet`. Spend it in `/shop`. Earn more by playing on the server (link your gamertag first with `/linkgamer`).",
    ],
    "wallet": [
        "💰 `/wallet` shows your penny balance. Earn pennies by playing on a linked server, completing PVE quests, and chatting (just watch the swear jar!).",
    ],
    "shop": [
        "🛒 `/shop` opens the server shop. Admins decide what's stocked — items, perks, custom rewards.",
    ],
    "pennies": [
        "🪙 Pennies are the in-Discord currency. Earned from gameplay, lost to the swear jar, spent in the shop.",
    ],
    "swear": [
        "💸 The swear jar is real! Every swear word costs pennies. Light moderation with a sense of humour. Check your balance with `/wallet`.",
    ],
    # ── Factions ──────────────────────────────────────────
    "faction": [
        "🏴 The faction system lets players create and manage factions entirely in Discord. Leaders can add members, set flags, and track activity. Start with `/createfaction`.",
        "⚔️ Faction wars are LIVE — create your faction, recruit members, claim territory, fight rivals. All tracked from ADM logs.",
    ],
    "clan": [
        "🏴 Same idea, different word — try `/createfaction` to make your own.",
    ],
    "team": [
        "🛡️ Factions let teams form persistent groups with leaders, members, territory and kill attribution. `/createfaction` to start one.",
    ],
    # ── Heatmap / map ─────────────────────────────────────
    "heatmap": [
        "🗺️ Heatmaps render a visual overlay of PvP kills, raids, building activity, and more on your actual server map. Run `/heatmap` to generate one.",
        "🔥 `/heatmap pvp`, `/heatmap raids`, `/heatmap builds`, or `/heatmap all` — each generates a colour-coded map image automatically.",
    ],
    "map": [
        "📍 Every kill embed includes an iZurvive map link with the exact coordinates. Try `/heatmap` for a visual conflict overlay.",
    ],
    "location": [
        "📡 Locations come straight from ADM logs. Every kill, raid and placement embed includes coordinates + an iZurvive link.",
    ],
    # ── Radar ─────────────────────────────────────────────
    "radar": [
        "📡 Radar zones alert your team when a player enters a defined coordinate area. Set one up with `/addradarzone` and choose a channel with `/setradarchannel`.",
    ],
    # ── PVE / quests ──────────────────────────────────────
    "pve": [
        "🧭 The PVE quest system posts rotating challenges — hunting, fishing, crafting, collection, and expeditions — and tracks completions via ADM logs. See `/pveinfo` for active quests.",
    ],
    "quest": [
        "🧭 PVE quests are live! Use `/pveinfo` to see active missions and `/linkgamer` to make sure rewards reach you.",
    ],
    "mission": [
        "🎯 Missions = PVE quests. `/pveinfo` shows what's active right now.",
    ],
    "reward": [
        "🎁 Rewards from PVE quests are paid in pennies straight to your `/wallet` once an admin verifies completion.",
    ],
    "fish": [
        "🎣 Fishing quests are part of the PVE system — `/pveinfo` to see if one's active.",
    ],
    "hunt": [
        "🦌 Hunting quests rotate in the PVE chain. Check `/pveinfo` for active ones.",
    ],
    # ── Leaderboards / stats ──────────────────────────────
    "leaderboard": [
        "🏆 `/topkills` for the kill leaderboard, `/toplongshots` for snipers. Updates in real-time from ADM logs.",
    ],
    "ranking": [
        "📊 Live rankings via `/topkills` and `/toplongshots`. Link your gamertag first with `/linkgamer` so your kills count.",
    ],
    "stats": [
        "📈 Full player stats: kills, deaths, K/D, longshots, session time, zombie kills. All from ADM. Try `/mylink` for yours.",
    ],
    "top": [
        "👑 Try `/topkills` or `/toplongshots` to see who's on top.",
    ],
    # ── Translation ───────────────────────────────────────
    "translate": [
        "🌍 Automatic translation is built in. Configure it with `/translationconfig` — choose `same` to post translations beside the original, or `channel` to forward them elsewhere.",
    ],
    "language": [
        "🌐 Multi-language support is on by default. Admins fine-tune it via `/translationconfig`.",
    ],
    # ── Online / players ──────────────────────────────────
    "online": [
        "✅ The online dashboard updates live as players connect/disconnect. Self-cleaning so chat never gets spammed.",
    ],
    "players": [
        "🎮 Player tracking is automatic. `/topkills`, `/toplongshots`, `/mylink` — all live from ADM.",
    ],
    # ── Welcome / first impressions ───────────────────────
    "welcome": [
        "👋 Custom welcome messages greet new survivors. `/welcomeconfig` to customise the text, embed, and channel.",
    ],
    "new": [
        "🌟 New here? Start at **#🌟🎉・GET STARTED NOW・🎉🌟** for the quick tour.",
    ],
    # ── Restart / uptime ──────────────────────────────────
    "restart": [
        "⏰ Automated restart announcements with 30/15/5/1-minute pre-restart countdown warnings. Self-cleaning so chat never gets spammed with restart messages.",
    ],
    "uptime": [
        "🌙 I run 24/7 with zero scheduled downtime. The bot never sleeps even when you do.",
    ],
    # ── Vehicles ──────────────────────────────────────────
    "vehicle": [
        "🚗 Vehicle rental economy available via `/vehiclerentals`. Players pay pennies, get keys, return for refunds.",
    ],
    "car": [
        "🛻 Same answer as vehicle — try `/vehiclerentals` for a rental economy on your server.",
    ],
    # ── DayZ flavour helpers ──────────────────────────────
    "loot": [
        "🎁 Loot tip: hit hunting camps, military tents, police stations, medical buildings. Use `/heatmap loot` to see where everyone else is looting.",
    ],
    "weapon": [
        "🔫 Guns spawn at police (basics), hunting (rifles), military (proper trouble). `/heatmap` shows where the fights are happening.",
    ],
    "base": [
        "🏗️ Base tip: small, ugly, hidden and boring survives longer than a giant castle screaming 'please raid me'. Wandering Bot logs ALL building activity.",
    ],
    "raid": [
        "💥 Raid alerts fire the moment a wall is destroyed. No more silent raids — your raids feed catches everything in real time.",
    ],
    "bear": [
        "🐻 If you hear the bear first, it's too late. `/heatmap` tracks animal kill events too.",
    ],
    "cheater": [
        "🚨 Record clips and timestamps before reporting. Wandering Bot's radar system flags suspicious movement automatically.",
    ],
    "lag": [
        "📡 If desync hits, slow down. Use `/admstatus` to check whether the bot is still receiving log updates.",
    ],
    "dead": [
        "💀 DayZ teaches lessons the painful way. Check `/toplongshots` to see who's been doing the teaching.",
    ],
}

# Per-guild cooldown for showcase proactive messages (seconds)
last_showcase_response_time = {}


async def maybe_showcase_guild_response(message, lower):
    """
    In showcase/advertising guilds, be proactive: suggest commands, promote
    features, and answer questions about the bot. Replaces the normal DayZ
    survival-focused personality with an enthusiastic, helpful showcase mode.
    """
    if not message.guild:
        return

    guild_id = str(message.guild.id)
    config = guild_configs.get(guild_id, {})

    if not config.get("is_showcase_guild"):
        return

    now_ts = datetime.now(UTC).timestamp()
    key = f"{guild_id}:{message.author.id}"

    # Per-user cooldown: don't spam the same person
    if now_ts - last_showcase_response_time.get(key, 0) < 60:
        return

    # Check for specific question keywords first (highest priority)
    for trigger, responses in SHOWCASE_QUESTION_RESPONSES.items():
        if trigger in lower:
            last_showcase_response_time[key] = now_ts
            await message.channel.send(random.choice(responses))
            return

    # Proactively drop a command hint or feature promo at low frequency
    roll = random.random()

    if roll < 0.25:
        # Command hint
        last_showcase_response_time[key] = now_ts
        await message.channel.send(random.choice(SHOWCASE_COMMAND_HINTS))
    elif roll < 0.40:
        # Feature promo
        last_showcase_response_time[key] = now_ts
        await message.channel.send(random.choice(SHOWCASE_FEATURE_PROMOS))


def ai_image_config(config):
    settings = config.setdefault("ai_images", {})
    settings.setdefault("enabled", False)
    settings.setdefault("style", "funny")
    settings.setdefault("channel_id", None)
    settings.setdefault("cooldown_seconds", AI_IMAGE_DEFAULT_COOLDOWN_SECONDS)
    settings.setdefault("chance", 0.006)
    return settings


def generate_ai_image_bytes(style):
    if not OPENAI_API_KEY:
        return None, "OPENAI_API_KEY is not set"

    style = str(style or "funny").lower()
    prompts = AI_IMAGE_PROMPTS.get(style, AI_IMAGE_PROMPTS["funny"])
    prompt = random.choice(prompts)

    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": AI_IMAGE_MODEL,
            "prompt": prompt,
            "size": "1024x1024",
            "n": 1
        },
        timeout=120
    )

    if response.status_code != 200:
        return None, f"Image API returned {response.status_code}: {response.text[:300]}"

    data = response.json()
    image_data = (data.get("data") or [{}])[0]
    b64_json = image_data.get("b64_json")
    image_url = image_data.get("url")

    if b64_json:
        return base64.b64decode(b64_json), None

    if image_url:
        image_response = requests.get(image_url, timeout=60)
        if image_response.status_code == 200:
            return image_response.content, None
        return None, f"Image download returned {image_response.status_code}"

    return None, "Image API did not return image data"


async def maybe_send_ai_generated_picture(message, now_ts):
    if not message.guild:
        return

    guild_id = str(message.guild.id)
    config = guild_configs.get(guild_id, {})
    settings = ai_image_config(config)

    if not settings.get("enabled"):
        return

    cooldown_seconds = max(3600, int(settings.get("cooldown_seconds") or AI_IMAGE_DEFAULT_COOLDOWN_SECONDS))
    if now_ts - last_ai_image_time.get(guild_id, 0) < cooldown_seconds:
        return

    chance = float(settings.get("chance") or 0.006)
    if random.random() > max(0.001, min(0.05, chance)):
        return

    channel = None
    channel_id = settings.get("channel_id")
    if channel_id:
        channel = message.guild.get_channel(int(channel_id))

    if not channel:
        channels = config.get("channels", {})
        for channel_key in ("ai_chat", "general_chat", "clips_channel"):
            configured_id = channels.get(channel_key)
            if configured_id:
                channel = message.guild.get_channel(int(configured_id))
                if channel:
                    break

    channel = channel or message.channel
    last_ai_image_time[guild_id] = now_ts

    image_bytes, error = await asyncio.to_thread(
        generate_ai_image_bytes,
        settings.get("style", "funny")
    )

    if error:
        print(f"AI IMAGE ERROR {guild_id}: {error}")
        return

    file = discord.File(io.BytesIO(image_bytes), filename="wandering_postcard.png")
    embed = discord.Embed(
        title="WANDERING BOT POSTCARD",
        description=random.choice(AI_IMAGE_CAPTIONS),
        color=0x9B59B6
    )
    embed.set_image(url="attachment://wandering_postcard.png")
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - AI Generated DayZ-Inspired Art")
    embed.timestamp = datetime.now(UTC)
    await channel.send(embed=style_embed(embed), file=file)

def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)


def save_json(path, data):
    folder = os.path.dirname(path)

    if folder:
        ensure_folder(folder)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def normalize_discord_name(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def new_guild_config(guild):
    return {
        "guild_name": guild.name,
        "guild_owner": str(guild.owner),
        "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
        "nitrado_token": "",
        "service_id": "",
        "nitrado_user": "",
        "ftp_user": "",
        "ftp_password": "",
        "ftp_host": "",
        "roasts_enabled": False,
        "channels": {}
    }


PRIVATE_FEED_CHANNEL_KEYS = {
    "admin_logs",
    "cheat_checks",
    "command_logs",
    "cuts_feed",
    "faction_staff",
    "flag_feed",
    "placed_feed",
    "suicide_feed",
}


CHANNEL_RESTORE_PACKS = {
    "live": [
        "killfeed",
        "raids",
        "building",
        "connections",
        "disconnects",
        "zombie_feed",
        "unconscious_feed",
        "cuts_feed",
        "suicide_feed",
        "flag_feed",
        "placed_feed",
        "pvp_intel",
    ],
    "info": [
        "online",
        "leaderboards",
        "heatmap",
        "longshots",
        "restart_alerts",
        "bot_updates",
        "welcome",
    ],
    "community": [
        "public_shame",
        "linked_players",
        "general_chat",
        "ai_chat",
        "clips_channel",
        "help_channel",
    ],
    "staff": [
        "admin_logs",
        "cheat_checks",
        "command_logs",
        "faction_staff",
        "company_announcements",
    ],
    "economy": [
        "economy",
        "purchase_logs",
        "vehicle_rentals",
        "rental_logs",
    ],
    "factions": [
        "factions_chat",
        "faction_list",
        "faction_tickets",
        "faction_staff",
    ],
    "pve": [
        "pve_quests",
        "pve_hunting",
        "pve_collection",
        "pve_fishing",
        "pve_crafting",
        "pve_expeditions",
        "pve_info",
        "pve_help",
        "pve_heatmap",
    ],
}
CHANNEL_RESTORE_PACKS["all"] = list(DEFAULT_CHANNEL_NAMES.keys())

CATEGORY_REPAIR_SPECS = [
    ("wandering_hq", "🟩🟩🟩┃WANDERING HQ┃🟩🟩🟩", ["wanderinghq", "wanderingbot", "wanderingbotalpha"]),
    ("live_feeds", "🟥🟧🟨┃LIVE SERVER FEEDS┃🟨🟧🟥", ["liveserverfeeds", "livefeeds", "killfeed", "serverfeeds"]),
    ("server_info", "🟦🟩🟦┃SERVER INFO┃🟦🟩🟦", ["serverinfo", "info", "leaderboards", "dashboard"]),
    ("survivor_comms", "🟪🟩🟪┃SURVIVOR COMMS┃🟪🟩🟪", ["survivorcomms", "survivorchat", "generalchat", "community"]),
    ("staff_ops", "🛡️🟥🛡️┃STAFF OPS┃🛡️🟥🛡️", ["staffops", "staff", "admin", "adminlogs"]),
    ("economy", "💰🟨💰┃ECONOMY┃💰🟨💰", ["economy", "blackmarket", "shop"]),
    ("factions", "🏴🟩🏴┃FACTIONS┃🏴🟩🏴", ["factions", "faction"]),
    ("support", "❓🟦❓┃HELP & SUPPORT┃❓🟦❓", ["helpsupport", "helpdesk", "support"]),
    ("pve", "🦌🌲🧭┃PVE EXPEDITIONS┃🧭🌲🦌", ["pve", "pvemissions", "pveexpeditions", "quests", "hunting", "collection", "fishing"]),
    ("bot_updates", "📢✨┃BOT NEWS & UPDATES┃✨📢", ["botnews", "botupdates", "updates"]),
    ("cheat_checks", "🕵️🚫┃PRIVATE CHEAT CHECK┃🚫🕵️", ["privatecheatcheck", "cheatchecks", "pccheatcheck"]),
    ("public_shame", "🚫📣┃WANDERING JUSTICE┃📣🚫", ["wanderingjustice", "wanderinginshame", "publicshame"]),
]


def channel_matches_saved_key(channel, key):
    normalized = normalize_discord_name(channel.name)
    aliases = set(CHANNEL_ALIASES.get(key, []))
    desired = DEFAULT_CHANNEL_NAMES.get(key)

    if desired:
        aliases.add(normalize_discord_name(desired))

    if key == "connections" and "disconnect" in normalized:
        return False

    return normalized in aliases or any(alias and alias in normalized for alias in aliases)


MOJIBAKE_MARKERS = ("đ", "Đ", "â", "ă", "Ă", "ď", "Ď", "\x83", "\x90", "\x9f")


def reverse_cp1250_mojibake(text):
    text = str(text or "")
    if not text or not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text

    reverse = {}
    for byte_value in range(256):
        try:
            reverse[bytes([byte_value]).decode("cp1250")] = byte_value
        except UnicodeDecodeError:
            pass

    for byte_value in range(0x80, 0xA0):
        reverse[chr(byte_value)] = byte_value

    raw = bytearray()
    for char in text:
        if ord(char) < 128:
            raw.append(ord(char))
        elif char in reverse:
            raw.append(reverse[char])
        else:
            return text

    try:
        return bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        return text


def default_channel_key_for_name(name):
    normalized = normalize_discord_name(name)
    if not normalized:
        return None

    best_key = None
    best_score = 0

    for key, desired_name in DEFAULT_CHANNEL_NAMES.items():
        aliases = set(CHANNEL_ALIASES.get(key, []))
        aliases.add(normalize_discord_name(desired_name))
        aliases.add(normalize_discord_name(key))

        for alias in aliases:
            if not alias:
                continue
            if normalized == alias:
                return key
            if alias in normalized and len(alias) > best_score:
                best_key = key
                best_score = len(alias)

    return best_key


def disabled_channel_keys(config):
    disabled = config.setdefault("disabled_channels", [])
    if not isinstance(disabled, list):
        disabled = []
        config["disabled_channels"] = disabled
    return disabled


def is_channel_key_disabled(config, key):
    return key in set(disabled_channel_keys(config))


def set_channel_key_disabled(config, key, disabled=True):
    disabled_keys = disabled_channel_keys(config)
    if disabled and key not in disabled_keys:
        disabled_keys.append(key)
    elif not disabled and key in disabled_keys:
        disabled_keys.remove(key)


def mark_deleted_bot_channel(guild_id, channel_id):
    config = guild_configs.get(str(guild_id))
    if not config:
        return None

    channels = config.setdefault("channels", {})
    for key, saved_id in list(channels.items()):
        if int(saved_id or 0) != int(channel_id):
            continue
        channels.pop(key, None)
        set_channel_key_disabled(config, key, True)
        save_guild_configs()
        return key

    return None


def discover_existing_guild_channels(guild, config):
    channels = config.setdefault("channels", {})
    changed = False

    for key in DEFAULT_CHANNEL_NAMES:
        existing_id = channels.get(key)

        if existing_id and guild.get_channel(existing_id):
            continue

        for channel in guild.text_channels:
            if channel_matches_saved_key(channel, key):
                channels[key] = channel.id
                changed = True
                break

    return changed


async def repair_guild_display_names(guild, config):
    channels = config.setdefault("channels", {})
    repaired = 0
    edited_channel_ids = set()

    for _, category_name, aliases in CATEGORY_REPAIR_SPECS:
        wanted = normalize_discord_name(category_name)
        alias_set = {wanted, *aliases}

        for category in guild.categories:
            normalized = normalize_discord_name(category.name)
            if normalized in alias_set or any(alias and alias in normalized for alias in alias_set):
                if category.name != category_name:
                    try:
                        await category.edit(name=category_name)
                        repaired += 1
                    except Exception:
                        pass
                break

    for category in guild.categories:
        decoded_name = reverse_cp1250_mojibake(category.name)
        if decoded_name != category.name:
            desired_name = decoded_name
            decoded_normalized = normalize_discord_name(decoded_name)
            for _, category_name, aliases in CATEGORY_REPAIR_SPECS:
                wanted = normalize_discord_name(category_name)
                alias_set = {wanted, *aliases}
                if decoded_normalized in alias_set or any(alias and alias in decoded_normalized for alias in alias_set):
                    desired_name = category_name
                    break

            try:
                await category.edit(name=desired_name)
                repaired += 1
            except Exception:
                pass

    for candidate in guild.text_channels:
        decoded_name = reverse_cp1250_mojibake(candidate.name)
        if decoded_name == candidate.name:
            continue

        key = default_channel_key_for_name(decoded_name)
        desired_name = DEFAULT_CHANNEL_NAMES.get(key, decoded_name)
        if candidate.name == desired_name:
            continue

        try:
            await candidate.edit(name=desired_name)
            edited_channel_ids.add(candidate.id)
            if key:
                channels[key] = candidate.id
            repaired += 1
        except Exception:
            pass

    for key, desired_name in DEFAULT_CHANNEL_NAMES.items():
        channel = None
        existing_id = channels.get(key)

        if existing_id:
            channel = guild.get_channel(int(existing_id))

        if not channel:
            for candidate in guild.text_channels:
                if channel_matches_saved_key(candidate, key):
                    channel = candidate
                    channels[key] = candidate.id
                    break

        if channel and channel.id not in edited_channel_ids and channel.name != desired_name:
            try:
                await channel.edit(name=desired_name)
                repaired += 1
            except Exception:
                pass

    save_guild_configs()
    return repaired


def env_truthy(name, default=""):
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def startup_display_name_repair_enabled():
    return env_truthy("WANDERING_REPAIR_NAMES_ON_STARTUP", "false")


def startup_display_name_repair_cooldown_seconds():
    try:
        hours = float(os.getenv("WANDERING_REPAIR_NAMES_COOLDOWN_HOURS", "24"))
    except Exception:
        hours = 24
    return max(1, int(hours * 3600))


def should_run_startup_display_name_repair(config, now_ts):
    if not startup_display_name_repair_enabled():
        return False

    try:
        last_repair = float(config.get("last_display_name_repair_ts", 0) or 0)
    except Exception:
        last_repair = 0

    return now_ts - last_repair >= startup_display_name_repair_cooldown_seconds()


async def repair_display_names_for_active_guilds(force=False):
    if not force and not startup_display_name_repair_enabled():
        print("DISPLAY NAME REPAIR SKIPPED: startup repair disabled")
        return

    now_ts = datetime.now(UTC).timestamp()
    changed = False

    for guild in bot.guilds:
        try:
            guild_id = str(guild.id)
            config = guild_configs.setdefault(guild_id, new_guild_config(guild))

            if not force and not should_run_startup_display_name_repair(config, now_ts):
                continue

            repaired = await repair_guild_display_names(guild, config)
            config["last_display_name_repair_ts"] = now_ts
            changed = True
            if repaired:
                print(f"DISPLAY NAME REPAIR {guild.id}: {repaired}")
        except Exception as error:
            print(f"DISPLAY NAME REPAIR ERROR {guild.id}: {error}")

    if changed:
        save_guild_configs()


async def ensure_bot_updates_channel(guild, config, force=False):
    channels = config.setdefault("channels", {})
    if is_channel_key_disabled(config, "bot_updates") and not force:
        return None

    if force:
        set_channel_key_disabled(config, "bot_updates", False)

    channel = bot.get_channel(channels.get("bot_updates"))
    if channel:
        return channel

    for existing in guild.text_channels:
        if channel_matches_saved_key(existing, "bot_updates"):
            channels["bot_updates"] = existing.id
            save_guild_configs()
            return existing

    category_name = "📢✨┃BOT NEWS & UPDATES┃✨📢"
    category = None
    for existing_category in guild.categories:
        normalized = normalize_discord_name(existing_category.name)
        if "botnews" in normalized or "botupdates" in normalized or "updates" in normalized:
            category = existing_category
            break

    if not category:
        category = await guild.create_category(category_name)

    channel = await guild.create_text_channel(
        DEFAULT_CHANNEL_NAMES["bot_updates"],
        category=category
    )
    channels["bot_updates"] = channel.id
    save_guild_configs()
    return channel


async def publish_bot_update_notes(guild, config, *, force=False):
    channel = await ensure_bot_updates_channel(guild, config, force=force)
    if not channel:
        return 0, None

    posted = set(config.setdefault("posted_bot_update_ids", []))
    sent = 0

    for note in BOT_UPDATE_NOTES:
        note_id = note["id"]
        if not force and note_id in posted:
            continue

        embed = discord.Embed(
            title=f"BOT UPDATE: {note['title']}",
            description=note["summary"],
            color=0xF1C40F
        )
        embed.add_field(name="Commands", value=note.get("commands", "No commands changed."), inline=False)
        embed.add_field(name="Who Uses It", value=note.get("audience", "Everyone"), inline=False)
        embed.add_field(name="Privacy", value="No tokens, passwords, private logs, or sensitive setup details are posted here.", inline=False)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text=f"Wandering Bot Alpha - Update ID {note_id}")
        embed.timestamp = datetime.now(UTC)
        await channel.send(embed=style_embed(embed))
        posted.add(note_id)
        sent += 1

    config["posted_bot_update_ids"] = sorted(posted)
    save_guild_configs()
    return sent, channel


async def publish_bot_updates_for_active_guilds():
    for guild in bot.guilds:
        try:
            guild_id = str(guild.id)
            config = guild_configs.setdefault(guild_id, new_guild_config(guild))
            await publish_bot_update_notes(guild, config)
        except Exception as error:
            print(f"BOT UPDATE FEED ERROR {guild.id}: {error}")


def resolve_channel_key(text):
    wanted = normalize_discord_name(text)
    if not wanted:
        return None

    for key in DEFAULT_CHANNEL_NAMES:
        if wanted == normalize_discord_name(key):
            return key
        if wanted == normalize_discord_name(DEFAULT_CHANNEL_NAMES.get(key, "")):
            return key
        for alias in CHANNEL_ALIASES.get(key, []):
            if wanted == normalize_discord_name(alias):
                return key

    return None


def format_channel_restore_packs():
    lines = []
    for pack, keys in CHANNEL_RESTORE_PACKS.items():
        if pack == "all":
            continue
        lines.append(f"`{pack}` - {len(keys)} channel(s)")
    lines.append("`all` - every bot channel")
    return "\n".join(lines)


async def restore_disabled_bot_channels(guild, config, channel_key=None, channel_keys=None):
    disabled = list(disabled_channel_keys(config))
    if channel_key:
        resolved = resolve_channel_key(channel_key)
        if not resolved:
            return [], f"`{channel_key}` is not a bot channel key I recognise."
        keys_to_restore = [resolved]
    elif channel_keys is not None:
        keys_to_restore = [key for key in channel_keys if key in DEFAULT_CHANNEL_NAMES]
    else:
        keys_to_restore = disabled

    restored = []
    for key in keys_to_restore:
        name = DEFAULT_CHANNEL_NAMES.get(key)
        if not name:
            continue

        if key == "bot_updates":
            channel = await ensure_bot_updates_channel(guild, config, force=True)
        elif key == "cheat_checks":
            channel = await ensure_cheat_check_channel(guild, config, force=True)
        elif key == "public_shame":
            channel = await ensure_public_shame_channel(guild, config, force=True)
        else:
            channel = await get_or_create_feed_channel(
                guild,
                config,
                key,
                name,
                private=key in PRIVATE_FEED_CHANNEL_KEYS,
                force=True
            )

        if channel:
            restored.append(f"`{key}` -> {channel.mention}")

    save_guild_configs()
    return restored, None


async def ensure_pve_channels(guild, config, force=False):
    channels = config.setdefault("channels", {})
    pve_channel_keys = [
        "pve_quests",
        "pve_hunting",
        "pve_collection",
        "pve_fishing",
        "pve_crafting",
        "pve_expeditions",
        "pve_info",
        "pve_help",
        "pve_heatmap"
    ]

    if not force and all(is_channel_key_disabled(config, key) for key in pve_channel_keys):
        return {}

    category_name = "🦌🌲🧭┃PVE EXPEDITIONS┃🧭🌲🦌"
    pve_category = None
    for category in guild.categories:
        normalized = normalize_discord_name(category.name)
        if "pve" in normalized or "pvemissions" in normalized:
            pve_category = category
            break

    if not pve_category:
        pve_category = await guild.create_category(category_name)
    elif pve_category.name != category_name:
        try:
            await pve_category.edit(name=category_name)
        except Exception:
            pass

    async def ensure_channel(key):
        name = DEFAULT_CHANNEL_NAMES[key]
        if is_channel_key_disabled(config, key) and not force:
            return None

        if force:
            set_channel_key_disabled(config, key, False)

        existing_id = channels.get(key)
        if existing_id:
            existing = guild.get_channel(existing_id)
            if existing:
                needs_name = existing.name != name
                needs_category = pve_category and existing.category_id != pve_category.id
                if needs_name or needs_category:
                    try:
                        await existing.edit(name=name, category=pve_category)
                    except Exception:
                        pass
                return existing

        for channel in guild.text_channels:
            if channel_matches_saved_key(channel, key):
                channels[key] = channel.id
                needs_name = channel.name != name
                needs_category = pve_category and channel.category_id != pve_category.id
                if needs_name or needs_category:
                    try:
                        await channel.edit(name=name, category=pve_category)
                    except Exception:
                        pass
                return channel

        channel = await guild.create_text_channel(name, category=pve_category)
        channels[key] = channel.id
        return channel

    created = {}
    for key in pve_channel_keys:
        channel = await ensure_channel(key)
        if channel:
            created[key] = channel

    config.setdefault("pve", {"enabled": True, "interval_hours": 12})
    save_guild_configs()
    return created


async def ensure_pve_channels_for_active_guilds():
    for guild in bot.guilds:
        try:
            guild_id = str(guild.id)
            config = guild_configs.setdefault(guild_id, new_guild_config(guild))
            await ensure_pve_channels(guild, config)
        except Exception as error:
            print(f"PVE SETUP ERROR {guild.id}: {error}")


class SlashContextAdapter:
    def __init__(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.guild = interaction.guild
        self.author = interaction.user
        self.channel = interaction.channel
        self.message = type("Msg", (), {"content": f"/{interaction.command.name}"})()

    async def send(self, content=None, embed=None):
        if not self.interaction.response.is_done():
            await self.interaction.response.send_message(content=content, embed=embed, ephemeral=True)
        else:
            await self.interaction.followup.send(content=content, embed=embed, ephemeral=True)


async def run_legacy_as_slash(interaction: discord.Interaction, legacy_name: str, *args, **kwargs):
    ctx = SlashContextAdapter(interaction)
    cmd = bot.get_command(legacy_name)
    if not cmd:
        await ctx.send(f"❌ Command `{legacy_name}` not found.")
        return
    await cmd.callback(ctx, *args, **kwargs)


def ensure_wallet(user):
    user_id = str(user.id)

    if user_id not in wallets:
        wallets[user_id] = {
            "name": str(user),
            "balance": 0,
            "daily_transactions": 0
        }

    return wallets[user_id]


async def translate_text(text, target_language="en", source_language="auto"):

    if not TRANSLATE_API_URL:
        return None

    payload = {
        "q": text,
        "source": source_language or "auto",
        "target": target_language or "en",
        "format": "text"
    }

    if TRANSLATE_API_KEY:
        payload["api_key"] = TRANSLATE_API_KEY

    try:
        response = await asyncio.to_thread(
            requests.post,
            TRANSLATE_API_URL,
            json=payload,
            timeout=12
        )

        if response.status_code != 200:
            print(f"TRANSLATION ERROR STATUS: {response.status_code}")
            return None

        data = response.json()
        return data.get("translatedText") or data.get("translated_text")

    except Exception as error:
        print(f"TRANSLATION ERROR: {error}")
        return None


async def maybe_translate_message(message):

    if not message.guild or not message.content.strip():
        return

    if message.content.startswith(("/", "!")):
        return

    guild_id = str(message.guild.id)
    config = guild_configs.get(guild_id, {})
    translation = config.get("translation", {})

    if not translation.get("enabled"):
        return

    source_channel_id = translation.get("source_channel_id")
    if source_channel_id and int(source_channel_id) != message.channel.id:
        return

    translated = await translate_text(
        message.content[:900],
        translation.get("target_language", "en"),
        translation.get("source_language", "auto")
    )

    if not translated or translated.strip() == message.content.strip():
        return

    mode = translation.get("mode", "same")
    target_channel = message.channel

    if mode == "channel":
        target_channel_id = translation.get("target_channel_id")
        target_channel = bot.get_channel(int(target_channel_id)) if target_channel_id else None

    if not target_channel:
        return

    embed = discord.Embed(
        title="Translation",
        description=translated[:1500],
        color=0x1ABC9C
    )
    embed.add_field(name="Original Author", value=message.author.mention, inline=True)
    embed.add_field(name="Target Language", value=translation.get("target_language", "en"), inline=True)

    if mode == "channel":
        embed.add_field(name="Original Channel", value=message.channel.mention, inline=False)

    await target_channel.send(embed=style_embed(embed))


async def apply_chat_reward_punishment_rules(message, lower):

    if not message.guild:
        return

    guild_id = str(message.guild.id)
    rules = guild_configs.get(guild_id, {}).get("chat_rules", [])

    if not rules:
        return

    matched = []
    wallet = ensure_wallet(message.author)

    for rule in rules:
        keyword = str(rule.get("keyword", "")).lower().strip()
        amount = int(rule.get("amount", 0))
        kind = rule.get("kind")

        if not keyword or amount <= 0 or keyword not in lower:
            continue

        if kind == "reward":
            wallet["balance"] += amount
            matched.append(f"Reward: +{amount} pennies for `{keyword}`")

        elif kind == "punishment":
            wallet["balance"] -= amount
            matched.append(f"Punishment: -{amount} pennies for `{keyword}`")

    if not matched:
        return

    save_wallets()

    embed = discord.Embed(
        title="Automated Economy Rule",
        description="\n".join(matched[:5]),
        color=0xF1C40F
    )
    embed.add_field(name="Survivor", value=message.author.mention, inline=True)
    embed.add_field(name="Wallet", value=f"{wallet['balance']} pennies", inline=True)

    await message.channel.send(embed=style_embed(embed))

# =========================================================
# LOADERS
# =========================================================

def load_guild_configs():
    global guild_configs

    guild_configs = load_json(GUILD_CONFIG_FILE)

    if os.path.isdir(GUILD_CONFIG_FOLDER):
        for config_file in os.listdir(GUILD_CONFIG_FOLDER):
            if not config_file.endswith(".json"):
                continue

            guild_id = config_file[:-5]
            guild_configs[guild_id] = load_json(
                os.path.join(GUILD_CONFIG_FOLDER, config_file)
            )


def save_guild_config(guild_id):
    guild_id = str(guild_id)
    config = guild_configs.get(guild_id)

    if not config:
        return

    save_json(
        os.path.join(GUILD_CONFIG_FOLDER, f"{guild_id}.json"),
        config
    )


def save_guild_configs():
    save_json(GUILD_CONFIG_FILE, guild_configs)

    for guild_id in guild_configs:
        save_guild_config(guild_id)


def load_player_stats():
    global player_stats
    player_stats = load_json(PLAYER_STATS_FILE)


def save_player_stats():
    save_json(PLAYER_STATS_FILE, player_stats)


def load_longshot_records():
    """Load top-N longshots per guild from disk. Migrates the legacy
    single-record-per-guild format (where each value was a dict of one
    longshot) into the new list-of-longshots format."""
    global longshot_records
    raw = load_json(LONGSHOT_RECORDS_FILE)
    migrated = {}
    for guild_id, value in (raw or {}).items():
        if isinstance(value, list):
            migrated[str(guild_id)] = value
        elif isinstance(value, dict) and value.get("killer"):
            migrated[str(guild_id)] = [value]
        else:
            migrated[str(guild_id)] = []
    longshot_records = migrated


def save_longshot_records():
    save_json(LONGSHOT_RECORDS_FILE, longshot_records)


def load_first_blood():
    global first_blood_today, final_kill_today
    data = load_json(FIRST_BLOOD_FILE)
    first_blood_today = data.get("first_blood", {}) if isinstance(data, dict) else {}
    final_kill_today = data.get("final_kill", {}) if isinstance(data, dict) else {}


def save_first_blood():
    save_json(FIRST_BLOOD_FILE, {
        "first_blood": first_blood_today,
        "final_kill": final_kill_today,
    })


def record_longshot(guild_id, longshot_dict):
    """Append a new longshot to the guild's list, keep sorted desc by
    distance, cap at LONGSHOT_LEADERBOARD_LIMIT. Returns True if the new
    shot is a new server record (i.e., it's now #1)."""
    gid = str(guild_id)
    records = longshot_records.setdefault(gid, [])
    records.append(longshot_dict)
    records.sort(key=lambda r: float(r.get("distance", 0) or 0), reverse=True)
    if len(records) > LONGSHOT_LEADERBOARD_LIMIT:
        del records[LONGSHOT_LEADERBOARD_LIMIT:]
    save_longshot_records()
    return records[0] is longshot_dict


# =========================================================
# DAILY RECAP / NEWS / SQUAD STATE
# =========================================================

def load_daily_recap():
    global daily_recap_data
    daily_recap_data = load_json(DAILY_RECAP_FILE) or {}


def save_daily_recap():
    save_json(DAILY_RECAP_FILE, daily_recap_data)


def load_recap_posted():
    global recap_posted
    recap_posted = load_json(RECAP_POSTED_FILE) or {}


def save_recap_posted():
    save_json(RECAP_POSTED_FILE, recap_posted)


def _today_key(event_time=None):
    when = event_time or datetime.now(UTC)
    return when.date().isoformat()


def _yesterday_key(event_time=None):
    when = event_time or datetime.now(UTC)
    return (when.date() - timedelta(days=1)).isoformat()


def record_daily_kill(guild_id, killer, victim, weapon, distance, headshot, zone, vehicle=False, event_time=None):
    """Aggregate a single kill event into the day's recap bucket."""
    gid = str(guild_id)
    today = _today_key(event_time)
    bucket = daily_recap_data.setdefault(gid, {}).setdefault(today, {
        "total_kills": 0,
        "headshots": 0,
        "vehicle_kills": 0,
        "killers": {},
        "victims": {},
        "weapons": {},
        "zones": {},
        "biggest_shot": None,
    })
    bucket["total_kills"] = bucket.get("total_kills", 0) + 1
    if headshot:
        bucket["headshots"] = bucket.get("headshots", 0) + 1
    if vehicle:
        bucket["vehicle_kills"] = bucket.get("vehicle_kills", 0) + 1
    bucket["killers"][killer] = bucket["killers"].get(killer, 0) + 1
    bucket["victims"][victim] = bucket["victims"].get(victim, 0) + 1
    if weapon:
        bucket["weapons"][weapon] = bucket["weapons"].get(weapon, 0) + 1
    if zone:
        bucket["zones"][zone] = bucket["zones"].get(zone, 0) + 1
    biggest = bucket.get("biggest_shot") or {"distance": 0}
    try:
        d = float(distance or 0)
    except Exception:
        d = 0.0
    if d > float(biggest.get("distance", 0) or 0):
        bucket["biggest_shot"] = {
            "killer": killer,
            "victim": victim,
            "weapon": weapon,
            "distance": d,
        }
    # Cap retention to last 60 days per guild
    if len(daily_recap_data[gid]) > 60:
        oldest = sorted(daily_recap_data[gid].keys())[:-60]
        for k in oldest:
            daily_recap_data[gid].pop(k, None)
    save_daily_recap()


# =========================================================
# BOUNTIES
# =========================================================

def load_bounties():
    global bounties
    bounties = load_json(BOUNTIES_FILE) or {}


def save_bounties():
    save_json(BOUNTIES_FILE, bounties)


def _bounty_key(name):
    return (name or "").strip().lower()


def add_bounty(guild_id, target, amount, posted_by):
    gid = str(guild_id)
    key = _bounty_key(target)
    if not key or amount <= 0:
        return None
    entry = bounties.setdefault(gid, {}).setdefault(key, {
        "target": target,
        "amount": 0,
        "posted_by": posted_by,
        "posted_at": datetime.now(UTC).isoformat(),
        "currency": BOUNTY_CURRENCY,
    })
    entry["amount"] += int(amount)
    entry["target"] = target  # preserve casing
    entry["last_topup_at"] = datetime.now(UTC).isoformat()
    save_bounties()
    return entry


def get_bounty(guild_id, target):
    return bounties.get(str(guild_id), {}).get(_bounty_key(target))


def clear_bounty(guild_id, target):
    return bounties.get(str(guild_id), {}).pop(_bounty_key(target), None)


def list_bounties(guild_id):
    return list(bounties.get(str(guild_id), {}).values())


def claim_bounty_on_kill(guild_id, killer, victim):
    """If the victim has a bounty, transfer the prize to the killer's
    stats and clear the bounty. Returns the claimed bounty dict or None."""
    bounty = get_bounty(guild_id, victim)
    if not bounty:
        return None
    amount = int(bounty.get("amount", 0) or 0)
    if amount <= 0:
        return None
    add_player_stat(guild_id, killer, "bounty_claims")
    add_player_stat(guild_id, killer, "bounty_earnings", amount=amount)
    save_player_stats()
    clear_bounty(guild_id, victim)
    return {**bounty, "claimed_by": killer, "claimed_amount": amount}


# =========================================================
# SURVIVAL STREAKS
# =========================================================

def load_survival_streaks():
    global survival_streaks
    survival_streaks = load_json(SURVIVAL_STREAKS_FILE) or {}


def save_survival_streaks():
    save_json(SURVIVAL_STREAKS_FILE, survival_streaks)


def note_player_alive(guild_id, player_name, event_time=None):
    """Mark a player as alive today. If they have no current streak,
    start one. Returns the updated streak entry."""
    if not player_name or player_name == "Unknown":
        return None
    gid = str(guild_id)
    today = _today_key(event_time)
    entry = survival_streaks.setdefault(gid, {}).setdefault(player_name, {
        "streak_start_date": today,
        "last_alive_date": today,
        "longest_days": 1,
        "current_days": 1,
    })
    last_alive = entry.get("last_alive_date") or today
    try:
        last_date = datetime.strptime(last_alive, "%Y-%m-%d").date()
        today_date = datetime.strptime(today, "%Y-%m-%d").date()
        gap = (today_date - last_date).days
    except Exception:
        gap = 0
    if gap == 0:
        pass  # same day, no change
    elif gap == 1:
        entry["current_days"] = int(entry.get("current_days", 0) or 0) + 1
    else:
        entry["streak_start_date"] = today
        entry["current_days"] = 1
    entry["last_alive_date"] = today
    if int(entry.get("current_days", 0) or 0) > int(entry.get("longest_days", 0) or 0):
        entry["longest_days"] = int(entry["current_days"])
    # Mirror onto player_stats so /playercard can show it
    stats = ensure_player_stats_record(guild_id, player_name)
    if stats:
        stats["current_streak_days"] = entry["current_days"]
        stats["longest_streak_days"] = entry["longest_days"]
        stats["streak_start_date"] = entry["streak_start_date"]
        stats["last_alive_date"] = entry["last_alive_date"]
    save_survival_streaks()
    return entry


def reset_player_streak(guild_id, player_name, event_time=None):
    """Player died — wipe their current streak (preserve longest)."""
    if not player_name or player_name == "Unknown":
        return None
    gid = str(guild_id)
    entry = survival_streaks.setdefault(gid, {}).setdefault(player_name, {
        "streak_start_date": "",
        "last_alive_date": "",
        "longest_days": 0,
        "current_days": 0,
    })
    broken_days = int(entry.get("current_days", 0) or 0)
    entry["current_days"] = 0
    entry["streak_start_date"] = ""
    entry["last_alive_date"] = ""
    stats = ensure_player_stats_record(guild_id, player_name)
    if stats:
        stats["current_streak_days"] = 0
        stats["streak_start_date"] = ""
    save_survival_streaks()
    return broken_days


def get_streak_milestone(days):
    """If `days` crosses one of the milestones, return it, else None."""
    return days if days in SURVIVAL_STREAK_MILESTONES else None


# =========================================================
# 🏆 ACHIEVEMENTS / BADGES
# =========================================================

ACHIEVEMENT_DEFS = {
    # id: (display_name, emoji, description, evaluator(stats, ctx)->bool)
    "first_blood":       ("First Blood",        "🩸", "Get your first PvP kill."),
    "double_digits":     ("Double Digits",      "💯", "Reach 10 PvP kills."),
    "century_club":      ("Century Club",       "💯", "Reach 100 PvP kills."),
    "killer_instinct":   ("Killer Instinct",    "☠️", "Reach 500 PvP kills."),
    "headhunter":        ("Headhunter",         "🎯", "Land 10 headshots."),
    "headhunter_elite":  ("Elite Headhunter",   "🎯", "Land 100 headshots."),
    "longshot_300":      ("Reach Out",          "🔭", "Confirm a 300m+ kill."),
    "longshot_500":      ("Sniper",             "🔭", "Confirm a 500m+ kill."),
    "longshot_700":      ("Marksman God",       "🔭", "Confirm a 700m+ kill."),
    "rampage_first":     ("Rampage",            "🔥", "Notch your first 3-kill rampage."),
    "rampage_5":         ("Unstoppable",        "💥", "Notch a 5-kill rampage."),
    "vehicle_kill":      ("Hit & Run",          "🚗", "Get a vehicle kill."),
    "vehicular_psycho":  ("Vehicular Psycho",   "🚗", "Get 10 vehicle kills."),
    "iron_lung":         ("Iron Lung",          "🫁", "Survive 7 consecutive days."),
    "iron_lung_30":      ("Iron Veteran",       "🛡️", "Survive 30 consecutive days."),
    "iron_lung_100":     ("Cockroach",          "🪳", "Survive 100 consecutive days."),
    "bounty_hunter":     ("Bounty Hunter",      "💰", "Claim your first bounty."),
    "bounty_pro":        ("Bounty Pro",         "💰", "Claim 5 bounties."),
    "nemesis":           ("Nemesis",            "👹", "Kill the same player 5 times."),
    "thousand_yard":     ("Thousand-Yard Stare", "👁️", "Spend 24+ hours online."),
    "builder":           ("Architect",          "🔨", "Place 50 building parts."),
    "raider":            ("Raider",             "💣", "Tear down 10 enemy structures."),
    "hunter":            ("Hunter",             "🏹", "Take down 25 animals."),
}


def load_achievements():
    global achievements_data
    achievements_data = load_json(ACHIEVEMENTS_FILE) or {}


def save_achievements():
    save_json(ACHIEVEMENTS_FILE, achievements_data)


def _player_achievements(guild_id, player):
    gid = str(guild_id)
    return achievements_data.setdefault(gid, {}).setdefault(player, {
        "unlocked": [],
        "unlocked_at": {},
    })


def _award_achievement(guild_id, player, badge_id):
    """Unlock badge if not already; returns the badge tuple to announce,
    or None if already unlocked."""
    if badge_id not in ACHIEVEMENT_DEFS or not player or player == "Unknown":
        return None
    entry = _player_achievements(guild_id, player)
    if badge_id in entry["unlocked"]:
        return None
    entry["unlocked"].append(badge_id)
    entry["unlocked_at"][badge_id] = datetime.now(UTC).isoformat()
    save_achievements()
    return ACHIEVEMENT_DEFS[badge_id]


def evaluate_achievements_for_player(guild_id, player, *, just_kill=False, distance=0, headshot=False, vehicle_kill=False, claimed_bounty=False, nemesis_count=0):
    """Run all evaluators for a player and return list of newly-unlocked badges."""
    stats = player_stats.get(player) or {}
    newly = []

    def maybe(badge_id, condition):
        if condition:
            badge = _award_achievement(guild_id, player, badge_id)
            if badge:
                newly.append((badge_id, badge))

    kills = int(stats.get("kills", 0) or 0)
    headshots = int(stats.get("headshots", 0) or 0)
    vehicle_kills = int(stats.get("vehicle_kills", 0) or 0)
    rampages = int(stats.get("rampages", 0) or 0)
    multikill_best = int(stats.get("multikill_best", 0) or 0)
    longest_shot = float(stats.get("longest_shot_distance", 0) or 0)
    current_streak = int(stats.get("current_streak_days", 0) or 0)
    bounty_claims = int(stats.get("bounty_claims", 0) or 0)
    time_online = int(stats.get("time_online_seconds", 0) or 0)
    builds = int(stats.get("builds", 0) or 0)
    raids = int(stats.get("raids", 0) or 0)
    animals = int(stats.get("animals_hunted", 0) or 0)

    maybe("first_blood",      kills >= 1)
    maybe("double_digits",    kills >= 10)
    maybe("century_club",     kills >= 100)
    maybe("killer_instinct",  kills >= 500)
    maybe("headhunter",       headshots >= 10)
    maybe("headhunter_elite", headshots >= 100)
    maybe("longshot_300",     longest_shot >= 300 or distance >= 300)
    maybe("longshot_500",     longest_shot >= 500 or distance >= 500)
    maybe("longshot_700",     longest_shot >= 700 or distance >= 700)
    maybe("rampage_first",    rampages >= 1 or multikill_best >= 3)
    maybe("rampage_5",        multikill_best >= 5)
    maybe("vehicle_kill",     vehicle_kills >= 1 or vehicle_kill)
    maybe("vehicular_psycho", vehicle_kills >= 10)
    maybe("iron_lung",        current_streak >= 7)
    maybe("iron_lung_30",     current_streak >= 30)
    maybe("iron_lung_100",    current_streak >= 100)
    maybe("bounty_hunter",    bounty_claims >= 1 or claimed_bounty)
    maybe("bounty_pro",       bounty_claims >= 5)
    maybe("nemesis",          nemesis_count >= 5)
    maybe("thousand_yard",    time_online >= 86400)
    maybe("builder",          builds >= 50)
    maybe("raider",           raids >= 10)
    maybe("hunter",           animals >= 25)
    return newly


async def announce_achievements(channel, guild_id, player, unlocked):
    """Post a single embed with all newly unlocked badges for a player."""
    if not channel or not unlocked:
        return
    lines = [f"{badge[1]} **{badge[0]}** — {badge[2]}" for _, badge in unlocked]
    embed = discord.Embed(
        title=f"🏆 ACHIEVEMENT UNLOCKED — {player}",
        description="\n".join(lines),
        color=0xF1C40F,
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text=f"Wandering Bot Alpha — Achievement System")
    embed.timestamp = datetime.now(UTC)
    try:
        await channel.send(embed=style_embed(embed))
    except Exception as err:
        print(f"[ACHIEVEMENT] post failed: {err}")


# =========================================================
# 👹 NEMESIS TRACKING
# =========================================================

def load_nemesis():
    global nemesis_data
    nemesis_data = load_json(NEMESIS_FILE) or {}


def save_nemesis():
    save_json(NEMESIS_FILE, nemesis_data)


def record_nemesis(guild_id, killer, victim):
    """Bump the kill-count for (killer→victim). Returns the new count."""
    if not killer or not victim or killer == victim:
        return 0
    gid = str(guild_id)
    entry = nemesis_data.setdefault(gid, {}).setdefault(killer, {})
    entry[victim] = int(entry.get(victim, 0) or 0) + 1
    save_nemesis()
    return entry[victim]


def get_top_nemeses(guild_id, player, limit=3):
    """Players that have killed `player` the most times."""
    gid = str(guild_id)
    counts = {}
    for killer, victims in (nemesis_data.get(gid) or {}).items():
        if killer == player:
            continue
        n = int(victims.get(player, 0) or 0)
        if n:
            counts[killer] = n
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]


def get_top_victims(guild_id, player, limit=3):
    """Players that this player has killed the most."""
    gid = str(guild_id)
    counts = (nemesis_data.get(gid) or {}).get(player) or {}
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]


# =========================================================
# 🔫 ALIVE-STREAK (kills since last death)
# =========================================================

def load_alive_streaks():
    global alive_streaks
    alive_streaks = load_json(ALIVE_STREAKS_FILE) or {}


def save_alive_streaks():
    save_json(ALIVE_STREAKS_FILE, alive_streaks)


def bump_alive_streak(guild_id, player, event_time=None):
    """Add 1 to player's current kill-spree. Returns the new count."""
    if not player or player == "Unknown":
        return 0
    gid = str(guild_id)
    entry = alive_streaks.setdefault(gid, {}).setdefault(player, {
        "current_spree": 0,
        "best_spree": 0,
        "last_kill_at": "",
    })
    entry["current_spree"] = int(entry.get("current_spree", 0) or 0) + 1
    if entry["current_spree"] > int(entry.get("best_spree", 0) or 0):
        entry["best_spree"] = entry["current_spree"]
    entry["last_kill_at"] = (event_time or datetime.now(UTC)).isoformat()
    save_alive_streaks()
    return entry["current_spree"]


def end_alive_streak(guild_id, player):
    """Player died — return (ended_spree, best_spree) and zero current."""
    if not player or player == "Unknown":
        return 0, 0
    gid = str(guild_id)
    entry = alive_streaks.setdefault(gid, {}).setdefault(player, {
        "current_spree": 0,
        "best_spree": 0,
        "last_kill_at": "",
    })
    ended = int(entry.get("current_spree", 0) or 0)
    best = int(entry.get("best_spree", 0) or 0)
    entry["current_spree"] = 0
    save_alive_streaks()
    return ended, best


# =========================================================
# 🎯 DAILY CHALLENGES
# =========================================================

CHALLENGE_POOL = [
    {"id": "hs3",          "name": "Triple-Tap",      "desc": "Land 3 headshots today.",        "type": "headshots",     "target": 3,  "reward": 100},
    {"id": "k5",           "name": "Body Count",       "desc": "Get 5 PvP kills today.",         "type": "kills",         "target": 5,  "reward": 150},
    {"id": "k10",          "name": "Death Dealer",     "desc": "Get 10 PvP kills today.",        "type": "kills",         "target": 10, "reward": 300},
    {"id": "ls300",        "name": "Reach Out",        "desc": "Land a 300m+ shot today.",       "type": "longshot",      "target": 300, "reward": 200},
    {"id": "ls500",        "name": "Cold Sniper",      "desc": "Land a 500m+ shot today.",       "type": "longshot",      "target": 500, "reward": 400},
    {"id": "veh1",         "name": "Hit & Run",        "desc": "Score a vehicle kill today.",    "type": "vehicle_kills", "target": 1,  "reward": 250},
    {"id": "rampage",      "name": "Rampage Ready",    "desc": "Land a 3-kill rampage today.",   "type": "rampage",       "target": 3,  "reward": 350},
    {"id": "survive",      "name": "Stay Frosty",      "desc": "Be online but stay alive today.","type": "survive_day",   "target": 1,  "reward": 200},
]


def load_daily_challenges():
    global daily_challenges
    daily_challenges = load_json(DAILY_CHALLENGE_FILE) or {}


def save_daily_challenges():
    save_json(DAILY_CHALLENGE_FILE, daily_challenges)


def get_or_roll_daily_challenge(guild_id, event_time=None):
    """Return today's challenge for the guild, generating one if missing."""
    gid = str(guild_id)
    today = _today_key(event_time)
    state = daily_challenges.get(gid) or {}
    if state.get("date") == today and state.get("challenge"):
        return state
    # Pick by hash of date+guild for deterministic per-day selection
    seed = int(hashlib.sha1(f"{gid}-{today}".encode()).hexdigest(), 16)
    challenge = CHALLENGE_POOL[seed % len(CHALLENGE_POOL)]
    state = {
        "date": today,
        "challenge": challenge,
        "completed_by": [],
        "progress": {},
    }
    daily_challenges[gid] = state
    save_daily_challenges()
    return state


def progress_daily_challenge(guild_id, player, *, kill_distance=0, headshot=False, vehicle_kill=False, rampage_size=0, event_time=None):
    """Update a player's progress on today's challenge. Returns the
    challenge dict if they just completed it, else None."""
    if not player or player == "Unknown":
        return None
    state = get_or_roll_daily_challenge(guild_id, event_time)
    ch = state.get("challenge") or {}
    completed_by = state.setdefault("completed_by", [])
    if player in completed_by:
        return None
    progress = state.setdefault("progress", {}).setdefault(player, 0)
    ch_type = ch.get("type")
    bumped = False
    if ch_type == "kills":
        state["progress"][player] = progress + 1
        bumped = True
    elif ch_type == "headshots" and headshot:
        state["progress"][player] = progress + 1
        bumped = True
    elif ch_type == "vehicle_kills" and vehicle_kill:
        state["progress"][player] = progress + 1
        bumped = True
    elif ch_type == "longshot" and kill_distance >= ch.get("target", 0):
        state["progress"][player] = ch.get("target", 0)
        bumped = True
    elif ch_type == "rampage" and rampage_size >= ch.get("target", 0):
        state["progress"][player] = ch.get("target", 0)
        bumped = True
    if not bumped:
        return None
    if state["progress"][player] >= int(ch.get("target", 1) or 1):
        completed_by.append(player)
        save_daily_challenges()
        return ch
    save_daily_challenges()
    return None


# =========================================================
# AI DEATH ROAST (Emergent Universal LLM Key)
# =========================================================

_AI_ROAST_FALLBACKS = [
    "Map called. Said you forgot to read it.",
    "{killer} just turned {victim} into loot.",
    "{victim}'s last words: 'where's the shot coming from'.",
    "{distance:.0f}m. {weapon}. Cold.",
    "{victim} blinked. {killer} did not.",
    "Inventory: tab → empty.",
    "Server tick ate {victim} before {killer} did.",
    "{killer} sends regards. And one bullet.",
    "{victim} respawned harder than they spawned.",
    "Coastal start incoming for {victim}.",
]


def _format_fallback_roast(killer, victim, weapon, distance):
    template = random.choice(_AI_ROAST_FALLBACKS)
    try:
        return template.format(
            killer=killer or "Unknown",
            victim=victim or "Unknown",
            weapon=weapon or "Unknown",
            distance=float(distance or 0),
        )
    except Exception:
        return template


async def generate_death_roast(killer, victim, weapon, distance, headshot=False, tone=None):
    """Return a short (<= ~22 word) one-liner roast for the killfeed.
    Uses the Emergent Universal LLM key via emergentintegrations. If the
    key is missing or the call fails, returns a deterministic fallback so
    the killfeed never blocks on AI."""
    killer = (killer or "Unknown").strip()
    victim = (victim or "Unknown").strip()
    weapon = (weapon or "Unknown").strip()
    try:
        distance = float(distance or 0)
    except Exception:
        distance = 0.0

    if not EMERGENT_LLM_KEY:
        return _format_fallback_roast(killer, victim, weapon, distance)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as error:
        print(f"[AI ROAST] emergentintegrations import failed: {error}")
        return _format_fallback_roast(killer, victim, weapon, distance)

    tone_value = (tone or AI_ROAST_TONE or "mixed").lower()
    tone_hint = {
        "edgy": "Tone: dark, edgy DayZ humour. Punchy. No slurs, no real-world tragedies.",
        "pg13": "Tone: PG-13 witty/sarcastic. No swears.",
        "brutal_clean": "Tone: brutal but clean. No swears. Make it sting.",
    }.get(tone_value, "Tone: pick at random between dark/edgy, witty/sarcastic, and brutal-but-clean.")

    headshot_hint = " It was a HEADSHOT — reference that." if headshot else ""
    distance_hint = f" Distance: {distance:.0f}m." if distance >= 50 else ""

    prompt = (
        f"Kill event:\n"
        f"- Killer: {killer}\n"
        f"- Victim: {victim}\n"
        f"- Weapon: {weapon}\n"
        f"- Distance: {distance:.0f}m\n"
        f"- Headshot: {'yes' if headshot else 'no'}\n\n"
        f"{tone_hint}{headshot_hint}{distance_hint}\n"
        f"Return ONLY the one-liner. No prefix, no quotes."
    )

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"roast-{hashlib.sha1(f'{killer}{victim}{weapon}{distance}'.encode()).hexdigest()[:12]}",
            system_message=AI_ROAST_SYSTEM_PROMPT,
        ).with_model(AI_ROAST_PROVIDER, AI_ROAST_MODEL)

        response = await asyncio.wait_for(
            chat.send_message(UserMessage(text=prompt)),
            timeout=AI_ROAST_TIMEOUT_SECONDS,
        )
        text = (str(response or "")).strip()
        # Strip any wrapping quotes/backticks the model might add
        text = text.strip('"').strip("'").strip("`").strip()
        # Single line only
        text = text.splitlines()[0] if text else ""
        # Hard cap at 220 chars so it always fits a Discord embed field
        if len(text) > 220:
            text = text[:217].rstrip() + "..."
        return text or _format_fallback_roast(killer, victim, weapon, distance)
    except asyncio.TimeoutError:
        print("[AI ROAST] LLM call timed out — using fallback")
        return _format_fallback_roast(killer, victim, weapon, distance)
    except Exception as error:
        print(f"[AI ROAST] LLM call failed ({error}) — using fallback")
        return _format_fallback_roast(killer, victim, weapon, distance)


def guild_roasts_enabled(guild_id):
    """AI death roasts are OFF by default; admins must opt in."""
    gid = str(guild_id)
    config = guild_configs.get(gid, {})
    return bool(config.get("roasts_enabled", False))


def guild_roast_tone(guild_id):
    gid = str(guild_id)
    config = guild_configs.get(gid, {})
    return (config.get("roast_tone") or AI_ROAST_TONE or "mixed").lower()


def load_heatmap():
    global territory_heat
    territory_heat = load_json(HEATMAP_FILE)


def save_heatmap():
    save_json(HEATMAP_FILE, territory_heat)


def load_swear_jar():
    global swear_jar
    swear_jar = load_json(SWEAR_JAR_FILE)


def save_swear_jar():
    save_json(SWEAR_JAR_FILE, swear_jar)


def load_linked_players():
    global linked_players
    linked_players = load_json(LINKED_PLAYERS_FILE)


def save_linked_players():
    save_json(LINKED_PLAYERS_FILE, linked_players)


def load_support_tickets():
    global support_tickets
    support_tickets = load_json(SUPPORT_TICKETS_FILE)


def save_support_tickets():
    save_json(SUPPORT_TICKETS_FILE, support_tickets)


def load_factions():
    global factions
    factions = load_json(FACTIONS_FILE)


def save_factions():
    save_json(FACTIONS_FILE, factions)


def load_pve_challenges():
    global pve_challenges
    pve_challenges = load_json(PVE_CHALLENGES_FILE)


def save_pve_challenges():
    save_json(PVE_CHALLENGES_FILE, pve_challenges)


def stable_line_hash(line):
    return hashlib.sha256(
        line.encode("utf-8", errors="ignore")
    ).hexdigest()


_ADM_TIME_PREFIX_RE = re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})\b")


def extract_adm_event_time(line, *, now=None):
    """Extract the in-game wall-clock time from an ADM log line and return
    a timezone-aware UTC datetime, or None if the line has no recognisable
    `HH:MM:SS` prefix.

    DayZ ADM lines look like:
        01:23:45 | Player "Bob" (id=ABC pos=<x, 0, z>) is connected
    The log only stores HH:MM:SS, never a date — we anchor it to today's
    UTC date (or yesterday's if the parsed time is *more* than 12 hours
    in the future relative to `now`, which handles late-night scans
    where the log line was written just before UTC midnight).
    """
    if not line:
        return None
    match = _ADM_TIME_PREFIX_RE.match(line)
    if not match:
        return None
    try:
        hh = int(match.group(1))
        mm = int(match.group(2))
        ss = int(match.group(3))
        if not (0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60):
            return None
    except Exception:
        return None

    reference = now or datetime.now(UTC)
    candidate = reference.replace(hour=hh, minute=mm, second=ss, microsecond=0)
    # ADM lines are always written in the past relative to "now". If the
    # parsed time appears to be more than 5 minutes in the future (a small
    # buffer for clock skew between the game server and the bot), it must
    # actually be from yesterday's log.
    if candidate > reference + timedelta(minutes=5):
        candidate -= timedelta(days=1)
    return candidate


def load_processed_adm_lines():
    global processed_lines

    data = load_json(PROCESSED_ADM_FILE)
    processed_lines = {}

    for guild_id, hashes in data.items():
        if isinstance(hashes, list):
            # Use an OrderedDict as an insertion-ordered set so trimming
            # always evicts the oldest entries, never random ones.
            ordered = OrderedDict()
            for item in hashes:
                ordered[str(item)] = None
            processed_lines[str(guild_id)] = ordered


def save_processed_adm_lines():
    data = {}

    for guild_id, hashes in processed_lines.items():
        # `hashes` is an OrderedDict; keep the most recent
        # PROCESSED_ADM_CACHE_LIMIT keys for crash recovery.
        keys = list(hashes.keys()) if isinstance(hashes, OrderedDict) else list(hashes)
        data[guild_id] = keys[-PROCESSED_ADM_CACHE_LIMIT:]

    save_json(PROCESSED_ADM_FILE, data)


def remember_processed_line(guild_id, line_hash):
    ensure_guild_runtime(guild_id)
    cache = processed_lines[guild_id]

    # Move to end if it already existed; otherwise insert at the end.
    # Either way, the entry is now the "most recently seen" so it will
    # be the last to be evicted by the FIFO trim below.
    if line_hash in cache:
        cache.move_to_end(line_hash)
    else:
        cache[line_hash] = None

    # Deterministic FIFO trim: drop the oldest entries until at limit.
    while len(cache) > PROCESSED_ADM_CACHE_LIMIT:
        cache.popitem(last=False)

    save_processed_adm_lines()


def active_guild_ids():
    return {str(guild.id) for guild in bot.guilds}


def is_active_guild(guild_id):
    return str(guild_id) in active_guild_ids()


def active_guild_config_items():
    active_ids = active_guild_ids()

    for guild_id, config in list(guild_configs.items()):
        if str(guild_id) in active_ids:
            yield str(guild_id), config


def bootstrap_runtime_from_connected_guilds():
    changed = False

    for guild in bot.guilds:
        guild_id = str(guild.id)

        if guild_id not in guild_configs:
            guild_configs[guild_id] = new_guild_config(guild)
            changed = True

        guild_configs[guild_id].setdefault("guild_name", guild.name)
        guild_configs[guild_id].setdefault("guild_owner", str(guild.owner))
        guild_configs[guild_id].setdefault("admin_roles", DEFAULT_ADMIN_ROLES.copy())
        guild_configs[guild_id].setdefault("channels", {})

        if is_showcase_guild(guild_id):
            guild_configs[guild_id]["is_showcase_guild"] = True
            guild_configs[guild_id]["showcase_mode"] = True
            guild_configs[guild_id]["disabled_channels"] = [
                key for key in DEFAULT_CHANNEL_NAMES
                if key not in {"general_chat", "ai_chat", "help_channel", "company_announcements"}
            ]

        if discover_existing_guild_channels(guild, guild_configs[guild_id]):
            changed = True

        ensure_guild_runtime(guild_id)

    if changed:
        save_guild_configs()


# =========================================================
# EVENT CLASSIFIER
# =========================================================

def get_zone_from_line(line):

    lower = line.lower()

    for zone, keywords in zone_keywords.items():

        for keyword in keywords:

            if keyword in lower:
                return zone

    coords = extract_adm_coords(line)
    if coords:
        return zone_from_coords(coords)

    return "Unknown"


def zone_from_coords(coords):
    try:
        x_text, y_text = coords.split(",")[:2]
        x = float(x_text.strip())
        y = float(y_text.strip())
    except Exception:
        return "Unknown"

    east_west = "West" if x < 5120 else "Central" if x < 10240 else "East"
    north_south = "South" if y < 5120 else "Midlands" if y < 10240 else "North"
    return f"{north_south} {east_west}"


def ensure_guild_runtime(guild_id):

    if guild_id not in processed_lines:
        processed_lines[guild_id] = OrderedDict()
    elif not isinstance(processed_lines[guild_id], OrderedDict):
        # Migrate any legacy `set` cache to OrderedDict on the fly.
        legacy = processed_lines[guild_id]
        processed_lines[guild_id] = OrderedDict((str(item), None) for item in legacy)

    if guild_id not in online_players:
        online_players[guild_id] = set()

    if guild_id not in player_last_coords:
        player_last_coords[guild_id] = {}

    if guild_id not in player_online_times:
        player_online_times[guild_id] = {}

    if guild_id not in territory_heat:
        territory_heat[guild_id] = {}


def increase_heat(guild_id, zone, mode="pvp", coords=None):

    ensure_guild_runtime(guild_id)

    if mode == "pvp":
        territory_heat[guild_id][zone] = (
            territory_heat[guild_id].get(zone, 0) + 1
        )

    modes = territory_heat[guild_id].setdefault("__modes__", {})
    mode_counts = modes.setdefault(mode, {})
    mode_counts[zone] = mode_counts.get(zone, 0) + 1

    if coords:
        points = territory_heat[guild_id].setdefault("__points__", {})
        mode_points = points.setdefault(mode, [])
        plotted = map_coords_to_pixel(coords, guild_id)
        if plotted:
            mode_points.append(plotted)
            points[mode] = mode_points[-300:]

    save_heatmap()


def remember_player_location_from_adm(guild_id, line):
    player_name = extract_player_name(line)
    coords = extract_adm_coords(line)

    if not coords or not player_name or player_name == "Unknown":
        return

    ensure_guild_runtime(guild_id)
    player_last_coords[str(guild_id)][player_name] = {
        "coords": coords,
        "seen": str(datetime.now(UTC)),
    }


def classify_event(line):

    lower = line.lower()
    zombie_terms = ["infected", "zombie", "zmb"]
    animal_terms = [
        "animal_",
        "deer",
        "stag",
        "doe",
        "boar",
        "pig",
        "cow",
        "sheep",
        "goat",
        "wolf",
        "bear",
        "chicken",
        "hen",
        "rooster",
        "fox",
        "hare"
    ]
    unconscious_terms = [
        "unconscious",
        "unconsciousness",
        "knocked out",
        "passed out"
    ]

    if "disconnected" in lower:
        return "disconnect"

    # Only treat completed joins as connections. "connecting" is ignored
    # to avoid duplicate Discord feed messages for the same player.
    if re.search(r"\bconnected\b", lower) and "connecting" not in lower:
        return "connect"

    if "territoryflag" in lower and "has raised" in lower:
        return "flag_raise"

    if "territoryflag" in lower and "has lowered" in lower:
        return "flag_lower"

    if "performed emotesuicide" in lower or "committed suicide" in lower:
        return "suicide"

    if "is choosing to respawn" in lower:
        return "respawn"

    if "bled out" in lower or "bleed sources" in lower:
        return "bleedout"

    if re.search(r"\bpacked\b", lower):
        return "packed"

    if re.search(r"\bplaced\b", lower):
        return "placed"

    if any(term in lower for term in unconscious_terms):
        return "unconscious"

    if any(term in lower for term in animal_terms) and any(word in lower for word in ["killed", "dead", "died"]):
        return "animal_kill"

    if any(term in lower for term in zombie_terms):

        if any(word in lower for word in ["killed", "died", "dead"]):
            return "zombie_kill"

        if any(word in lower for word in ["hit", "attacked", "damage", "wound"]):
            return "zombie_hit"

    if 'hit by player "' in lower and ("(dead)" in lower or "[hp: 0]" in lower):
        return "kill"

    # Vehicle deaths/hits — DayZ ADM lines look like:
    #   Player "X" (DEAD) ... hit by Transport_PickupTruck for 250 damage
    #   Player "X" (DEAD) ... hit by Vehicle CivilianSedan from ...
    if "(dead)" in lower and (" by transport" in lower or " by vehicle" in lower or "by transporthit" in lower):
        return "vehicle_kill"

    if "hit by" in lower:
        return "cut"

    if "killed by" in lower and 'killed by player "' not in lower:
        if any(term in lower for term in zombie_terms):
            return "zombie_kill"
        return "cut"

    if "killed" in lower:
        return "kill"

    if "built" in lower or "mounted" in lower or "unmounted" in lower:
        return "build"

    if "destroyed" in lower or "dismantled" in lower:
        return "raid"

    return None

# =========================================================
# MULTI GUILD API SEARCH
# =========================================================

ADM_LOG_NAME_PATTERN = re.compile(
    r"^DayZServer_[A-Z0-9]+_x64_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$",
    re.IGNORECASE
)


def nitrado_adm_search_paths(config):
    nitrado_user = config.get("nitrado_user")
    return [
        f"/games/{nitrado_user}/noftp/dayzxb/config/",
        f"/games/{nitrado_user}/noftp/dayzxb/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/",
        f"/games/{nitrado_user}/noftp/dayzxb/storage_1/",
        f"/games/{nitrado_user}/noftp/dayzxb/profiles/",
        f"/games/{nitrado_user}/noftp/dayzxb/logs/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/dayzOffline.chernarusplus/",
        f"/games/{nitrado_user}/noftp/dayzxb/mpmissions/dayzOffline.enoch/",
        f"/games/{nitrado_user}/noftp/"
    ]


def parse_nitrado_datetime(value):
    if not value:
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, UTC)
        except Exception:
            return None

    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def adm_log_datetime(entry):
    name_match = ADM_LOG_NAME_PATTERN.match(entry.get("name", ""))
    if name_match:
        time_text = f"{name_match.group(1)} {name_match.group(2).replace('-', ':')}"
        try:
            return datetime.strptime(time_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except Exception:
            pass

    return parse_nitrado_datetime(entry.get("modified_at"))


def adm_debug_enabled():
    return str(os.getenv("WANDERING_ADM_DEBUG", "")).strip().lower() in {"1", "true", "yes", "on"}


def adm_debug_log(message):
    if adm_debug_enabled():
        print(message)


def list_adm_logs(config, lookback_hours=None):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    cutoff = None
    if lookback_hours:
        cutoff = datetime.now(UTC) - timedelta(hours=int(lookback_hours))

    matching_logs = {}

    for search_path in nitrado_adm_search_paths(config):

        try:

            url = (
                f"https://api.nitrado.net/services/"
                f"{service_id}/gameservers/file_server/list"
            )

            params = {
                "dir": search_path,
                "search": "*DayZServer*"
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=20
            )

            adm_debug_log(f"[PING STATUS] {response.status_code}")

            if response.status_code != 200:
                continue

            data = response.json()

            entries = (
                data
                .get("data", {})
                .get("entries", [])
            )

            adm_debug_log(f"[SEARCH PATH] {search_path}")

            for entry in entries:
                if not ADM_LOG_NAME_PATTERN.match(entry.get("name", "")):
                    continue

                adm_debug_log(f"FOUND FILE: {entry.get('name')}")

                entry_time = adm_log_datetime(entry)
                if cutoff and entry_time and entry_time < cutoff:
                    continue

                path = entry.get("path")
                if path:
                    entry["_adm_datetime"] = entry_time.isoformat() if entry_time else ""
                    matching_logs[path] = entry

        except Exception as error:
            print(error)

    logs = list(matching_logs.values())
    logs.sort(key=lambda item: item.get("_adm_datetime") or item.get("modified_at", ""), reverse=True)
    return logs


def ping_latest_adm_log(config):
    matching_logs = list_adm_logs(config)

    if not matching_logs:
        adm_debug_log("NO MATCHING ADM FILES")
        return None

    latest = matching_logs[0]
    adm_debug_log(f"LATEST ADM FOUND: {latest.get('path')}")
    return latest

# =========================================================
# LIVE DASHBOARD SETTINGS
# =========================================================

ONLINE_UPDATE_MINUTES = 30
LEADERBOARD_UPDATE_MINUTES = 60
HEATMAP_UPDATE_MINUTES = 60

last_online_message_ids = {}
last_leaderboard_message_ids = {}
last_heatmap_message_ids = {}
last_pve_heatmap_message_ids = {}
last_restart_message_ids = {}
last_restart_countdown_message_ids = {}

CUSTOM_FEED_TYPES = [
    "text",
    "restart",
    "basedamage",
    "serverstatus",
    "heatmap"
]

# =========================================================
# CLICKABLE MAP LINKS
# =========================================================

def izurvive_map_path(guild_id=None):
    if guild_id is None:
        return ""

    map_key = server_map_key(guild_id)

    if map_key == "livonia":
        return "livonia/"

    if map_key == "sakhal":
        return "sakhal/"

    return ""


def build_izurvive_link(coords, guild_id=None):

    try:

        split_coords = coords.split(",")

        x = split_coords[0].strip()
        y = split_coords[1].strip()
        map_path = izurvive_map_path(guild_id)

        return f"https://dayz.ginfo.gg/{map_path}#location={x};{y}"

    except:
        return None


ZONE_POINTS_BY_MAP = {
    "chernarus": {
        "NWAF": (330, 120), "Tisy": (220, 70), "Zelenogorsk": (170, 220),
        "Chernogorsk": (120, 290), "Elektrozavodsk": (360, 300), "Vybor": (210, 140),
        "Berezino": (430, 150), "Severograd": (360, 95),
        "South West": (95, 305), "South Central": (255, 305), "South East": (420, 305),
        "Midlands West": (95, 195), "Midlands Central": (255, 195), "Midlands East": (420, 195),
        "North West": (95, 85), "North Central": (255, 85), "North East": (420, 85)
    },
    "livonia": {
        "South West": (95, 305), "South Central": (255, 305), "South East": (420, 305),
        "Midlands West": (95, 195), "Midlands Central": (255, 195), "Midlands East": (420, 195),
        "North West": (95, 85), "North Central": (255, 85), "North East": (420, 85)
    },
    "sakhal": {
        "South West": (95, 305), "South Central": (255, 305), "South East": (420, 305),
        "Midlands West": (95, 195), "Midlands Central": (255, 195), "Midlands East": (420, 195),
        "North West": (95, 85), "North Central": (255, 85), "North East": (420, 85)
    }
}


def configured_heatmap_image_source(guild_id, map_key):
    config = guild_configs.get(str(guild_id), {})
    images = config.get("heatmap_images", {})
    return images.get(map_key) or images.get("default") or DEFAULT_MAP_IMAGE_SOURCES.get(map_key)


def normalize_map_image_key(map_name):
    wanted = normalize_discord_name(map_name)

    if wanted in ["cherno", "chernarusplus", "chernarus"]:
        return "chernarus"

    if wanted in ["livonia", "enoch"]:
        return "livonia"

    if wanted in ["sakhal", "sakhalplus"]:
        return "sakhal"

    if wanted == "default":
        return "default"

    return None


def heatmap_status_key(guild_id, mode):
    return f"{guild_id}:{mode or 'all'}"


def set_heatmap_render_status(guild_id, mode, message):
    last_heatmap_render_status[heatmap_status_key(str(guild_id), mode)] = message


def heatmap_render_status(guild_id, mode):
    return last_heatmap_render_status.get(
        heatmap_status_key(str(guild_id), mode),
        "No heatmap render has happened since the bot started."
    )


def pillow_install_status():
    try:
        import PIL
        return True, f"Pillow installed: `{getattr(PIL, '__version__', 'unknown')}`"
    except Exception as error:
        return False, f"Pillow is missing: `{error}`. Add `Pillow` to `requirements.txt` and redeploy Railway."


def map_image_source_status(guild_id, map_key):
    source = configured_heatmap_image_source(guild_id, map_key)

    if not source:
        return None, f"No map image configured for `{map_key}`."

    if str(source).startswith(("http://", "https://")):
        return source, f"Using URL image for `{map_key}`."

    if os.path.exists(source):
        return source, f"Using local image for `{map_key}`: `{source}`"

    return source, f"Configured image is missing from this bot process: `{source}`"


def generate_real_map_heatmap_image(guild_id, mode, map_key, width=512, height=384):
    source, source_status = map_image_source_status(guild_id, map_key)
    if not source:
        set_heatmap_render_status(guild_id, mode, source_status)
        return None

    if not str(source).startswith(("http://", "https://")) and not os.path.exists(source):
        set_heatmap_render_status(guild_id, mode, source_status)
        return None

    try:
        from PIL import Image, ImageDraw
    except Exception as error:
        set_heatmap_render_status(guild_id, mode, f"Pillow is not installed or could not load: {error}")
        return None

    try:
        if str(source).startswith(("http://", "https://")):
            response = requests.get(source, timeout=20)
            if response.status_code != 200:
                set_heatmap_render_status(guild_id, mode, f"Map image download failed with status `{response.status_code}`.")
                return None
            image_file = tempfile.NamedTemporaryFile(delete=False, suffix=".map")
            image_file.write(response.content)
            image_file.close()
            source_path = image_file.name
        else:
            source_path = source

        base = Image.open(source_path).convert("RGBA").resize((width, height))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        def draw_heat(cx, cy, radius, color):
            for current_radius in range(radius, 4, -6):
                alpha = max(20, int(color[3] * (current_radius / radius)))
                draw.ellipse(
                    (cx - current_radius, cy - current_radius, cx + current_radius, cy + current_radius),
                    fill=(color[0], color[1], color[2], alpha)
                )

        for px, py in heat_points_for_mode(guild_id, mode):
            draw_heat(px, py, 34, (255, 55, 0, 80))
            draw_heat(px, py, 14, (255, 215, 0, 160))
            draw.line((px - 5, py, px + 5, py), fill=(255, 255, 255, 220), width=2)
            draw.line((px, py - 5, px, py + 5), fill=(255, 255, 255, 220), width=2)

        zone_counts = heat_counts_for_mode(guild_id, mode)
        max_count = max(zone_counts.values()) if zone_counts else 1
        zone_points = ZONE_POINTS_BY_MAP.get(map_key, ZONE_POINTS_BY_MAP["chernarus"])
        for zone, count in zone_counts.items():
            if zone not in zone_points:
                continue
            x, y = zone_points[zone]
            intensity = max(0.2, min(1.0, count / max_count))
            draw_heat(x, y, 54, (255, 65, 0, int(90 * intensity)))

        final = Image.alpha_composite(base, overlay)
        fd, path = tempfile.mkstemp(prefix=f"heat_{guild_id}_real_", suffix=".png")
        os.close(fd)
        final.save(path, "PNG")
        set_heatmap_render_status(guild_id, mode, f"Real map image rendered. {source_status}")

        if str(source).startswith(("http://", "https://")):
            try:
                os.remove(source_path)
            except Exception:
                pass

        return path

    except Exception as error:
        print(f"REAL HEATMAP ERROR {guild_id}: {error}")
        set_heatmap_render_status(guild_id, mode, f"Real map render failed: {error}")
        return None


def generate_guild_heatmap_image(guild_id: str, mode=None):
    import math
    import struct
    import zlib

    width = 512
    height = 384
    guild_id = str(guild_id)
    mode = mode or guild_heatmap_mode(guild_id)
    map_key = server_map_key(guild_id)
    map_title = {"livonia": "Livonia", "sakhal": "Sakhal"}.get(map_key, "Chernarus")
    real_map_path = generate_real_map_heatmap_image(guild_id, mode, map_key, width, height)
    if real_map_path:
        return real_map_path

    current_status = heatmap_render_status(guild_id, mode)
    set_heatmap_render_status(
        guild_id,
        mode,
        f"Using fallback drawn map because the real image was unavailable. {current_status}"
    )

    pixels = [
        [(36, 58, 49, 255) for _ in range(width)]
        for _ in range(height)
    ]

    def blend_pixel(px, py, color):
        if px < 0 or px >= width or py < 0 or py >= height:
            return

        sr, sg, sb, sa = color
        dr, dg, db, da = pixels[py][px]
        alpha = sa / 255
        inv_alpha = 1 - alpha
        pixels[py][px] = (
            int(sr * alpha + dr * inv_alpha),
            int(sg * alpha + dg * inv_alpha),
            int(sb * alpha + db * inv_alpha),
            da,
        )

    def draw_line(x1, y1, x2, y2, color, thickness=1):
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        for step in range(steps + 1):
            t = step / steps
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)
            for oy in range(-thickness, thickness + 1):
                for ox in range(-thickness, thickness + 1):
                    blend_pixel(x + ox, y + oy, color)

    def draw_heat_circle(cx, cy, radius, color):
        radius_sq = radius * radius

        for py in range(cy - radius, cy + radius + 1):
            for px in range(cx - radius, cx + radius + 1):
                dx = px - cx
                dy = py - cy
                dist_sq = dx * dx + dy * dy

                if dist_sq > radius_sq:
                    continue

                distance = math.sqrt(dist_sq)
                fade = max(0.0, 1.0 - (distance / radius))
                alpha = int(color[3] * fade)
                blend_pixel(px, py, (color[0], color[1], color[2], alpha))

    def draw_cross(cx, cy):
        for offset in range(-5, 6):
            blend_pixel(cx + offset, cy, (255, 255, 255, 230))
            blend_pixel(cx, cy + offset, (255, 255, 255, 230))

    def draw_label_bar():
        for y in range(0, 28):
            for x in range(width):
                blend_pixel(x, y, (15, 22, 20, 180))

    def draw_map_background():
        # Map-aware terrain base. Coordinates scale to the configured DayZ world:
        # Chernarus is 15360x15360, Livonia/Enoch is 12800x12800.
        for x in range(0, width, 64):
            for y in range(height):
                blend_pixel(x, y, (96, 119, 103, 65))

        for y in range(0, height, 48):
            for x in range(width):
                blend_pixel(x, y, (96, 119, 103, 65))

        if map_key == "livonia":
            for x in range(width):
                river_y = int(148 + math.sin(x / 35) * 16 + math.sin(x / 13) * 4)
                for y in range(river_y - 5, river_y + 6):
                    blend_pixel(x, y, (44, 85, 108, 210))

            for x in range(45, width - 35):
                south_y = int(302 + math.sin(x / 29) * 10)
                for y in range(south_y, height):
                    blend_pixel(x, y, (42, 70, 45, 120))

            roads = [
                ((44, 78), (170, 124), (296, 150), (464, 116)),
                ((58, 246), (170, 206), (280, 215), (440, 270)),
                ((262, 40), (252, 144), (270, 250), (250, 350)),
            ]
        else:
            for x in range(32, width - 18):
                coast_y = int(300 + math.sin(x / 24) * 18 + math.sin(x / 9) * 5)
                for y in range(coast_y, height):
                    blend_pixel(x, y, (36, 75, 100, 225))

            for y in range(70, height - 55):
                coast_x = int(452 + math.sin(y / 24) * 22)
                for x in range(coast_x, width):
                    blend_pixel(x, y, (36, 75, 100, 190))

            roads = [
                ((62, 290), (156, 244), (245, 196), (354, 151), (453, 110)),
                ((110, 92), (200, 119), (300, 145), (420, 158)),
                ((163, 318), (205, 236), (222, 152), (218, 65)),
                ((348, 320), (340, 250), (363, 180), (400, 118)),
            ]

        for road in roads:
            for idx in range(len(road) - 1):
                x1, y1 = road[idx]
                x2, y2 = road[idx + 1]
                draw_line(x1, y1, x2, y2, (176, 153, 103, 150), 1)

        draw_label_bar()

    def png_chunk(chunk_type, data):
        chunk = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + chunk
            + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        )

    draw_map_background()
    zone_counts = heat_counts_for_mode(guild_id, mode)
    max_count = max(zone_counts.values()) if zone_counts else 1

    for point in heat_points_for_mode(guild_id, mode):
        px, py = point
        draw_heat_circle(px, py, 36, (255, 60, 0, 90))
        draw_heat_circle(px, py, 18, (255, 210, 0, 190))
        draw_cross(px, py)

    zone_points = ZONE_POINTS_BY_MAP.get(map_key, ZONE_POINTS_BY_MAP["chernarus"])
    for zone, count in zone_counts.items():
        if zone not in zone_points:
            continue

        x, y = zone_points[zone]
        intensity = max(0.2, min(1.0, count / max_count))
        draw_heat_circle(x, y, 70, (255, 45, 0, int(45 * intensity)))
        draw_heat_circle(x, y, 48, (255, 80, 0, int(90 * intensity)))
        draw_heat_circle(x, y, 25, (255, 180, 0, int(170 * intensity)))
        draw_cross(x, y)

    # Tiny title ticks so saved images show which server map was used without needing fonts.
    for idx, char in enumerate(f"{map_title} {mode}"[:28]):
        marker = ord(char) % 12
        x = 12 + idx * 10
        for y in range(8, 20):
            if (y + marker) % 5 == 0:
                for ox in range(0, 6):
                    blend_pixel(x + ox, y, (230, 235, 215, 180))

    raw = bytearray()

    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend([r, g, b, a])

    png_data = b"".join([
        b"\x89PNG\r\n\x1a\n",
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
        png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9)),
        png_chunk(b"IEND", b""),
    ])

    fd, path = tempfile.mkstemp(prefix=f"heat_{guild_id}_", suffix=".png")
    os.close(fd)

    with open(path, "wb") as f:
        f.write(png_data)

    return path


def generate_live_player_map_image(guild_id: str):
    guild_id = str(guild_id)
    map_key = server_map_key(guild_id)
    source = configured_heatmap_image_source(guild_id, map_key)

    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None, "Pillow is not installed, so map images cannot be rendered. Add `Pillow` to `requirements.txt` in the Railway deploy root and redeploy."

    if not source:
        return None, f"No map image configured for `{map_key}`."

    if not str(source).startswith(("http://", "https://")) and not os.path.exists(source):
        return None, f"Map image path does not exist: `{source}`"

    downloaded_path = None

    try:
        source_status_note = None
        if str(source).startswith(("http://", "https://")):
            response = requests.get(source, timeout=20)
            if response.status_code != 200:
                source_status_note = f"Real map image download failed with status {response.status_code}; using fallback map."
                source_path = None
            else:
                image_file = tempfile.NamedTemporaryFile(delete=False, suffix=".map")
                image_file.write(response.content)
                image_file.close()
                downloaded_path = image_file.name
                source_path = downloaded_path
        else:
            source_path = source

        width = 1200
        height = 900
        if source_path:
            base = Image.open(source_path).convert("RGBA").resize((width, height))
        else:
            base = Image.new("RGBA", (width, height), (39, 61, 49, 255))
            fallback_draw = ImageDraw.Draw(base)
            for x in range(0, width, 120):
                fallback_draw.line((x, 0, x, height), fill=(90, 118, 96, 95), width=2)
            for y in range(0, height, 90):
                fallback_draw.line((0, y, width, y), fill=(90, 118, 96, 95), width=2)
            if map_key == "livonia":
                fallback_draw.line((0, 350, 220, 310, 480, 365, 760, 330, 1200, 380), fill=(44, 86, 112, 210), width=18)
            else:
                fallback_draw.polygon([(0, 710), (240, 675), (500, 725), (740, 690), (1200, 735), (1200, 900), (0, 900)], fill=(36, 76, 104, 230))
                fallback_draw.polygon([(1080, 120), (1200, 70), (1200, 720), (1115, 680), (1060, 430)], fill=(36, 76, 104, 190))
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        try:
            font = ImageFont.truetype("arial.ttf", 22)
            small_font = ImageFont.truetype("arial.ttf", 16)
        except Exception:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        online = sorted(online_players.get(guild_id, set()))
        locations = player_last_coords.get(guild_id, {})
        plotted_players = []

        for player in online:
            coord_record = locations.get(player)
            coords = coord_record.get("coords") if isinstance(coord_record, dict) else None
            if not coords:
                continue

            point = map_coords_to_pixel(coords, guild_id, width, height)
            if not point:
                continue

            plotted_players.append((player, coords, point))

        draw.rectangle((0, 0, width, 68), fill=(10, 14, 16, 205))
        map_title = {"livonia": "Livonia", "sakhal": "Sakhal"}.get(map_key, "Chernarus")
        draw.text((24, 14), f"Live Survivor Map - {map_title}", fill=(245, 248, 238, 255), font=font)
        draw.text(
            (24, 42),
            f"{len(plotted_players)} plotted / {len(online)} online - latest known ADM positions",
            fill=(203, 216, 196, 255),
            font=small_font
        )
        if source_status_note:
            draw.text((760, 42), source_status_note[:52], fill=(255, 210, 120, 255), font=small_font)

        for idx, (player, coords, point) in enumerate(plotted_players, start=1):
            px, py = point
            label = f"{idx}. {player[:24]}"
            label_width = max(120, len(label) * 10)

            draw.ellipse((px - 14, py - 14, px + 14, py + 14), fill=(255, 45, 45, 235), outline=(255, 255, 255, 255), width=3)
            draw.ellipse((px - 4, py - 4, px + 4, py + 4), fill=(255, 255, 255, 255))

            label_x = min(max(8, px + 18), width - label_width - 12)
            label_y = min(max(76, py - 18), height - 34)
            draw.rounded_rectangle(
                (label_x - 6, label_y - 4, label_x + label_width, label_y + 24),
                radius=5,
                fill=(12, 18, 18, 210),
                outline=(255, 255, 255, 120)
            )
            draw.text((label_x, label_y), label, fill=(255, 255, 255, 255), font=small_font)

        final = Image.alpha_composite(base, overlay)
        fd, path = tempfile.mkstemp(prefix=f"live_map_{guild_id}_", suffix=".png")
        os.close(fd)
        final.save(path, "PNG")

        return path, None

    except Exception as error:
        return None, str(error)

    finally:
        if downloaded_path:
            try:
                os.remove(downloaded_path)
            except Exception:
                pass


def extract_adm_log_time(line):
    match = re.match(r"^(\d{1,2}:\d{2}:\d{2})", str(line).strip())
    return match.group(1) if match else None


def build_pvp_kill_embed(kill_details, line=None, history=False, guild_id=None, event_time=None):
    killer = kill_details["killer"]
    victim = kill_details["victim"]
    weapon = kill_details.get("weapon", "Unknown")
    distance = float(kill_details.get("distance", 0) or 0)
    coords = kill_details.get("coords")

    embed = discord.Embed(
        title="HISTORICAL PLAYER KILL" if history else "PLAYER KILL",
        color=0x992D22
    )
    embed.add_field(name="Killer", value=killer, inline=True)
    embed.add_field(name="Victim", value=victim, inline=True)

    if distance > 0:
        embed.add_field(name="Distance", value=f"{distance}m", inline=True)

    embed.add_field(name="Weapon", value=weapon, inline=False)

    if kill_details.get("ammo"):
        embed.add_field(name="Ammo", value=kill_details["ammo"], inline=True)

    log_time = extract_adm_log_time(line) if line else None
    if history and log_time:
        embed.add_field(name="ADM Log Time", value=log_time, inline=True)

    if coords:
        map_link = build_izurvive_link(coords, guild_id)
        if map_link:
            embed.add_field(name="Kill Location", value=f"[Open Map](<{map_link}>)", inline=False)

    embed.set_thumbnail(url=BOT_IMAGE)
    footer = "Wandering Bot Alpha - PvP History Backfill" if history else "Wandering Bot Alpha - PvP Intelligence"
    embed.set_footer(text=footer)
    # Anchor the embed to the in-game event time so Discord shows "when
    # the kill actually happened" rather than "when the bot processed it".
    if event_time is None and line:
        event_time = extract_adm_event_time(line)
    embed.timestamp = event_time or datetime.now(UTC)
    return embed


def build_longshot_embed(kill_details, is_new_record=False, history=False, guild_id=None, event_time=None):
    killer = kill_details["killer"]
    victim = kill_details["victim"]
    weapon = kill_details.get("weapon", "Unknown")
    distance = float(kill_details.get("distance", 0) or 0)
    coords = kill_details.get("coords")

    if history:
        title = "HISTORICAL SERVER LONGSHOT RECORD" if is_new_record else "HISTORICAL LONGSHOT"
    else:
        title = "NEW SERVER LONGSHOT RECORD" if is_new_record else "LONGSHOT CONFIRMED"

    embed = discord.Embed(
        title=title,
        description=f"{killer} dropped {victim} from {distance}m.",
        color=0xF1C40F
    )
    embed.add_field(name="Distance", value=f"{distance}m", inline=True)
    embed.add_field(name="Weapon", value=weapon, inline=True)
    embed.add_field(name="Victim", value=victim, inline=True)

    if coords:
        map_link = build_izurvive_link(coords, guild_id)
        if map_link:
            embed.add_field(name="Kill Location", value=f"[Open Map](<{map_link}>)", inline=False)

    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text=f"Wandering Bot Alpha - Longshot Tracking - Threshold {LONGSHOT_ANNOUNCE_METERS}m")
    embed.timestamp = event_time or datetime.now(UTC)
    return embed


async def send_pvp_kill_feed_message(guild_id, config, line, history=False):
    kill_details = extract_pvp_kill_details(line)
    if not kill_details:
        return False, False

    channels = config.get("channels", {})
    killfeed_channel = bot.get_channel(channels.get("killfeed"))
    longshot_channel = bot.get_channel(channels.get("longshots"))

    if killfeed_channel:
        await killfeed_channel.send(embed=style_embed(build_pvp_kill_embed(kill_details, line, history, guild_id)))

    distance = float(kill_details.get("distance", 0) or 0)
    guild_longshot = longshot_records.get(str(guild_id), {
        "killer": "None",
        "distance": 0,
        "weapon": "Unknown"
    })

    is_new_record = distance > float(guild_longshot.get("distance", 0) or 0)
    is_longshot = distance >= LONGSHOT_ANNOUNCE_METERS

    if is_new_record:
        longshot_records[str(guild_id)] = {
            "killer": kill_details["killer"],
            "victim": kill_details["victim"],
            "distance": distance,
            "weapon": kill_details.get("weapon", "Unknown")
        }

    if longshot_channel and (is_longshot or is_new_record):
        await longshot_channel.send(embed=style_embed(build_longshot_embed(kill_details, is_new_record, history, guild_id)))

    return True, bool(is_longshot or is_new_record)
# =========================================================
# AUTO GUILD SETUP
# =========================================================

@bot.event
async def on_guild_channel_delete(channel):
    guild = getattr(channel, "guild", None)
    if not guild or not isinstance(channel, discord.TextChannel):
        return

    key = mark_deleted_bot_channel(guild.id, channel.id)
    if key:
        print(f"CHANNEL DISABLED BY DELETE {guild.id}: {key}")


@bot.event
async def on_guild_join(guild):

    guild_id = str(guild.id)

    if guild_id in guild_configs:
        return

    if is_showcase_guild(guild_id):
        guild_configs[guild_id] = new_guild_config(guild)
        guild_configs[guild_id]["is_showcase_guild"] = True
        guild_configs[guild_id]["showcase_mode"] = True
        guild_configs[guild_id]["disabled_channels"] = list(DEFAULT_CHANNEL_NAMES.keys())
        save_guild_configs()
        return

    category = await guild.create_category("🟩🟩🟩┃WANDERING HQ┃🟩🟩🟩")
    live_category = await guild.create_category("🟥🟧🟨┃LIVE SERVER FEEDS┃🟨🟧🟥")
    info_category = await guild.create_category("🟦🟩🟦┃SERVER INFO┃🟦🟩🟦")
    community_category = await guild.create_category("🟪🟩🟪┃SURVIVOR COMMS┃🟪🟩🟪")
    staff_category = await guild.create_category("🛡️🟥🛡️┃STAFF OPS┃🛡️🟥🛡️")
    economy_category = await guild.create_category("💰🟨💰┃ECONOMY┃💰🟨💰")
    faction_category = await guild.create_category("🏴🟩🏴┃FACTIONS┃🏴🟩🏴")
    support_category = await guild.create_category("❓🟦❓┃HELP & SUPPORT┃❓🟦❓")
    pve_category = await guild.create_category("🦌🌲🧭┃PVE EXPEDITIONS┃🧭🌲🦌")

    async def make_channel(name, *, cat=None):

        return await guild.create_text_channel(
            name,
            category=cat or category
        )

    staff_overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False)
    }
    for role in guild.roles:
        if role.permissions.administrator or role.name in DEFAULT_ADMIN_ROLES:
            staff_overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    killfeed = await make_channel("🔥🔥・killfeed・🔥🔥", cat=live_category)
    raids = await make_channel("🚨🏴・raids・🏴🚨", cat=live_category)
    builds = await make_channel("🔨🧱・building・🧱🔨", cat=live_category)
    connections = await make_channel("🟢✅・connected・✅🟢", cat=live_category)
    disconnects = await make_channel("🔴⛔・disconnects・⛔🔴", cat=live_category)
    zombie_feed = await make_channel("🧟🧟・zombie-feed・🧟🧟", cat=live_category)
    unconscious_feed = await make_channel("🩹⚠️・unconscious-feed・⚠️🩹", cat=live_category)
    cuts_feed = await guild.create_text_channel("🩸🩹・cuts-feed・🩹🩸", category=live_category, overwrites=staff_overwrites)
    suicide_feed = await guild.create_text_channel("💀🧠・suicide-feed・🧠💀", category=live_category, overwrites=staff_overwrites)
    flag_feed = await guild.create_text_channel("🚩🏴・flag-feed・🏴🚩", category=live_category, overwrites=staff_overwrites)
    placed_feed = await guild.create_text_channel("📦🧰・placed-feed・🧰📦", category=live_category, overwrites=staff_overwrites)
    pvp_intel = await make_channel("⚔️📡・pvp-intel・📡⚔️", cat=live_category)

    online = await make_channel("✅🎮・online-survivors・🎮✅", cat=info_category)
    leaderboards = await make_channel("🏆📊・leaderboards・📊🏆", cat=info_category)
    heatmap_channel = await make_channel("🔥🗺️・heatmap・🗺️🔥", cat=info_category)
    longshot_channel = await make_channel("🎯🏹・longshots・🏹🎯", cat=info_category)
    restart_alerts = await make_channel("📢⏰・restart-alerts・⏰📢", cat=info_category)
    bot_updates = await make_channel("📢✨・bot-updates・✨📢", cat=info_category)

    welcome_channel = await make_channel("👋🟩・welcome・🟩👋", cat=community_category)
    public_shame = await make_channel("🚫📣・wandering-in-shame・📣🚫", cat=community_category)
    general_chat = await make_channel("💬🌲・survivor-chat・🌲💬", cat=community_category)
    ai_channel = await make_channel("🧠📻・survivor-ai・📻🧠", cat=community_category)
    clips_channel = await make_channel("🎬⭐・dayz-clips・⭐🎬", cat=community_category)

    factions_chat = await make_channel("🏴⚔️・factions-chat・⚔️🏴", cat=faction_category)
    faction_list = await make_channel("📜🏴・faction-list・🏴📜", cat=faction_category)
    faction_tickets = await make_channel("🎫🏴・faction-tickets・🏴🎫", cat=faction_category)
    faction_staff = await make_channel("🛡️🏴・faction-staff・🏴🛡️", cat=staff_category)

    help_channel = await make_channel("❓📘・help-desk・📘❓", cat=support_category)
    economy_channel = await make_channel("💰🛒・black-market・🛒💰", cat=economy_category)
    admin_logs = await make_channel("🛡️📕・admin-logs・📕🛡️", cat=staff_category)
    cheat_checks = await guild.create_text_channel("🕵️🚫・pc-cheat-check・🚫🕵️", category=staff_category, overwrites=staff_overwrites)
    command_logs = await make_channel("📜🛡️・command-logs・🛡️📜", cat=staff_category)
    purchase_logs = await make_channel("💳📦・purchase-logs・📦💳", cat=economy_category)
    vehicle_rentals = await make_channel("🚗💰・vehicle-rentals・💰🚗", cat=economy_category)
    rental_logs = await make_channel("🛻📒・rental-logs・📒🛻", cat=economy_category)
    pve_quests = await make_channel("🧭📜・pve-quests・📜🧭", cat=pve_category)
    pve_hunting = await make_channel("🦌🏹・pve-hunting・🏹🦌", cat=pve_category)
    pve_collection = await make_channel("🎒🥫・pve-collection・🥫🎒", cat=pve_category)
    pve_fishing = await make_channel("🎣🐟・pve-fishing・🐟🎣", cat=pve_category)
    pve_crafting = await make_channel("🪓🛠️・pve-crafting・🛠️🪓", cat=pve_category)
    pve_expeditions = await make_channel("🗺️⛺・pve-expeditions・⛺🗺️", cat=pve_category)
    pve_info = await make_channel("📘🌿・pve-info・🌿📘", cat=pve_category)
    pve_help = await make_channel("❔🌿・pve-help・🌿❔", cat=pve_category)
    pve_heatmap = await make_channel("🦌🗺️・pve-heatmap・🗺️🦌", cat=pve_category)
    owner_overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.owner: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    company_announcements = await guild.create_text_channel(
        "📢・wandering-company-announcements・📢",
        category=staff_category,
        overwrites=owner_overwrites
    )

    guild_configs[guild_id] = {
        "guild_name": guild.name,
        "guild_owner": str(guild.owner),
        "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
        "nitrado_token": "",
        "service_id": "",
        "nitrado_user": "",
        "ftp_user": "",
        "ftp_password": "",
        "ftp_host": "",
        "channels": {
            "killfeed": killfeed.id,
            "raids": raids.id,
            "building": builds.id,
            "connections": connections.id,
            "disconnects": disconnects.id,
            "online": online.id,
            "leaderboards": leaderboards.id,
            "heatmap": heatmap_channel.id,
            "longshots": longshot_channel.id,
            "restart_alerts": restart_alerts.id,
            "bot_updates": bot_updates.id,
            "welcome": welcome_channel.id,
            "public_shame": public_shame.id,
            "general_chat": general_chat.id,
            "factions_chat": factions_chat.id,
            "faction_list": faction_list.id,
            "help_channel": help_channel.id,
            "clips_channel": clips_channel.id,
            "economy": economy_channel.id,
            "ai_chat": ai_channel.id,
            "admin_logs": admin_logs.id,
            "cheat_checks": cheat_checks.id,
            "command_logs": command_logs.id,
            "purchase_logs": purchase_logs.id,
            "vehicle_rentals": vehicle_rentals.id,
            "rental_logs": rental_logs.id,
            "pve_quests": pve_quests.id,
            "pve_hunting": pve_hunting.id,
            "pve_collection": pve_collection.id,
            "pve_fishing": pve_fishing.id,
            "pve_crafting": pve_crafting.id,
            "pve_expeditions": pve_expeditions.id,
            "pve_info": pve_info.id,
            "pve_heatmap": pve_heatmap.id,
            "faction_tickets": faction_tickets.id,
            "faction_staff": faction_staff.id,
            "zombie_feed": zombie_feed.id,
            "unconscious_feed": unconscious_feed.id,
            "cuts_feed": cuts_feed.id,
            "suicide_feed": suicide_feed.id,
            "flag_feed": flag_feed.id,
            "placed_feed": placed_feed.id,
            "pvp_intel": pvp_intel.id,
            "pve_help": pve_help.id,
            "company_announcements": company_announcements.id
        }
    }

    try:
        await send_owner_notification(
            "➕ Bot Added to New Server",
            f"Server: **{guild.name}** (`{guild.id}`)\nOwner: **{guild.owner}**"
        )
    except Exception:
        pass

    save_guild_configs()

    try:
        await publish_bot_update_notes(guild, guild_configs[guild_id])
    except Exception as update_error:
        print(f"BOT UPDATE JOIN ERROR {guild_id}: {update_error}")

# =========================================================
# /SETUP COMMAND
# =========================================================

@bot.tree.command(
    name="setup",
    description="Connect your Nitrado server"
)
@app_commands.describe(
    nitrado_token="Your Nitrado API token",
    service_id="Your Nitrado service ID",
    nitrado_user="Example: ni12248929_2",
    ftp_user="Your Nitrado FTP username",
    ftp_password="Your Nitrado FTP password",
    restore_deleted_channels="Recreate bot channels that server owners deleted",
    ftp_host="Optional: your Nitrado FTP host/IP if Railway cannot resolve Nitrado defaults"
)
async def setup_command(
    interaction: discord.Interaction,
    nitrado_token: str,
    service_id: str,
    nitrado_user: str,
    ftp_user: str,
    ftp_password: str,
    restore_deleted_channels: bool = False,
    ftp_host: str = ""
):

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    supplied_ftp_host = normalize_ftp_host(ftp_host)
    if supplied_ftp_host and not looks_like_ftp_host(supplied_ftp_host):
        await interaction.followup.send(
            "That FTP host does not look valid. Use only the host/IP shown by Nitrado, not a full URL or file path.",
            ephemeral=True
        )
        return

    if guild_id not in guild_configs:

        guild_configs[guild_id] = {
            "guild_name": interaction.guild.name,
            "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
            "channels": {}
        }

    def normalize_discord_name(name):
        return re.sub(r"[^a-z0-9]+", "", name.lower())

    category_aliases = {
        "wandering_hq": ["wanderinghq", "wanderingbot", "wanderingbotalpha"],
        "live_feeds": ["liveserverfeeds", "livefeeds", "killfeed", "serverfeeds"],
        "server_info": ["serverinfo", "info", "leaderboards", "dashboard"],
        "survivor_comms": ["survivorcomms", "survivorchat", "generalchat", "community"],
        "staff_ops": ["staffops", "staff", "admin", "adminlogs"],
        "economy": ["economy", "blackmarket", "shop"],
        "factions": ["factions", "faction"],
        "support": ["helpsupport", "helpdesk", "support"],
        "pve": ["pve", "pvemissions", "pveexpeditions", "quests", "hunting", "collection", "fishing"]
    }

    async def ensure_category(category_key, name):
        wanted = normalize_discord_name(name)
        aliases = set(category_aliases.get(category_key, []))
        aliases.add(wanted)

        for existing in interaction.guild.categories:
            normalized = normalize_discord_name(existing.name)
            if normalized in aliases or any(alias in normalized for alias in aliases):
                if existing.name != name:
                    try:
                        await existing.edit(name=name)
                    except Exception:
                        pass
                return existing

        return await interaction.guild.create_category(name)

    category = await ensure_category("wandering_hq", "🟩🟩🟩┃WANDERING HQ┃🟩🟩🟩")
    live_category = await ensure_category("live_feeds", "🟥🟧🟨┃LIVE SERVER FEEDS┃🟨🟧🟥")
    info_category = await ensure_category("server_info", "🟦🟩🟦┃SERVER INFO┃🟦🟩🟦")
    community_category = await ensure_category("survivor_comms", "🟪🟩🟪┃SURVIVOR COMMS┃🟪🟩🟪")
    staff_category = await ensure_category("staff_ops", "🛡️🟥🛡️┃STAFF OPS┃🛡️🟥🛡️")
    economy_category = await ensure_category("economy", "💰🟨💰┃ECONOMY┃💰🟨💰")
    faction_category = await ensure_category("factions", "🏴🟩🏴┃FACTIONS┃🏴🟩🏴")
    support_category = await ensure_category("support", "❓🟦❓┃HELP & SUPPORT┃❓🟦❓")
    pve_category = await ensure_category("pve", "🦌🌲🧭┃PVE EXPEDITIONS┃🧭🌲🦌")

    channel_aliases = {
        "killfeed": ["killfeed", "kills", "pvpfeed", "playerkills"],
        "raids": ["raids", "raidfeed", "raiddetected", "raidalerts"],
        "building": ["building", "build", "buildfeed", "basebuilding"],
        "connections": ["connected", "connections", "connect", "joins", "playerjoins"],
        "disconnects": ["disconnects", "disconnect", "leftserver", "playerleaves"],
        "online": ["online", "onlinesurvivors", "liveonline", "survivorsonline"],
        "leaderboards": ["leaderboards", "leaderboard", "topkills", "rankings"],
        "heatmap": ["heatmap", "conflictheatmap", "pvPheatmap".lower()],
        "longshots": ["longshots", "longshot", "snipes"],
        "restart_alerts": ["restartalerts", "restart", "restarts", "serverrestarts"],
        "bot_updates": ["botupdates", "updates", "changelog", "newfeatures", "patchnotes"],
        "welcome": ["welcome", "newsurvivor", "joins"],
        "public_shame": ["wanderinginshame", "publicshame", "nameandshame", "bans"],
        "general_chat": ["survivorchat", "generalchat", "general", "chat"],
        "factions_chat": ["factionschat", "factions", "factionchat"],
        "faction_list": ["factionlist", "factionslist"],
        "help_channel": ["helpdesk", "help", "support"],
        "clips_channel": ["dayzclips", "clips", "media"],
        "economy": ["blackmarket", "economy", "shop", "market"],
        "ai_chat": ["survivorai", "aichat", "ai"],
    "admin_logs": ["adminlogs", "stafflogs"],
    "cheat_checks": ["cheatchecks", "anticheat", "pccheatcheck"],
    "command_logs": ["commandlogs", "commands"],
        "purchase_logs": ["purchaselogs", "purchases"],
        "vehicle_rentals": ["vehiclerentals", "rentvehicles", "rentals"],
        "rental_logs": ["rentallogs"],
        "faction_tickets": ["factiontickets", "factionrequests"],
        "faction_staff": ["factionstaff"],
        "zombie_feed": ["zombiefeed", "infectedfeed", "zmbfeed", "zombies"],
        "unconscious_feed": ["unconsciousfeed", "medicalfeed", "unconscious"],
        "cuts_feed": ["cutsfeed", "cuts", "damagefeed", "survivordamage"],
        "suicide_feed": ["suicidefeed", "suicides", "suicide"],
        "flag_feed": ["flagfeed", "flags", "territoryflags", "flagactivity"],
        "placed_feed": ["placedfeed", "placements", "placed", "packed", "itemactivity"],
        "pvp_intel": ["pvpintel", "pvptips", "pvpinfo"],
        "pve_quests": ["pvequests", "quests", "missions", "pvemissions"],
        "pve_hunting": ["pvehunting", "hunting", "animalhunts"],
        "pve_collection": ["pvecollection", "collection", "scavenger", "gathering"],
        "pve_fishing": ["pvefishing", "fishing", "fish"],
        "pve_crafting": ["pvecrafting", "crafting", "bushcraft"],
        "pve_expeditions": ["pveexpeditions", "expeditions", "exploration", "survivalruns"],
    "pve_info": ["pveinfo", "survivalinfo", "huntinginfo"],
    "pve_help": ["pvehelp", "pveadvice", "questhelp"],
        "pve_heatmap": ["pveheatmap", "animalheatmap"]
    }

    def channel_matches_key(channel, key, desired_name):
        normalized = normalize_discord_name(channel.name)
        desired = normalize_discord_name(desired_name)
        aliases = set(channel_aliases.get(key, []))
        aliases.add(desired)

        if key == "connections" and "disconnect" in normalized:
            return False

        return normalized in aliases or any(alias and alias in normalized for alias in aliases)

    async def ensure_channel(key, name, *, cat=None, private=False):
        target_category = cat or category
        channels = guild_configs[guild_id].setdefault("channels", {})
        if is_channel_key_disabled(guild_configs[guild_id], key) and not restore_deleted_channels:
            return None

        if restore_deleted_channels:
            set_channel_key_disabled(guild_configs[guild_id], key, False)

        existing_id = channels.get(key)
        overwrites = {}

        if private:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False)
            }
            for role in interaction.guild.roles:
                if role.permissions.administrator or role.name in guild_configs[guild_id].get("admin_roles", DEFAULT_ADMIN_ROLES):
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        if existing_id:
            existing_channel = interaction.guild.get_channel(existing_id)
            if existing_channel:
                try:
                    await existing_channel.edit(name=name, category=target_category)
                    if overwrites:
                        await existing_channel.edit(overwrites=overwrites)
                except Exception:
                    pass
                return existing_channel

            channels.pop(key, None)

        for existing_channel in interaction.guild.text_channels:
            if channel_matches_key(existing_channel, key, name):
                channels[key] = existing_channel.id
                try:
                    await existing_channel.edit(name=name, category=target_category)
                    if overwrites:
                        await existing_channel.edit(overwrites=overwrites)
                except Exception:
                    pass
                return existing_channel

        channel = await interaction.guild.create_text_channel(
            name,
            category=target_category,
            overwrites=overwrites
        )

        channels[key] = channel.id

        return channel
    await ensure_channel("killfeed", "🔥🔥・killfeed・🔥🔥", cat=live_category)
    await ensure_channel("raids", "🚨🏴・raids・🏴🚨", cat=live_category)
    await ensure_channel("building", "🔨🧱・building・🧱🔨", cat=live_category)
    await ensure_channel("connections", "🟢✅・connected・✅🟢", cat=live_category)
    await ensure_channel("disconnects", "🔴⛔・disconnects・⛔🔴", cat=live_category)
    await ensure_channel("zombie_feed", "🧟🧟・zombie-feed・🧟🧟", cat=live_category)
    await ensure_channel("unconscious_feed", "🩹⚠️・unconscious-feed・⚠️🩹", cat=live_category)
    await ensure_channel("cuts_feed", "🩸🩹・cuts-feed・🩹🩸", cat=live_category, private=True)
    await ensure_channel("suicide_feed", "💀🧠・suicide-feed・🧠💀", cat=live_category, private=True)
    await ensure_channel("flag_feed", "🚩🏴・flag-feed・🏴🚩", cat=live_category, private=True)
    await ensure_channel("placed_feed", "📦🧰・placed-feed・🧰📦", cat=live_category, private=True)
    await ensure_channel("pvp_intel", "⚔️📡・pvp-intel・📡⚔️", cat=live_category)

    await ensure_channel("online", "✅🎮・online-survivors・🎮✅", cat=info_category)
    await ensure_channel("leaderboards", "🏆📊・leaderboards・📊🏆", cat=info_category)
    await ensure_channel("heatmap", "🔥🗺️・heatmap・🗺️🔥", cat=info_category)
    await ensure_channel("longshots", "🎯🏹・longshots・🏹🎯", cat=info_category)
    await ensure_channel("restart_alerts", "📢⏰・restart-alerts・⏰📢", cat=info_category)
    await ensure_channel("bot_updates", "📢✨・bot-updates・✨📢", cat=info_category)

    await ensure_channel("welcome", "👋🟩・welcome・🟩👋", cat=community_category)
    await ensure_channel("public_shame", "🚫📣・wandering-in-shame・📣🚫", cat=community_category)
    await ensure_channel("general_chat", "💬🌲・survivor-chat・🌲💬", cat=community_category)
    await ensure_channel("ai_chat", "🧠📻・survivor-ai・📻🧠", cat=community_category)
    await ensure_channel("clips_channel", "🎬⭐・dayz-clips・⭐🎬", cat=community_category)

    await ensure_channel("factions_chat", "🏴⚔️・factions-chat・⚔️🏴", cat=faction_category)
    await ensure_channel("faction_list", "📜🏴・faction-list・🏴📜", cat=faction_category)
    await ensure_channel("faction_tickets", "🎫🏴・faction-tickets・🏴🎫", cat=faction_category)
    await ensure_channel("faction_staff", "🛡️🏴・faction-staff・🏴🛡️", cat=staff_category)

    await ensure_channel("help_channel", "❓📘・help-desk・📘❓", cat=support_category)
    await ensure_channel("economy", "💰🛒・black-market・🛒💰", cat=economy_category)
    await ensure_channel("admin_logs", "🛡️📕・admin-logs・📕🛡️", cat=staff_category)
    await ensure_channel("cheat_checks", "🕵️🚫・pc-cheat-check・🚫🕵️", cat=staff_category, private=True)
    await ensure_channel("command_logs", "📜🛡️・command-logs・🛡️📜", cat=staff_category)
    await ensure_channel("purchase_logs", "💳📦・purchase-logs・📦💳", cat=economy_category)
    await ensure_channel("vehicle_rentals", "🚗💰・vehicle-rentals・💰🚗", cat=economy_category)
    await ensure_channel("rental_logs", "🛻📒・rental-logs・📒🛻", cat=economy_category)
    pve_channels = await ensure_pve_channels(
        interaction.guild,
        guild_configs[guild_id],
        force=restore_deleted_channels
    )

    guild_configs[guild_id]["nitrado_token"] = nitrado_token
    guild_configs[guild_id]["service_id"] = service_id
    guild_configs[guild_id]["nitrado_user"] = nitrado_user.strip()
    guild_configs[guild_id]["ftp_user"] = ftp_user
    guild_configs[guild_id]["ftp_password"] = ftp_password
    if supplied_ftp_host:
        guild_configs[guild_id]["ftp_host"] = supplied_ftp_host
    else:
        guild_configs[guild_id].setdefault("ftp_host", "")

    save_guild_configs()

    try:
        sent_updates, updates_channel = await publish_bot_update_notes(interaction.guild, guild_configs[guild_id])
        if sent_updates:
            print(f"BOT UPDATE BACKLOG SEEDED {interaction.guild.name}: {sent_updates}")
    except Exception as update_error:
        print(f"BOT UPDATE SETUP ERROR {guild_id}: {update_error}")

    try:
        shame_channel = bot.get_channel(guild_configs[guild_id]["channels"].get("public_shame"))
        if shame_channel:
            intro = discord.Embed(
                title="WANDERING IN SHAME",
                description="Public ban, temp-ban, and unban notices will appear here with staff reason and duration.",
                color=0xE74C3C
            )
            intro.set_thumbnail(url=BOT_IMAGE)
            intro.set_footer(text="Wandering Bot Alpha - Public Moderation Feed")
            await shame_channel.send(embed=style_embed(intro))

        cheat_channel = bot.get_channel(guild_configs[guild_id]["channels"].get("cheat_checks"))
        if cheat_channel:
            await post_cheat_check_intro(cheat_channel, guild_configs[guild_id])
    except Exception as setup_feed_error:
        print(f"SETUP SAFETY FEED INTRO ERROR: {setup_feed_error}")

    help_channel = bot.get_channel(
        guild_configs[guild_id]["channels"].get("help_channel")
    )

    if help_channel:

        setup_embed = discord.Embed(
            title="WANDERING BOT ALPHA - SERVER COMMAND CENTER",
            description=(
                "Your server is now connected. This guide is for owners and admins.\n\n"
                "Use slash commands for all bot controls."
            ),
            color=0xF1C40F
        )

        setup_embed.add_field(
            name="LIVE SERVER INTELLIGENCE",
            value=(
                "`/online` - current tracked survivors online\n"
                "`/serverstatus` - bot and tracking status\n"
                "`/map` - admin-only live survivor map using latest ADM positions\n"
                "`/heatmap` - territory activity summary\n"
                "`/topkills` - kill leaderboard\n"
                "`/toplongshots` - global longshot leaderboard\n"
                "`/backfilladmstats` - add up to 14 days of ADM history into leaderboard stats\n"
                "`/backfillkills` - post recent ADM kill history into killfeed and longshots\n"
                "`/setaiimages` - occasional AI-generated DayZ-style pictures\n"
                "`/aiimagepostnow` - post one AI picture immediately\n"
                "`/setservermap` and `/setheatmapimage` - choose map scale and real map artwork\n"
                "Auto channels: killfeed, raids, building, zombie-feed, unconscious-feed, online, leaderboards, heatmap"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="RAILWAY MAP IMAGE FIX",
            value=(
                "Railway cannot use Windows paths like `C:\\Users\\...`. If heatmaps show the drawn fallback map, set public map URLs:\n"
                "`/setheatmapimage map_name: chernarus image_source: https://i.redd.it/a2mn8bzx93gd1.jpeg`\n"
                "`/setheatmapimage map_name: livonia image_source: https://i.imgur.com/nzEp9wF.jpeg`\n"
                "Use `/mapimagestatus` after setting them. You can also upload a map with `/uploadmapimage`."
            ),
            inline=False
        )

        setup_embed.add_field(
            name="ADMIN SETUP & MODERATION",
            value=(
                "`/tools setadminrole role` - replace the primary bot admin role\n"
                "`/tools addstaffrole role` - add another role allowed to use staff tools\n"
                "`/tools staffroles` - list staff roles\n"
                "`/shamesetup` - create the public Wandering in Shame feed\n"
                "`/adminban member reason` - ban a Discord member and post the reason\n"
                "`/admintempban member duration reason` - temp-ban with examples like `2h` or `3d`\n"
                "`/adminunban user_id reason` - unban by Discord user ID\n"
                "`/cheatchecksetup` - create the private PC cheat-check evidence feed\n"
                "`/cheatcheckconfig` - turn PC cheat-check detection on/off\n"
                "`/purge amount` - clear recent messages\n"
                "`/purgeuser member amount` - clear a member's messages\n"
                "`/tools purgebots amount` - clear bot messages\n"
                "`/tools giverole` and `/tools removerole` - manage Discord roles\n"
                "`/tools channelstatus` - see channels kept deleted\n"
                "`/tools channelpacks` - see restore groups\n"
                "`/tools restorechannels` or `/tools restorechannelpack` - bring deleted bot channels back"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="SERVER CONTROL & RADAR",
            value=(
                "`/restartserver` - trigger a Nitrado restart\n"
                "`/setrestartinterval hours` - set restart interval\n"
                "`/setrestartstart hour` - set UTC restart start hour\n"
                "`/cancelrestarts` - disable recurring restart schedule\n"
                "`/listrestarts` - show restart schedule\n"
                "`/botupdates` - create/repair the public bot updates feed and post missing notes\n"
                "`/togglebasedamage state` - log base damage state\n"
                "`/setradarchannel channel` - choose radar channel\n"
                "`/radarping x y reason` - send a manual map ping\n"
                "`/addradarzone` - alert staff when non-ignored gamertags enter an area\n"
                "`/forcelinkgamer` - admin override when ADM linking cannot find a player"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="ECONOMY, SHOP, REWARDS & PUNISHMENTS",
            value=(
                "`/wallet` - check wallet\n"
                "`/shop` - view black market\n"
                "`/buy item_name x y` - queue item delivery\n"
                "`/tools rentvehicle vehicle_name rental_hours x y` - queue vehicle rental\n"
                "Shop admin: `/addshopitem`, `/editshopitem`, `/toggleshopitem`, `/removeshopitem`, `/givepennies`, `/tools shopcategories`, `/tools importtypesxml`\n"
                "Admin rules: `/addreward`, `/addpunishment`, `/listrules`, `/removerule`"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="TRANSLATION SYSTEM",
            value=(
                "`/translationconfig` - configure automatic chat translation\n"
                "Mode choices: `same` posts beside the original, `channel` forwards to another channel, `off` disables it.\n"
                "Use `source_language:auto` to auto-detect languages when your translation service supports it.\n"
                "Same-channel translation posts translated embeds beside chat. Channel mode forwards translations into a chosen channel."
            ),
            inline=False
        )

        setup_embed.add_field(
            name="FACTIONS, IDENTITY & SUPPORT",
            value=(
                "`/linkgamer gamertag` - link Discord to gamertag\n"
                "`/mylink` - view linked account\n"
                "`/playerstats player_name` - lookup player stats\n"
                "`/factionticket faction_name` - create faction request\n"
                "`/factionapprove message_id` - approve faction ticket\n"
                "`/supportbot issue` - admin-only ticket to the bot owner"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="FINAL DAYZ SERVER STEP",
            value=(
                "PC/custom hosts: add `SpawnWanderingDeliveries();` to your DayZ `init.c` after weather setup. "
                "That enables restart delivery spawning from the XML this bot uploads.\n"
                "Console hosts: `init.c` is not exposed. Use XML/JSON config files instead: `types.xml`, "
                "`cfgspawnabletypes.xml`, `globals.xml`, `events.xml`, `cfgeventspawns.xml`, and `cfgplayerspawn.json`.\n\n"
                "Console object spawns: run `/console setupobjects` to create `custom/WanderingBotObjects.json` and add it to "
                "`cfggameplay.json` under `WorldsData.objectSpawnersArr`. Add spawns with `/console addobject`.\n"
                "Item spawning: add shop items with `/addshopitem`, players use `/buy item_name x y`, then the bot uploads `deliveries.xml` for next restart.\n"
                "Vehicle resets/rentals: players use `/tools rentvehicle vehicle_name rental_hours x y`; the vehicle entry is written into the same restart delivery XML.\n"
                "In-game message rotation: the server owner can use `/setdayzmessages messages:... interval_minutes:...` to upload a safe XML message file. Check your Nitrado FTP path before changing the default."
            ),
            inline=False
        )
        setup_embed.add_field(
            name="AUTOMATIC DELIVERY BRIDGE INSTALL",
            value=(
                "Use `/installdayzbridge` after setup if you want the bot to install the restart delivery hook for you. "
                "If Nitrado shows a specific FTP host/IP, include it with `ftp_host:` or save it with `/bridge setftphost`. "
                "It downloads `init.c`, uploads a timestamped backup, inserts `SpawnWanderingDeliveries();` only if missing, "
                "and uploads a starter `deliveries.xml`. It is owner-only because changing `init.c` can affect server boot. "
                "This is for PC/custom hosts only; console packages should use the XML/JSON config workflow."
            ),
            inline=False
        )

        setup_embed.set_thumbnail(url=BOT_IMAGE)
        setup_embed.set_footer(
            text="Wandering System created by CraneMonkey6273"
        )

        await help_channel.send(embed=style_embed(setup_embed))
        await send_command_guide_pages(
            help_channel,
            title="WANDERING BOT FULL COMMAND LIST",
            intro=(
                "This is the live command guide for the bot. It lists every registered slash command, "
                "what it does, and the required or optional options to type."
            )
        )

    await interaction.followup.send(
        "✅ Wandering Bot fully connected and operational.",
        ephemeral=True
    )

bridge_group = app_commands.Group(
    name="bridge",
    description="DayZ bridge and Nitrado FTP helper commands"
)


@bridge_group.command(name="setftphost", description="Admin: set the saved Nitrado FTP host/IP for this server")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(ftp_host="Nitrado FTP host/IP, for example the FTP server shown in Nitrado file browser")
async def setftphost(interaction: discord.Interaction, ftp_host: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    host = normalize_ftp_host(ftp_host)
    if not looks_like_ftp_host(host):
        await interaction.response.send_message(
            discord_safe_content(
                "That does not look like an FTP host/IP. "
                f"I read it as `{host or 'empty'}`. Paste the Nitrado FTP server value, for example `ukln138.gamedata.io`."
            ),
            ephemeral=True
        )
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, new_guild_config(interaction.guild))
    config["ftp_host"] = host
    config.pop("_discovered_ftp_hosts", None)
    save_guild_configs()

    await interaction.response.send_message(
        "FTP host saved for this server. `/installdayzbridge install:true` will use the existing setup plus this host.",
        ephemeral=True
    )


# =========================================================
# NITRADO XML DELIVERY BRIDGE
# =========================================================

def nitrado_ftp_hosts(config):
    hosts = [
        config.get("ftp_host"),
        config.get("ftp_hostname"),
        config.get("nitrado_ftp_host"),
        os.getenv("NITRADO_FTP_HOST"),
        *discover_nitrado_ftp_hosts_from_api(config),
        "ftps.nitrado.net",
        "ftp.nitrado.net",
    ]
    deduped = []
    for host in hosts:
        host = normalize_ftp_host(host)
        if host and host not in deduped:
            deduped.append(host)
    return deduped


def normalize_ftp_host(value):
    text = str(value or "").strip()
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)
    text = text.strip("`'\"<>")
    text = re.sub(r"^(?:ftps?|sftp)://", "", text, flags=re.IGNORECASE)
    text = text.split("/", 1)[0].split("\\", 1)[0].strip()
    if "@" in text:
        text = text.rsplit("@", 1)[-1].strip()
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")].strip()
    if " " in text:
        host_match = re.search(
            r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)\b",
            text,
            re.IGNORECASE
        )
        text = host_match.group(0) if host_match else text
    if ":" in text:
        host_part, port_part = text.rsplit(":", 1)
        if port_part.isdigit():
            text = host_part.strip()
    return text.strip().strip("`'\"<>")


def looks_like_ftp_host(value):
    text = normalize_ftp_host(value)
    if not text or "/" in text or "@" in text or " " in text:
        return False
    if text.lower() in {"api.nitrado.net", "nitrado.net"}:
        return False
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", text):
        return all(0 <= int(part) <= 255 for part in text.split("."))
    return bool(re.match(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$", text, re.IGNORECASE)) and len(text) <= 253


def collect_host_values(value, path="", results=None):
    if results is None:
        results = []

    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower()
            nested_path = f"{path}.{key_text}" if path else key_text
            if isinstance(nested, str):
                host_related = (
                    "ftp" in nested_path
                    or key_text in {"host", "hostname", "ip", "address", "server"}
                    or key_text.endswith("_host")
                )
                if host_related and looks_like_ftp_host(nested):
                    results.append(normalize_ftp_host(nested))
            else:
                collect_host_values(nested, nested_path, results)
    elif isinstance(value, list):
        for nested in value:
            collect_host_values(nested, path, results)

    return results


def discover_nitrado_ftp_hosts_from_api(config):
    cached = config.get("_discovered_ftp_hosts")
    if isinstance(cached, list) and cached:
        return cached

    headers = nitrado_api_headers(config)
    service_id = config.get("service_id")
    if not headers or not service_id:
        return []

    url = f"https://api.nitrado.net/services/{service_id}/gameservers"
    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.status_code != 200:
            return []

        discovered = []
        for host in collect_host_values(response.json()):
            if host not in discovered:
                discovered.append(host)

        if discovered:
            config["_discovered_ftp_hosts"] = discovered[:5]
        return discovered[:5]
    except Exception:
        return []


def format_ftp_connection_error(host_errors):
    if not host_errors:
        return "Could not connect to Nitrado FTP."

    dns_errors = [
        error
        for _, error in host_errors
        if isinstance(error, socket.gaierror) or "Name or service not known" in str(error)
    ]
    lines = [f"{host}: {error}" for host, error in host_errors]
    if dns_errors and len(dns_errors) == len(host_errors):
        return (
            "Could not resolve any Nitrado FTP host from this bot environment. "
            "This is DNS/network access, not a missing `init.c` path. Tried: "
            + "; ".join(lines)
        )
    return "Could not connect to Nitrado FTP. Tried: " + "; ".join(lines)


def connect_nitrado_ftp(config, timeout_seconds=30):
    ftp_user = config.get("ftp_user")
    ftp_pass = config.get("ftp_password")

    if not ftp_user or not ftp_pass:
        return None, None, "FTP details are not configured."

    host_errors = []
    for ftp_host in nitrado_ftp_hosts(config):
        try:
            ftp = FTP_TLS(ftp_host, timeout=timeout_seconds)
            ftp.login(ftp_user, ftp_pass)
            ftp.prot_p()
            try:
                ftp.sock.settimeout(timeout_seconds)
            except Exception:
                pass
            return ftp, ftp_host, None
        except Exception as error:
            host_errors.append((ftp_host, error))

    return None, None, format_ftp_connection_error(host_errors)


def nitrado_api_headers(config):
    token = config.get("nitrado_token")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def nitrado_api_service_url(config, endpoint):
    service_id = config.get("service_id")
    if not service_id:
        return None
    endpoint = str(endpoint or "").lstrip("/")
    return f"https://api.nitrado.net/services/{service_id}/gameservers/file_server/{endpoint}"


def is_noftp_dayz_path(path):
    clean = canonical_remote_path(path)
    prefixes = (
        "/dayz/",
        "/dayz_missions",
        "/dayz_missions/",
        "/dayzps/",
        "/dayzps_missions",
        "/dayzps_missions/",
        "/dayzxb/",
        "/dayzxb_missions",
        "/dayzxb_missions/",
        "/dayzserver/",
        "/dayzxbserver/",
        "/mpmissions/",
    )
    return any(clean == prefix.rstrip("/") or clean.startswith(prefix) for prefix in prefixes)


def nitrado_api_file_path(config, target_path):
    clean = str(target_path or "").replace("\\", "/").strip()
    if not clean:
        return clean

    if not clean.startswith("/"):
        clean = "/" + clean

    if clean.startswith("/games/"):
        return clean

    nitrado_user = str(config.get("nitrado_user") or "").strip()
    if nitrado_user and is_noftp_dayz_path(clean):
        return f"/games/{nitrado_user}/noftp{clean}"

    if nitrado_user and clean.startswith("/noftp/"):
        return f"/games/{nitrado_user}{clean}"

    return clean


def nitrado_api_file_path_candidates(config, target_path):
    clean = str(target_path or "").replace("\\", "/").strip()
    if not clean:
        return []

    if not clean.startswith("/"):
        clean = "/" + clean

    candidates = [nitrado_api_file_path(config, clean), clean]
    nitrado_user = str(config.get("nitrado_user") or "").strip()

    if nitrado_user:
        if is_noftp_dayz_path(clean):
            candidates.extend([
                f"/games/{nitrado_user}/noftp{clean}",
                f"/games/{nitrado_user}{clean}",
            ])
        elif clean.startswith("/noftp/"):
            candidates.append(f"/games/{nitrado_user}{clean}")
        elif clean.startswith("/mpmissions/"):
            candidates.extend([
                f"/games/{nitrado_user}/noftp/dayzxb{clean}",
                f"/dayzxb{clean}",
            ])

    deduped = []
    for candidate in candidates:
        candidate = str(candidate or "").replace("\\", "/").strip()
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def split_remote_file_path(target_path):
    clean = str(target_path or "").replace("\\", "/").strip()
    folder = os.path.dirname(clean) or "/"
    name = os.path.basename(clean)
    return folder, name


def nitrado_api_token_payload(data):
    token_data = data.get("token") or data.get("data", {}).get("token") or {}
    token_url = token_data.get("url") or data.get("url")
    token_value = token_data.get("token") or data.get("token")
    if isinstance(token_value, dict):
        token_value = token_value.get("token")
    return token_url, token_value


def download_text_file_from_nitrado_api(config, target_path):
    headers = nitrado_api_headers(config)
    url = nitrado_api_service_url(config, "download")
    if not headers or not url:
        return False, "Nitrado API token or service ID is missing.", None

    try:
        attempts = []
        for api_path in nitrado_api_file_path_candidates(config, target_path):
            for param_name in ("file", "path"):
                response = requests.get(
                    url,
                    headers=headers,
                    params={param_name: api_path},
                    timeout=15
                )
                if response.status_code != 200:
                    attempts.append(f"{param_name}={api_path}: {response.status_code} {response.text[:160]}")
                    continue

                token_url, token_value = nitrado_api_token_payload(response.json().get("data", response.json()))
                if not token_url:
                    attempts.append(f"{param_name}={api_path}: no download URL")
                    continue

                file_response = requests.get(
                    token_url,
                    params={"token": token_value} if token_value else None,
                    timeout=20
                )
                if file_response.status_code != 200:
                    attempts.append(f"{param_name}={api_path}: file {file_response.status_code} {file_response.text[:160]}")
                    continue

                return True, f"Downloaded successfully via Nitrado API using `{param_name}` path `{api_path}`.", file_response.content.decode("utf-8", errors="ignore")

        return False, "Nitrado API download failed for all path variants: " + "; ".join(attempts[-8:]), None

    except Exception as error:
        return False, f"Nitrado API download failed: {error}", None


def ensure_nitrado_api_folder(config, folder):
    headers = nitrado_api_headers(config)
    url = nitrado_api_service_url(config, "mkdir")
    if not headers or not url:
        return

    folder = nitrado_api_file_path(config, folder)
    parent = os.path.dirname(folder.rstrip("/")) or "/"
    name = os.path.basename(folder.rstrip("/"))
    if not name:
        return

    try:
        requests.post(
            url,
            headers=headers,
            data={"path": parent, "name": name},
            timeout=20
        )
    except Exception:
        pass


def upload_text_file_to_nitrado_api(config, target_path, text_content):
    headers = nitrado_api_headers(config)
    url = nitrado_api_service_url(config, "upload")
    if not headers or not url:
        return False, "Nitrado API token or service ID is missing."

    api_target_path = nitrado_api_file_path(config, target_path)
    folder, name = split_remote_file_path(api_target_path)
    if not name:
        return False, "Remote file name is missing."

    try:
        ensure_nitrado_api_folder(config, folder)
        token_response = requests.post(
            url,
            headers=headers,
            data={"path": folder, "file": name},
            timeout=20
        )
        if token_response.status_code not in (200, 201):
            return False, f"Nitrado API upload token failed with status {token_response.status_code}: {token_response.text[:300]}"

        token_url, token_value = nitrado_api_token_payload(token_response.json().get("data", token_response.json()))
        if not token_url or not token_value:
            return False, "Nitrado API did not return an upload URL/token."

        upload_response = requests.post(
            token_url,
            headers={
                "content-type": "application/binary",
                "token": token_value,
            },
            data=str(text_content or "").encode("utf-8"),
            timeout=30
        )
        if upload_response.status_code not in (200, 201, 204):
            return False, f"Nitrado API file upload failed with status {upload_response.status_code}: {upload_response.text[:300]}"

        return True, "Uploaded successfully via Nitrado API."

    except Exception as error:
        return False, f"Nitrado API upload failed: {error}"


def upload_delivery_xml_to_nitrado(config, xml_path):

    try:

        with open(xml_path, "r", encoding="utf-8", errors="ignore") as xml_file:
            xml_text = xml_file.read()

        target_path = (
            config.get("dayz_delivery_bridge", {}).get("delivery_path")
            or "/dayzxb/custom/deliveries.xml"
        )

        api_success, api_message = upload_text_file_to_nitrado_api(config, target_path, xml_text)
        if api_success:
            print(api_message)
            return True

        ftp, ftp_host, ftp_error = connect_nitrado_ftp(config)
        if ftp_error:
            print(ftp_error)
            return False

        with open(xml_path, "rb") as xml_file:

            ftp.storbinary(
                f"STOR {target_path}",
                xml_file
            )

        ftp.quit()

        print(f"DELIVERY XML UPLOADED TO NITRADO VIA {ftp_host}")

        return True

    except Exception as error:

        print(error)
        return False


def upload_text_file_to_nitrado(config, target_path, text_content):
    temp_path = None
    try:
        api_success, api_message = upload_text_file_to_nitrado_api(config, target_path, text_content)
        if api_success:
            return True, api_message

        ftp, ftp_host, ftp_error = connect_nitrado_ftp(config)
        if ftp_error:
            return False, f"{api_message} FTP fallback also failed: {ftp_error}"

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".xml") as temp_file:
            temp_file.write(text_content)
            temp_path = temp_file.name

        remote_folder = os.path.dirname(str(target_path).replace("\\", "/"))
        if remote_folder and remote_folder != "/":
            try:
                ftp.mkd(remote_folder)
            except Exception:
                pass

        with open(temp_path, "rb") as file_obj:
            ftp.storbinary(f"STOR {target_path}", file_obj)

        ftp.quit()

        try:
            os.remove(temp_path)
        except Exception:
            pass

        return True, f"Uploaded successfully via {ftp_host}."

    except Exception as error:
        return False, str(error)
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except Exception:
                pass


def download_text_file_from_nitrado_ftp(config, target_path, exact_only=False):
    ftp, ftp_host, ftp_error = connect_nitrado_ftp(config)
    if ftp_error:
        return False, ftp_error, None

    clean = canonical_remote_path(target_path)
    ftp_paths = [clean, clean.lstrip("/")] if exact_only else nitrado_ftp_path_candidates(config, target_path)
    ftp_errors = []

    for ftp_path in ftp_paths:
        buffer = io.BytesIO()
        try:
            ftp.retrbinary(f"RETR {ftp_path}", buffer.write)
            ftp.quit()
            content = buffer.getvalue().decode("utf-8", errors="ignore")
            return True, f"Downloaded successfully via {ftp_host} path `{ftp_path}`.", content
        except Exception as error:
            ftp_errors.append(f"{ftp_path}: {error}")
            folder = os.path.dirname(str(ftp_path).replace("\\", "/")) or "/"
            filename = os.path.basename(str(ftp_path).replace("\\", "/"))
            if not filename:
                continue
            try:
                cwd_target = canonical_remote_path(folder)
                ftp.cwd(cwd_target)
                buffer = io.BytesIO()
                ftp.retrbinary(f"RETR {filename}", buffer.write)
                ftp.quit()
                content = buffer.getvalue().decode("utf-8", errors="ignore")
                return True, f"Downloaded successfully via {ftp_host} folder `{cwd_target}` file `{filename}`.", content
            except Exception as cwd_error:
                ftp_errors.append(f"{folder}/{filename}: {cwd_error}")

    try:
        ftp.quit()
    except Exception:
        pass

    return False, "; ".join(ftp_errors[-6:]) or "FTP download failed.", None


def download_text_file_from_nitrado(config, target_path):
    try:
        api_success, api_message, api_content = download_text_file_from_nitrado_api(config, target_path)
        if api_success:
            return True, api_message, api_content

        ftp_success, ftp_message, ftp_content = download_text_file_from_nitrado_ftp(config, target_path)
        if ftp_success:
            return True, ftp_message, ftp_content

        return False, f"{api_message} FTP fallback also failed: {ftp_message}", None

    except Exception as error:
        return False, str(error), None


def canonical_remote_path(path):
    clean = str(path or "").replace("\\", "/").strip().strip("`'\"<>")
    if not clean:
        return ""

    clean = re.sub(r"/+", "/", clean)
    if not clean.startswith("/"):
        clean = "/" + clean

    clean = re.sub(r"(/dayzxb_missions)(?:/dayzxb_missions)+/", r"\1/", clean)
    clean = re.sub(r"(/dayzxb)(?:/dayzxb)+/", r"\1/", clean)
    return clean.rstrip("/") or "/"


def nitrado_ftp_path_candidates(config, target_path):
    clean = canonical_remote_path(target_path)
    if not clean:
        return []

    candidates = [
        clean,
        clean.lstrip("/"),
        nitrado_api_file_path(config, clean),
        nitrado_api_file_path(config, clean).lstrip("/"),
    ]

    nitrado_user = str(config.get("nitrado_user") or "").strip()
    if nitrado_user and is_noftp_dayz_path(clean):
        candidates.extend([
            f"/games/{nitrado_user}/noftp{clean}",
            f"games/{nitrado_user}/noftp{clean}",
            f"/noftp{clean}",
            f"noftp{clean}",
        ])

    deduped = []
    for candidate in candidates:
        candidate = canonical_remote_path(candidate)
        if candidate.startswith("/games/"):
            candidate_variants = [candidate, candidate.lstrip("/")]
        else:
            candidate_variants = [candidate, candidate.lstrip("/")]
        for candidate in candidate_variants:
            if candidate and candidate not in deduped:
                deduped.append(candidate)
    return deduped


def list_remote_directory_from_nitrado_api(config, folder, timeout_seconds=8):
    headers = nitrado_api_headers(config)
    url = nitrado_api_service_url(config, "list")
    if not headers or not url:
        return []

    entries = []
    for api_folder in nitrado_api_file_path_candidates(config, folder):
        try:
            response = requests.get(
                url,
                headers=headers,
                params={"dir": api_folder},
                timeout=timeout_seconds
            )
            if response.status_code != 200:
                continue

            data = response.json()
            for entry in data.get("data", {}).get("entries", []):
                name = entry.get("name")
                path = entry.get("path")
                if name or path:
                    entries.append({
                        "name": str(name or os.path.basename(str(path))),
                        "path": canonical_remote_path(path or os.path.join(folder, str(name))),
                        "type": str(entry.get("type") or entry.get("file_type") or ""),
                    })
        except Exception:
            continue

    return entries


def list_remote_directory_from_ftp(config, folder, timeout_seconds=8):
    ftp, ftp_host, ftp_error = connect_nitrado_ftp(config, timeout_seconds=timeout_seconds)
    if ftp_error:
        return []

    entries = []
    try:
        for remote_folder in nitrado_ftp_path_candidates(config, folder):
            for item, entry_type in ftp_list_directory_entries(ftp, remote_folder):
                item_text = str(item).replace("\\", "/").rstrip("/")
                name = os.path.basename(item_text)
                if not name:
                    continue
                remote_clean = canonical_remote_path(remote_folder)
                item_clean = item_text.lstrip("/")
                remote_key = remote_clean.lstrip("/")
                if item_text.startswith("/"):
                    path = canonical_remote_path(item_text)
                elif remote_key and item_clean.startswith(remote_key + "/"):
                    path = canonical_remote_path(item_clean)
                else:
                    path = canonical_remote_path(f"{remote_clean}/{item_clean}")
                entries.append({
                    "name": name,
                    "path": path,
                    "type": entry_type,
                })
    except Exception:
        pass
    finally:
        try:
            ftp.quit()
        except Exception:
            pass

    return entries


def ftp_list_directory_entries(ftp, remote_folder):
    remote_folder = canonical_remote_path(remote_folder)
    entries = []
    seen = set()

    def add_entry(name, entry_type=""):
        name = str(name or "").replace("\\", "/").rstrip("/")
        if not name or name in {".", ".."}:
            return
        key = (name, entry_type)
        if key in seen:
            return
        seen.add(key)
        entries.append((name, entry_type))

    for candidate in [remote_folder, remote_folder.lstrip("/")]:
        if not candidate:
            continue
        try:
            for item in ftp.nlst(candidate):
                add_entry(item)
        except Exception:
            pass

    original_folder = None
    try:
        original_folder = ftp.pwd()
    except Exception:
        pass

    for candidate in [remote_folder, remote_folder.lstrip("/")]:
        if not candidate:
            continue
        try:
            ftp.cwd(candidate)
        except Exception:
            continue

        try:
            for name, facts in ftp.mlsd():
                add_entry(name, str((facts or {}).get("type") or ""))
        except Exception:
            pass

        try:
            for item in ftp.nlst():
                add_entry(item)
        except Exception:
            pass

        if entries:
            break

    if original_folder:
        try:
            ftp.cwd(original_folder)
        except Exception:
            pass

    return entries


def remote_directory_entries(config, folder, timeout_seconds=8):
    entries = []
    for entry in list_remote_directory_from_nitrado_api(config, folder, timeout_seconds=timeout_seconds):
        entries.append(entry)
    for entry in list_remote_directory_from_ftp(config, folder, timeout_seconds=timeout_seconds):
        entries.append(entry)

    deduped = []
    seen = set()
    for entry in entries:
        path = canonical_remote_path(entry.get("path"))
        if not path or path in seen:
            continue
        seen.add(path)
        entry["path"] = path
        deduped.append(entry)
    return deduped


def init_search_roots(config):
    nitrado_user = str(config.get("nitrado_user") or "").strip()
    base_roots = [
        "/",
        "/dayz",
        "/dayz/mpmissions",
        "/dayz_missions",
        "/dayz_missions/mpmissions",
        "/dayzps",
        "/dayzps/mpmissions",
        "/dayzps_missions",
        "/dayzps_missions/mpmissions",
        "/dayzxb",
        "/dayzxb/mpmissions",
        "/dayzxb_missions",
        "/dayzxb_missions/mpmissions",
        "/dayzserver",
        "/dayzserver/mpmissions",
        "/dayzxbserver",
        "/dayzxbserver/mpmissions",
        "/mpmissions",
    ]
    roots = list(base_roots)

    if nitrado_user:
        roots.extend(f"/games/{nitrado_user}/noftp{root}" for root in base_roots if root != "/")
        roots.append(f"/games/{nitrado_user}/noftp")

    deduped = []
    for root in roots:
        root = str(root or "").replace("\\", "/").rstrip("/") or "/"
        if root not in deduped:
            deduped.append(root)
    return deduped


def remember_remote_path(paths, candidate):
    candidate = canonical_remote_path(candidate)
    if candidate and candidate not in paths:
        paths.append(candidate)


def search_remote_init_paths_from_nitrado_api(config, max_dirs=60, timeout_seconds=8):
    headers = nitrado_api_headers(config)
    url = nitrado_api_service_url(config, "list")
    if not headers or not url:
        return []

    found = []
    for root in init_search_roots(config):
        for api_root in nitrado_api_file_path_candidates(config, root):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params={"dir": api_root, "search": "*init.c*"},
                    timeout=timeout_seconds
                )
                if response.status_code != 200:
                    continue

                data = response.json()
                for entry in data.get("data", {}).get("entries", []):
                    name = str(entry.get("name") or "").strip()
                    path = str(entry.get("path") or "").replace("\\", "/").rstrip("/")
                    if name.lower() == "init.c":
                        remember_remote_path(found, path or f"{root.rstrip('/')}/init.c")
                    elif path.lower().endswith("/init.c"):
                        remember_remote_path(found, path)
            except Exception:
                continue

    queued = []
    seen_dirs = set()
    for root in init_search_roots(config):
        root = str(root or "").replace("\\", "/").rstrip("/") or "/"
        if root not in queued:
            queued.append(root)

    index = 0
    while index < len(queued) and len(seen_dirs) < max_dirs:
        current = queued[index]
        index += 1

        if current in seen_dirs:
            continue
        seen_dirs.add(current)

        depth = current.strip("/").count("/")
        for entry in list_remote_directory_from_nitrado_api(config, current, timeout_seconds=timeout_seconds):
            name = str(entry.get("name") or "").strip()
            path = str(entry.get("path") or "").replace("\\", "/").rstrip("/")
            if not path:
                continue

            if name.lower() == "init.c" or path.lower().endswith("/init.c"):
                remember_remote_path(found, path)
                continue

            if depth >= 8:
                continue

            entry_type = str(entry.get("type") or "").lower()
            is_directory = entry_type in {"dir", "directory", "folder"}
            if not is_directory and not looks_like_remote_directory(path):
                continue

            if path not in seen_dirs and path not in queued:
                queued.append(path)

    return found


def ftp_child_path(parent, item):
    parent = canonical_remote_path(parent)
    item = str(item or "").replace("\\", "/").rstrip("/")
    if not item:
        return ""
    if item.startswith("/"):
        return canonical_remote_path(item)
    parent_key = parent.lstrip("/")
    item_key = item.lstrip("/")
    if parent_key and item_key.startswith(parent_key + "/"):
        return canonical_remote_path(item_key)
    if parent == "/":
        return canonical_remote_path(item.lstrip("/"))
    return canonical_remote_path(f"{parent}/{item.lstrip('/')}")


def looks_like_remote_directory(path):
    name = os.path.basename(str(path or "").rstrip("/")).lower()
    if not name:
        return False
    if name == "init.c":
        return False
    if "." in name and not name.startswith("dayzoffline."):
        return False
    skip = {"logs", "profiles", "storage_1", "cache", "__pycache__"}
    return name not in skip


def search_remote_init_paths_from_ftp(config, max_depth=6, max_dirs=60, timeout_seconds=8):
    ftp, ftp_host, ftp_error = connect_nitrado_ftp(config, timeout_seconds=timeout_seconds)
    if ftp_error:
        return []

    found = []
    queued = []
    seen_dirs = set()

    try:
        for root in init_search_roots(config):
            for candidate in nitrado_ftp_path_candidates(config, root):
                candidate = str(candidate or "").replace("\\", "/").rstrip("/") or "/"
                if candidate not in queued:
                    queued.append(candidate)

        index = 0
        while index < len(queued) and len(seen_dirs) < max_dirs:
            current = queued[index]
            index += 1

            if current in seen_dirs:
                continue
            seen_dirs.add(current)

            depth = current.strip("/").count("/")
            listing = ftp_list_directory_entries(ftp, current)
            if not listing:
                continue

            for item, entry_type in listing:
                child = ftp_child_path(current, item)
                if not child:
                    continue

                name = os.path.basename(child.rstrip("/"))
                if name.lower() == "init.c":
                    remember_remote_path(found, child)
                    continue

                if depth >= max_depth:
                    continue

                if entry_type and entry_type not in {"dir", "directory", "folder"}:
                    continue

                if not looks_like_remote_directory(child):
                    continue

                if child not in seen_dirs and child not in queued:
                    queued.append(child)
    except Exception:
        pass
    finally:
        try:
            ftp.quit()
        except Exception:
            pass

    return found


def discover_init_c_paths(config, max_dirs=60, timeout_seconds=8):
    discovered = []

    for candidate in search_remote_init_paths_from_nitrado_api(config, max_dirs=max_dirs, timeout_seconds=timeout_seconds):
        remember_remote_path(discovered, candidate)

    for candidate in search_remote_init_paths_from_ftp(config, max_dirs=max_dirs, timeout_seconds=timeout_seconds):
        remember_remote_path(discovered, candidate)

    bases = [
        "/dayz/mpmissions",
        "/dayz_missions",
        "/dayz_missions/mpmissions",
        "/dayzps/mpmissions",
        "/dayzps_missions",
        "/dayzps_missions/mpmissions",
        "/dayzxb/mpmissions",
        "/dayzxb_missions",
        "/dayzxb_missions/mpmissions",
        "/dayzserver/mpmissions",
        "/dayzxbserver/mpmissions",
        "/mpmissions",
    ]

    for base in bases:
        for entry in remote_directory_entries(config, base, timeout_seconds=timeout_seconds):
            name = str(entry.get("name") or "").strip()
            path = str(entry.get("path") or "").replace("\\", "/").rstrip("/")
            if not name or not path:
                continue
            if name.startswith(".") or name.lower() in {"__pycache__", "storage_1"}:
                continue
            if name.lower() == "init.c":
                candidate = path
            else:
                candidate = f"{path}/init.c"
            remember_remote_path(discovered, candidate)

    return discovered


def bridge_init_c_diagnostic(config, max_dirs=60, max_roots=12, timeout_seconds=8):
    found = discover_init_c_paths(config, max_dirs=max_dirs, timeout_seconds=timeout_seconds)
    visible_roots = []

    for root in init_search_roots(config)[:max_roots]:
        entries = remote_directory_entries(config, root, timeout_seconds=timeout_seconds)
        if not entries:
            continue

        names = []
        for entry in entries[:8]:
            name = str(entry.get("name") or os.path.basename(str(entry.get("path") or ""))).strip()
            if name and name not in names:
                names.append(name)

        visible_roots.append({
            "root": root,
            "count": len(entries),
            "sample": names,
        })

    notes = []
    if not visible_roots:
        ftp, ftp_host, ftp_error = connect_nitrado_ftp(config, timeout_seconds=timeout_seconds)
        if ftp_error:
            notes.append(ftp_error)
        else:
            notes.append(f"FTPS login succeeded on `{ftp_host}`, but the searched folders returned no listable entries.")
            try:
                ftp.quit()
            except Exception:
                pass

        headers = nitrado_api_headers(config)
        url = nitrado_api_service_url(config, "list")
        if not headers or not url:
            notes.append("Nitrado API token or service ID is missing.")
        else:
            try:
                response = requests.get(url, headers=headers, params={"dir": "/"}, timeout=timeout_seconds)
                notes.append(f"Nitrado API root list returned HTTP `{response.status_code}`.")
            except Exception as error:
                notes.append(f"Nitrado API root list failed: `{error}`.")

    return found, visible_roots, notes


WANDERING_DELIVERY_BRIDGE_CODE = r'''
string WanderingBotAttribute(string line, string attributeName)
{
    string marker = attributeName + "=\"";
    int startIndex = line.IndexOf(marker);
    if (startIndex < 0)
    {
        return "";
    }

    startIndex = startIndex + marker.Length();
    int endIndex = line.IndexOf("\"", startIndex);
    if (endIndex < 0)
    {
        return "";
    }

    return line.Substring(startIndex, endIndex - startIndex);
}

bool WanderingBotExcludedType(string itemName, string excludedTypes)
{
    if (excludedTypes == "")
    {
        return false;
    }

    TStringArray excluded = new TStringArray;
    excludedTypes.Split("|", excluded);

    foreach (string excludedType: excluded)
    {
        if (excludedType == itemName)
        {
            return true;
        }
    }

    return false;
}

void WanderingBotDeleteNearby(string itemName, vector spawnPos, float radius)
{
    array<Object> objects = new array<Object>;
    array<CargoBase> proxyCargos = new array<CargoBase>;
    GetGame().GetObjectsAtPosition(spawnPos, radius, objects, proxyCargos);

    foreach (Object obj: objects)
    {
        if (obj && obj.GetType() == itemName)
        {
            GetGame().ObjectDelete(obj);
            Print("[WANDERING BOT] Removed old vehicle before reset: " + itemName);
        }
    }
}

void WanderingBotDeleteAllVehicles(vector centerPos, float radius, string excludedTypes)
{
    array<Object> objects = new array<Object>;
    array<CargoBase> proxyCargos = new array<CargoBase>;
    GetGame().GetObjectsAtPosition(centerPos, radius, objects, proxyCargos);

    foreach (Object obj: objects)
    {
        if (!obj || !obj.IsInherited(CarScript))
        {
            continue;
        }

        string itemName = obj.GetType();
        if (WanderingBotExcludedType(itemName, excludedTypes))
        {
            Print("[WANDERING BOT] Vehicle reset skipped excluded type: " + itemName);
            continue;
        }

        GetGame().ObjectDelete(obj);
        Print("[WANDERING BOT] Removed vehicle during all-vehicle reset: " + itemName);
    }
}

vector WanderingBotRandomNearby(vector centerPos, float radius)
{
    if (radius <= 0)
    {
        return centerPos;
    }

    float offsetX = Math.RandomFloatInclusive(-radius, radius);
    float offsetZ = Math.RandomFloatInclusive(-radius, radius);
    return Vector(centerPos[0] + offsetX, centerPos[1], centerPos[2] + offsetZ);
}

void WanderingBotFillLoot(EntityAI container, string lootTypes)
{
    if (!container || lootTypes == "")
    {
        return;
    }

    TStringArray loot = new TStringArray;
    lootTypes.Split("|", loot);

    foreach (string lootType: loot)
    {
        if (lootType != "")
        {
            container.GetInventory().CreateInInventory(lootType);
        }
    }
}

void WanderingBotTryAttachment(EntityAI target, string attachmentType)
{
    if (!target || attachmentType == "")
    {
        return;
    }

    target.GetInventory().CreateAttachment(attachmentType);
}

void WanderingBotPrepareVehicle(EntityAI spawned, string condition)
{
    if (!spawned || !spawned.IsInherited(CarScript))
    {
        return;
    }

    if (condition == "no_parts")
    {
        return;
    }

    bool randomParts = condition == "random_parts";
    TStringArray commonParts = new TStringArray;
    commonParts.Insert("SparkPlug");
    commonParts.Insert("CarBattery");
    commonParts.Insert("CarRadiator");
    commonParts.Insert("TruckBattery");
    commonParts.Insert("HeadlightH7");
    commonParts.Insert("HeadlightH7");
    commonParts.Insert("HatchbackWheel");
    commonParts.Insert("HatchbackWheel");
    commonParts.Insert("HatchbackWheel");
    commonParts.Insert("HatchbackWheel");
    commonParts.Insert("CivSedanWheel");
    commonParts.Insert("CivSedanWheel");
    commonParts.Insert("CivSedanWheel");
    commonParts.Insert("CivSedanWheel");
    commonParts.Insert("Truck_01_Wheel");
    commonParts.Insert("Truck_01_Wheel");
    commonParts.Insert("Truck_01_WheelDouble");
    commonParts.Insert("Truck_01_WheelDouble");

    foreach (string partName: commonParts)
    {
        if (!randomParts || Math.RandomIntInclusive(0, 100) >= 45)
        {
            WanderingBotTryAttachment(spawned, partName);
        }
    }

    if (!randomParts)
    {
        CarScript car = CarScript.Cast(spawned);
        if (car)
        {
            car.Fill(CarFluid.FUEL, car.GetFluidCapacity(CarFluid.FUEL));
            car.Fill(CarFluid.OIL, car.GetFluidCapacity(CarFluid.OIL));
            car.Fill(CarFluid.BRAKE, car.GetFluidCapacity(CarFluid.BRAKE));
            car.Fill(CarFluid.COOLANT, car.GetFluidCapacity(CarFluid.COOLANT));
        }
    }
}

void WanderingBotSpawnGuards(string guardClass, vector centerPos, int guardCount, float guardRadius)
{
    if (guardClass == "" || guardCount <= 0)
    {
        return;
    }

    if (guardCount > 80)
    {
        guardCount = 80;
    }

    for (int guardIndex = 0; guardIndex < guardCount; guardIndex++)
    {
        vector guardPos = WanderingBotRandomNearby(centerPos, guardRadius);
        GetGame().CreateObject(guardClass, guardPos);
        Print("[WANDERING BOT] Airdrop guard spawned: " + guardClass);
    }
}

void WanderingBotSpawnEvent(string itemName, vector centerPos, int count, float radius, string lootTypes, string eventType, string vehicleCondition, string markerClass, string guardClass, int guardCount, float guardRadius)
{
    if (count <= 0)
    {
        count = 1;
    }

    if (count > 250)
    {
        count = 250;
    }

    if (markerClass != "")
    {
        GetGame().CreateObject(markerClass, centerPos);
        Print("[WANDERING BOT] Event marker spawned: " + markerClass);
    }

    for (int index = 0; index < count; index++)
    {
        vector spawnPos = WanderingBotRandomNearby(centerPos, radius);
        EntityAI spawned = EntityAI.Cast(GetGame().CreateObject(itemName, spawnPos));
        if (spawned)
        {
            if (eventType == "vehicle_spawn")
            {
                WanderingBotPrepareVehicle(spawned, vehicleCondition);
            }
            WanderingBotFillLoot(spawned, lootTypes);
            Print("[WANDERING BOT] Scenario spawned: " + itemName);
        }
    }

    WanderingBotSpawnGuards(guardClass, centerPos, guardCount, guardRadius);
}

void SpawnWanderingDeliveries()
{
    // WANDERING BOT BRIDGE v5 - supports deliveries, vehicle reset, and scenario events.
    string path = "$profile:custom/deliveries.xml";
    FileHandle file = OpenFile(path, FileMode.READ);

    if (!file)
    {
        Print("[WANDERING BOT] deliveries.xml not found");
        return;
    }

    string line;
    while (FGets(file, line) > 0)
    {
        if (line.Contains("<object"))
        {
            string itemName = WanderingBotAttribute(line, "name");
            string position = WanderingBotAttribute(line, "pos");
            string action = WanderingBotAttribute(line, "action");
            string radiusText = WanderingBotAttribute(line, "radius");
            string excludedTypes = WanderingBotAttribute(line, "exclude");
            string countText = WanderingBotAttribute(line, "count");
            string lootTypes = WanderingBotAttribute(line, "loot");
            string eventType = WanderingBotAttribute(line, "event_type");
            string vehicleCondition = WanderingBotAttribute(line, "vehicle_condition");
            string markerClass = WanderingBotAttribute(line, "marker_class");
            string guardClass = WanderingBotAttribute(line, "guard_class");
            string guardCountText = WanderingBotAttribute(line, "guard_count");
            string guardRadiusText = WanderingBotAttribute(line, "guard_radius");

            TStringArray posSplit = new TStringArray;
            position.Split(" ", posSplit);

            if (itemName != "" && posSplit.Count() >= 3)
            {
                vector spawnPos = Vector(
                    posSplit.Get(0).ToFloat(),
                    posSplit.Get(1).ToFloat(),
                    posSplit.Get(2).ToFloat()
                );

                if (action == "reset_vehicle")
                {
                    float radius = radiusText.ToFloat();
                    if (radius <= 0)
                    {
                        radius = 35;
                    }
                    WanderingBotDeleteNearby(itemName, spawnPos, radius);
                }
                else if (action == "reset_all_vehicles")
                {
                    float allRadius = radiusText.ToFloat();
                    if (allRadius <= 0)
                    {
                        allRadius = 22000;
                    }
                    WanderingBotDeleteAllVehicles(spawnPos, allRadius, excludedTypes);
                    continue;
                }
                else if (action == "spawn_event")
                {
                    int count = countText.ToInt();
                    float eventRadius = radiusText.ToFloat();
                    int guardCount = guardCountText.ToInt();
                    float guardRadius = guardRadiusText.ToFloat();
                    WanderingBotSpawnEvent(itemName, spawnPos, count, eventRadius, lootTypes, eventType, vehicleCondition, markerClass, guardClass, guardCount, guardRadius);
                    continue;
                }

                EntityAI spawned = EntityAI.Cast(GetGame().CreateObject(itemName, spawnPos));
                if (spawned)
                {
                    Print("[WANDERING BOT] Spawned: " + itemName);
                }
            }
        }
    }

    CloseFile(file);
}
'''


def find_enforce_function_block(text, function_name):
    match = re.search(rf"\bvoid\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{", text)
    if not match:
        return None

    depth = 0
    for index in range(match.end() - 1, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return match.start(), index + 1

    return None


def install_wandering_delivery_bridge(init_text):
    changed = False
    updated = init_text
    bridge_code = WANDERING_DELIVERY_BRIDGE_CODE.strip()

    if "WANDERING BOT BRIDGE v5" not in updated:
        block = find_enforce_function_block(updated, "SpawnWanderingDeliveries")
        if block:
            start, end = block
            helper_start = updated.rfind("string WanderingBotAttribute", 0, start)
            if helper_start >= 0:
                start = helper_start
            updated = updated[:start] + bridge_code + "\n\n" + updated[end:]
        elif "void SpawnWanderingDeliveries()" in updated:
            updated = updated.replace("void SpawnWanderingDeliveries()", bridge_code + "\n\nvoid SpawnWanderingDeliveries()", 1)
        else:
            main_match = re.search(r"\bvoid\s+main\s*\(", updated)
            if main_match:
                updated = updated[:main_match.start()] + bridge_code + "\n\n" + updated[main_match.start():]
            else:
                updated = updated.rstrip() + "\n\n" + bridge_code + "\n"
        changed = True

    elif "void SpawnWanderingDeliveries()" not in updated:
        main_match = re.search(r"\bvoid\s+main\s*\(", updated)
        if main_match:
            updated = updated[:main_match.start()] + bridge_code + "\n\n" + updated[main_match.start():]
        else:
            updated = updated.rstrip() + "\n\n" + bridge_code + "\n"
        changed = True

    if "SpawnWanderingDeliveries();" not in updated:
        weather_match = re.search(r"^.*MissionWeather\s*\([^;\n]*\)\s*;\s*$", updated, re.MULTILINE)
        if weather_match:
            insert_at = weather_match.end()
            updated = updated[:insert_at] + "\n    SpawnWanderingDeliveries();" + updated[insert_at:]
        else:
            main_open = re.search(r"\bvoid\s+main\s*\([^)]*\)\s*\{", updated)
            if main_open:
                insert_at = main_open.end()
                updated = updated[:insert_at] + "\n    SpawnWanderingDeliveries();" + updated[insert_at:]
            else:
                return updated, changed, "Could not find `main()` in init.c to insert the startup call."
        changed = True

    return updated, changed, None


def build_dayz_messages_xml(messages, interval_minutes):
    root = ET.Element("messages")
    for message in messages:
        item = ET.SubElement(root, "message")
        item.set("interval", str(max(1, int(interval_minutes))))
        item.text = str(message).strip()

    return ET.tostring(root, encoding="unicode")

# =========================================================
# DOWNLOAD ADM
# =========================================================

def download_latest_adm(
    guild_id,
    config,
    latest_log
):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    try:

        download_url = (
            f"https://api.nitrado.net/services/"
            f"{service_id}/gameservers/file_server/download"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        params = {
            "file": latest_log.get("path")
        }

        response = requests.get(
            download_url,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return False

        data = response.json()

        token_url = (
            data
            .get("data", {})
            .get("token", {})
            .get("url")
        )

        if not token_url:
            return False

        file_response = requests.get(token_url)

        adm_path = os.path.join(
            GUILD_DATA_FOLDER,
            f"{guild_id}.ADM"
        )

        with open(adm_path, "wb") as f:
            f.write(file_response.content)

        return True

    except Exception as error:

        print(error)

        return False

# =========================================================
# FEED EMBED STYLES
# =========================================================

def create_feed_embed(title, color, player=None, details=None, weapon=None, coords=None, guild_id=None):

    embed = discord.Embed(
        title=title,
        color=color
    )

    if player:
        embed.add_field(
            name="👤 Player",
            value=player,
            inline=True
        )

    if weapon:
        embed.add_field(
            name="🔫 Weapon",
            value=weapon,
            inline=True
        )

    if coords:
        map_link = build_izurvive_link(coords, guild_id)

        if map_link:
            coords_value = f"[🗺️ {coords}](<{map_link}>)"
        else:
            coords_value = coords

        embed.add_field(
            name="📍 Coordinates",
            value=coords_value,
            inline=False
        )

    if details:
        embed.add_field(
            name="📜 Event Details",
            value=f"```{details[:900]}```",
            inline=False
        )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Live DayZ Intelligence"
    )

    return style_embed(embed)

# =========================================================
# ADM PARSER
# =========================================================

async def parse_adm(guild_id, config):

    adm_path = os.path.join(
        GUILD_DATA_FOLDER,
        f"{guild_id}.ADM"
    )

    if not os.path.exists(adm_path):
        return

    with open(
        adm_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    channels = config.get("channels", {})

    killfeed_channel = bot.get_channel(
        channels.get("killfeed")
    )

    raid_channel = bot.get_channel(
        channels.get("raids")
    )

    build_channel = bot.get_channel(
        channels.get("building")
    )

    connect_channel = bot.get_channel(
        channels.get("connections")
    )

    disconnect_channel = bot.get_channel(
        channels.get("disconnects")
    )

    for raw_line in lines[-250:]:

        line = raw_line.strip()

        if not line:
            continue

        line_hash = stable_line_hash(line)

        ensure_guild_runtime(guild_id)

        if line_hash in processed_lines[guild_id]:
            continue

        remember_processed_line(guild_id, line_hash)

        # Parse the in-game event time from the ADM line ONCE per line.
        # Every embed dispatched off this line will use this timestamp so
        # Discord shows "when the event actually happened in-game", not
        # "when the bot got around to processing it". Falls back to "now"
        # if the line has no parseable HH:MM:SS prefix.
        event_time = extract_adm_event_time(line) or datetime.now(UTC)

        event_type = classify_event(line)

        if not event_type:
            if extract_adm_coords(line):
                ensure_guild_runtime(guild_id)
                remember_player_location_from_adm(guild_id, line)
                await check_radar_zones_for_adm(guild_id, config, "position", line)
            continue

        if event_type == "kill":
            kill_details = extract_pvp_kill_details(line)
            if not kill_details:
                continue
            if is_duplicate_pvp_kill(guild_id, kill_details):
                continue
            await process_cheat_check_from_kill(guild_id, config, kill_details, line)

        print(f"EVENT: {event_type} | {line}")

        ensure_guild_runtime(guild_id)
        remember_player_location_from_adm(guild_id, line)
        update_player_stats_from_adm(guild_id, event_type, line)
        save_player_stats()

        zone = get_zone_from_line(line)
        coords = extract_adm_coords(line)
        heat_mode = heatmap_mode_for_event(event_type)

        if heat_mode:
            increase_heat(guild_id, zone, heat_mode, coords)

        await check_radar_zones_for_adm(guild_id, config, event_type, line)
        await process_pve_progress_from_adm(guild_id, config, event_type, line)
        await send_special_adm_feed(guild_id, config, event_type, line, event_time=event_time)

        if event_type in [
            "flag_raise",
            "flag_lower",
            "cut",
            "bleedout",
            "suicide",
            "respawn",
            "packed",
            "placed"
        ]:
            continue

        # ================= CONNECT =================

        if event_type == "connect" and connect_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            online_players[guild_id].add(player_name)
            player_online_times[guild_id][player_name] = datetime.now(UTC)
            # ── 🪖 Squad-inbound alert: 5+ connects within 60s ────
            now_ts_conn = (event_time or datetime.now(UTC)).timestamp()
            conn_log = recent_connect_times.setdefault(guild_id, [])
            conn_log.append((now_ts_conn, player_name))
            # purge stale
            conn_log[:] = [
                (t, p) for (t, p) in conn_log
                if now_ts_conn - t <= SQUAD_INBOUND_WINDOW_SECONDS
            ]
            unique_recent = sorted({p for (_, p) in conn_log})
            if len(unique_recent) >= SQUAD_INBOUND_MIN_PLAYERS and killfeed_channel:
                # Only post once per window — track via the last-post ts
                last_post = recent_connect_times.get(f"_last_post_{guild_id}", 0)
                if now_ts_conn - last_post > SQUAD_INBOUND_WINDOW_SECONDS:
                    recent_connect_times[f"_last_post_{guild_id}"] = now_ts_conn
                    sq_embed = discord.Embed(
                        title="🪖 SQUAD INBOUND",
                        description=(
                            f"**{len(unique_recent)}** survivors just connected in under "
                            f"{SQUAD_INBOUND_WINDOW_SECONDS}s. Stay frosty."
                        ),
                        color=0x34495E,
                    )
                    sq_embed.add_field(
                        name="Connected",
                        value=", ".join(f"`{p}`" for p in unique_recent[:10]),
                        inline=False,
                    )
                    sq_embed.set_thumbnail(url=BOT_IMAGE)
                    sq_embed.set_footer(text="Wandering Bot Alpha — Squad Inbound")
                    sq_embed.timestamp = event_time or datetime.now(UTC)
                    try:
                        await killfeed_channel.send(embed=style_embed(sq_embed))
                    except Exception as squad_err:
                        print(f"[SQUAD INBOUND] post failed: {squad_err}")

            # Survival-streak: mark player alive today + announce milestones
            streak_entry = note_player_alive(guild_id, player_name, event_time=event_time)
            if streak_entry and killfeed_channel:
                milestone = get_streak_milestone(int(streak_entry.get("current_days", 0) or 0))
                if milestone:
                    try:
                        m_embed = discord.Embed(
                            title=f"🩸 SURVIVAL MILESTONE — {milestone} DAYS",
                            description=f"**{player_name}** has stayed alive for **{milestone}** consecutive days. Loot accordingly.",
                            color=0x16A085,
                        )
                        m_embed.set_thumbnail(url=BOT_IMAGE)
                        m_embed.set_footer(text="Wandering Bot Alpha — Survival Streak")
                        m_embed.timestamp = event_time or datetime.now(UTC)
                        await killfeed_channel.send(embed=style_embed(m_embed))
                    except Exception as milestone_err:
                        print(f"[STREAK] milestone post failed: {milestone_err}")

            embed = discord.Embed(
                title="🟢 SURVIVOR CONNECTED",
                color=0x2ECC71
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Connection Feed"
            )

            embed.timestamp = event_time

            await connect_channel.send(embed=embed)

            # Welcome channel messaging for in-game connects removed.
            # Welcome messages are only for Discord member joins.

        # ================= DISCONNECT =================

        elif event_type == "disconnect" and disconnect_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            # ─── 💀 Session recap on disconnect ───────────────────
            session_started = player_online_times[guild_id].get(player_name)

            if player_name in online_players[guild_id]:
                online_players[guild_id].remove(player_name)

            if player_name in player_online_times[guild_id]:
                del player_online_times[guild_id][player_name]

            embed = discord.Embed(
                title="🔴 SURVIVOR DISCONNECTED",
                color=0xE74C3C
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=False
            )

            if session_started:
                try:
                    duration = int((datetime.now(UTC) - session_started).total_seconds())
                    if duration >= 60:
                        embed.add_field(
                            name="⏱️ Session Length",
                            value=format_duration(duration),
                            inline=True,
                        )
                except Exception:
                    pass
            # Show player's current alive-streak summary if non-trivial
            spree_entry = (alive_streaks.get(str(guild_id)) or {}).get(player_name) or {}
            current_spree = int(spree_entry.get("current_spree", 0) or 0)
            best_spree = int(spree_entry.get("best_spree", 0) or 0)
            if current_spree >= 1 or best_spree >= 3:
                embed.add_field(
                    name="🔫 Kill Spree",
                    value=f"This life: **{current_spree}** • Personal best: **{best_spree}**",
                    inline=True,
                )

            if coords:

                map_link = build_izurvive_link(coords, guild_id)

                if map_link:

                    embed.add_field(
                        name="📍 Last Known Location",
                        value=f"[🔵 Open Map](<{map_link}>)",
                        inline=False
                    )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Disconnect Feed"
            )

            embed.timestamp = event_time

            disconnect_channel = bot.get_channel(
                channels.get("disconnects")
            )

            if disconnect_channel:
                await disconnect_channel.send(embed=embed)

        # ================= BUILD =================

        elif event_type == "build" and build_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else "Unknown"
            )

            action = "Building"
            object_name = "Structure"
            tool_used = "Tool"

            if "placed" in line.lower():

                action_match = re.search(
                    r'placed ([^<]+)',
                    line,
                    re.IGNORECASE
                )

                if action_match:
                    object_name = action_match.group(1).strip()

                action = "Placed"

            elif "built" in line.lower():

                build_match = re.search(
                    r'Built ([^ ]+)',
                    line,
                    re.IGNORECASE
                )

                if build_match:
                    object_name = build_match.group(1).replace("_", " ").title()

                tool_match = re.search(
                    r'with ([^ ]+)',
                    line,
                    re.IGNORECASE
                )

                if tool_match:
                    tool_used = tool_match.group(1)

                action = "Built"

            embed = discord.Embed(
                title="🏗️ BUILDING ACTIVITY",
                color=0xF1C40F
            )

            embed.add_field(
                name="👤 Survivor",
                value=player_name,
                inline=True
            )

            embed.add_field(
                name="🛠️ Action",
                value=action,
                inline=True
            )

            embed.add_field(
                name="🏗️ Structure",
                value=object_name,
                inline=False
            )

            if tool_used != "Tool":

                embed.add_field(
                    name="🔨 Tool",
                    value=tool_used,
                    inline=True
                )

            map_link = build_izurvive_link(coords, guild_id)

            if map_link:

                embed.add_field(
                    name="📍 Location",
                    value=f"[🔵 Open Map](<{map_link}>)",
                    inline=False
                )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Building Intelligence"
            )

            embed.timestamp = event_time

            await build_channel.send(embed=embed)

        # ================= RAID =================

        elif event_type == "raid" and raid_channel:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player_name = (
                player_match.group(1)
                if player_match else "Unknown"
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            action = "Raid Activity"
            structure = "Base Structure"
            tool_used = "Unknown"

            dismantle_match = re.search(
                r'Dismantled ([^ ]+(?: [^ ]+)*) from ([^ ]+)',
                line,
                re.IGNORECASE
            )

            if dismantle_match:
                action = dismantle_match.group(1)
                structure = dismantle_match.group(2)

            tool_match = re.search(
                r'with ([^ ]+)',
                line,
                re.IGNORECASE
            )

            if tool_match:
                tool_used = tool_match.group(1)

            embed = discord.Embed(
                title="🚨 RAID DETECTED",
                color=0xFF0000
            )

            embed.add_field(
                name="👤 Raider",
                value=player_name,
                inline=True
            )

            embed.add_field(
                name="🧨 Action",
                value=action,
                inline=True
            )

            embed.add_field(
                name="🏚️ Structure",
                value=structure,
                inline=False
            )

            embed.add_field(
                name="🔨 Tool",
                value=tool_used,
                inline=True
            )

            if coords:

                map_link = build_izurvive_link(coords, guild_id)

                if map_link:

                    embed.add_field(
                        name="📍 Raid Location",
                        value=f"[🔵 Open Map](<{map_link}>)",
                        inline=False
                    )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Raid Intelligence"
            )

            embed.timestamp = event_time

            await raid_channel.send(embed=embed)

        # ================= PVE HUNTING =================

        elif event_type == "animal_kill":

            hunting_channel = bot.get_channel(
                channels.get("pve_hunting")
            )

            if not hunting_channel:
                guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
                if guild:
                    created = await ensure_pve_channels(guild, config)
                    hunting_channel = created.get("pve_hunting")

            if hunting_channel:

                player_name = extract_player_name(line)
                coords = extract_adm_coords(line)
                animal_match = re.search(
                    r"(Animal_[A-Za-z0-9_]+|bear|wolf|deer|stag|boar|cow|sheep|goat|chicken|hen|rooster|fox|hare)",
                    line,
                    re.IGNORECASE
                )
                animal_name = animal_match.group(1).replace("Animal_", "").replace("_", " ").title() if animal_match else "Animal"

                embed = discord.Embed(
                    title="🏹 PVE HUNTING ACTIVITY",
                    color=0x2ECC71
                )

                embed.add_field(name="Hunter", value=player_name, inline=True)
                embed.add_field(name="Target", value=animal_name, inline=True)

                if coords:
                    x, z, _ = split_adm_coords(coords)
                    coord_lines = []
                    if x:
                        coord_lines.append(f"X: {x}")
                    if z:
                        coord_lines.append(f"Z: {z}")
                    if coord_lines:
                        embed.add_field(name="Location", value="\n".join(coord_lines), inline=False)

                    map_link = build_izurvive_link(coords, guild_id)
                    if map_link:
                        embed.add_field(name="Map", value=f"[Open Map](<{map_link}>)", inline=False)

                embed.set_thumbnail(url=BOT_IMAGE)
                embed.set_footer(text="Wandering Bot Alpha - PVE Hunting Feed")
                await hunting_channel.send(embed=style_embed(embed))

                # ================= ZOMBIES =================

        elif event_type == "zombie_hit":

            zombie_channel = bot.get_channel(
                channels.get("zombie_feed")
            )

            if zombie_channel:

                player_match = re.search(
                    r'Player "([^"]+)"',
                    line
                )

                player_name = (
                    player_match.group(1)
                    if player_match else "Unknown"
                )

                embed = discord.Embed(
                    title="🧟 INFECTED ATTACK",
                    description=f"**{player_name}** was attacked by infected.",
                    color=0x2ECC71
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot • Zombie Activity"
                )

                embed.timestamp = event_time

                await zombie_channel.send(
                    embed=style_embed(embed)
                )

        elif event_type == "zombie_kill":

            zombie_channel = bot.get_channel(
                channels.get("zombie_feed")
            )

            if zombie_channel:

                player_match = re.search(
                    r'Player "([^"]+)"',
                    line
                )

                player_name = (
                    player_match.group(1)
                    if player_match else "Unknown"
                )

                embed = discord.Embed(
                    title="☠️ KILLED BY INFECTED",
                    description=f"**{player_name}** was overwhelmed by zombies.",
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot • Zombie Fatality"
                )

                embed.timestamp = event_time

                await zombie_channel.send(
                    embed=style_embed(embed)
                )

        elif event_type == "unconscious":

            unconscious_channel = bot.get_channel(
                channels.get("unconscious_feed")
            )

            if unconscious_channel:

                player_match = re.search(
                    r'Player "([^"]+)"',
                    line
                )

                player_name = (
                    player_match.group(1)
                    if player_match else "Unknown"
                )

                coords_match = re.search(
                    r'pos=<([^>]+)>',
                    line
                )

                coords = (
                    coords_match.group(1)
                    if coords_match else None
                )

                embed = discord.Embed(
                    title="UNCONSCIOUS SURVIVOR",
                    description=f"**{player_name}** is unconscious.",
                    color=0xE67E22
                )

                if coords:
                    map_link = build_izurvive_link(coords, guild_id)
                    if map_link:
                        embed.add_field(
                            name="Last Known Location",
                            value=f"[Open Map](<{map_link}>)",
                            inline=False
                        )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Alpha - Medical Feed"
                )

                embed.timestamp = event_time

                await unconscious_channel.send(
                    embed=style_embed(embed)
                )
        # ================= VEHICLE KILL =================

        elif event_type == "vehicle_kill" and killfeed_channel:
            vk = extract_vehicle_kill_details(line)
            if vk:
                v_victim = vk["victim"]
                v_vehicle = vk.get("vehicle", "Vehicle")
                v_coords = vk.get("coords")
                v_zone = get_zone_from_line(line) or "Unknown"

                add_player_stat(guild_id, v_victim, "vehicle_deaths")
                add_player_stat(guild_id, v_victim, "deaths")
                save_player_stats()
                reset_player_streak(guild_id, v_victim, event_time=event_time)
                end_alive_streak(guild_id, v_victim)
                record_daily_kill(
                    guild_id,
                    killer=f"🚗 {v_vehicle}",
                    victim=v_victim,
                    weapon=v_vehicle,
                    distance=vk.get("distance", 0),
                    headshot=False,
                    zone=v_zone,
                    vehicle=True,
                    event_time=event_time,
                )

                v_embed = discord.Embed(
                    title="🚗💥 VEHICLE KILL",
                    description=f"**{v_victim}** got run over by a **{v_vehicle}**.",
                    color=0xE67E22,
                )
                v_embed.add_field(name="Victim", value=v_victim, inline=True)
                v_embed.add_field(name="Vehicle", value=v_vehicle, inline=True)
                if vk.get("distance"):
                    v_embed.add_field(name="Impact Distance", value=f"{vk['distance']}m", inline=True)
                v_embed.add_field(name="Zone", value=v_zone, inline=True)
                if v_coords:
                    map_link = build_izurvive_link(v_coords, guild_id)
                    if map_link:
                        v_embed.add_field(name="Location", value=f"[Open Map](<{map_link}>)", inline=False)
                v_embed.set_thumbnail(url=BOT_IMAGE)
                v_embed.set_footer(text="Wandering Bot Alpha — Vehicle Carnage Tracker")
                v_embed.timestamp = event_time or datetime.now(UTC)
                try:
                    await killfeed_channel.send(embed=style_embed(v_embed))
                except Exception:
                    pass

        # ================= KILLFEED =================

        elif event_type == "kill" and killfeed_channel:

            kill_details = extract_pvp_kill_details(line)

            if kill_details:

                killer = kill_details["killer"]
                victim = kill_details["victim"]
                weapon = kill_details.get("weapon", "Unknown")
                distance = float(kill_details.get("distance", 0) or 0)
                coords = kill_details.get("coords")
                is_headshot = bool(kill_details.get("headshot"))

                embed = discord.Embed(
                    title="💥 HEADSHOT — PLAYER KILL" if is_headshot else "PLAYER KILL",
                    color=0xE74C3C if is_headshot else 0x992D22
                )

                embed.add_field(
                    name="Killer",
                    value=killer,
                    inline=True
                )

                embed.add_field(
                    name="Victim",
                    value=victim,
                    inline=True
                )

                if distance > 0:

                    embed.add_field(
                        name="Distance",
                        value=f"{distance}m",
                        inline=True
                    )

                embed.add_field(
                    name="Weapon",
                    value=weapon,
                    inline=False
                )

                if kill_details.get("ammo"):
                    embed.add_field(
                        name="Ammo",
                        value=kill_details["ammo"],
                        inline=True
                    )

                if is_headshot:
                    embed.add_field(
                        name="Hit Zone",
                        value=f"💥 {kill_details.get('hit_location', 'Head')}",
                        inline=True
                    )

                if coords:

                    map_link = build_izurvive_link(coords, guild_id)

                    if map_link:

                        embed.add_field(
                            name="Kill Location",
                            value=f"[Open Map](<{map_link}>)",
                            inline=False
                        )

                # AI death roast — opt-in per guild. Fire-and-await with
                # internal timeout so we never block the killfeed for
                # more than AI_ROAST_TIMEOUT_SECONDS. Always falls back
                # to a static one-liner if the LLM is unavailable.
                if guild_roasts_enabled(guild_id):
                    try:
                        roast = await generate_death_roast(
                            killer, victim, weapon, distance,
                            headshot=is_headshot,
                            tone=guild_roast_tone(guild_id),
                        )
                    except Exception as roast_error:
                        print(f"[AI ROAST] unexpected error: {roast_error}")
                        roast = None
                    if roast:
                        embed.add_field(
                            name="📣 Killfeed Says",
                            value=f"*{roast}*",
                            inline=False
                        )

                # ─── Bounty claim ─────────────────────────────────────
                bounty_claim = claim_bounty_on_kill(guild_id, killer, victim)
                if bounty_claim:
                    embed.add_field(
                        name="💰 BOUNTY CLAIMED",
                        value=(
                            f"**{killer}** collected **{bounty_claim['claimed_amount']:,} "
                            f"{bounty_claim.get('currency', BOUNTY_CURRENCY)}** for hunting **{victim}**."
                        ),
                        inline=False
                    )

                # ─── Nemesis tracking ────────────────────────────────
                nemesis_count = record_nemesis(guild_id, killer, victim)
                if nemesis_count in NEMESIS_MILESTONES:
                    embed.add_field(
                        name="👹 RIVALRY HEATED UP",
                        value=(
                            f"**{killer}** has now killed **{victim}** "
                            f"**{nemesis_count}** times. This is personal."
                        ),
                        inline=False,
                    )

                # ─── Squad detection ─────────────────────────────────
                # If another distinct killer scored a kill in this zone
                # within SQUAD_WINDOW_SECONDS, flag the squad-mates.
                zone_now = get_zone_from_line(line) or "Unknown"
                now_ts_for_squad = (event_time or datetime.now(UTC)).timestamp()
                ev_deque = recent_kill_events.setdefault(guild_id, [])
                # purge stale
                ev_deque[:] = [e for e in ev_deque if now_ts_for_squad - e.get("ts", 0) <= SQUAD_WINDOW_SECONDS]
                squad_mates = [
                    e["killer"] for e in ev_deque
                    if e.get("zone") == zone_now and e.get("killer") != killer
                ]
                ev_deque.append({
                    "ts": now_ts_for_squad,
                    "killer": killer,
                    "victim": victim,
                    "zone": zone_now,
                    "weapon": weapon,
                })
                # cap memory
                if len(ev_deque) > 50:
                    del ev_deque[:-50]
                if len(set(squad_mates)) >= (SQUAD_MIN_MATES - 1):
                    mates_unique = sorted(set(squad_mates))
                    embed.add_field(
                        name="🛡️ POSSIBLE SQUAD",
                        value=", ".join([killer] + mates_unique) + f"  *(same zone within {SQUAD_WINDOW_SECONDS}s)*",
                        inline=False,
                    )

                # ─── Per-killer longest-shot tracking ────────────────
                killer_stats = ensure_player_stats_record(guild_id, killer)
                if killer_stats and distance > float(killer_stats.get("longest_shot_distance", 0) or 0):
                    killer_stats["longest_shot_distance"] = distance
                    killer_stats["longest_shot_weapon"] = weapon
                    killer_stats["longest_shot_victim"] = victim
                if is_headshot:
                    add_player_stat(guild_id, killer, "headshots")
                save_player_stats()

                # ─── Streaks: killer alive, victim reset ─────────────
                note_player_alive(guild_id, killer, event_time=event_time)
                broken_days = reset_player_streak(guild_id, victim, event_time=event_time)
                if broken_days and broken_days >= 7:
                    embed.add_field(
                        name="🩸 Streak Broken",
                        value=f"**{victim}** had survived **{broken_days}** day(s).",
                        inline=True,
                    )

                # ─── 🔫 Alive-streak (kills since last death) ────────
                killer_spree = bump_alive_streak(guild_id, killer, event_time=event_time)
                ended_spree, best_spree = end_alive_streak(guild_id, victim)
                if killer_spree >= 5:
                    embed.add_field(
                        name="🔫 ON A KILL SPREE",
                        value=f"**{killer}** is on a **{killer_spree}-kill** spree without dying.",
                        inline=True,
                    )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Alpha - PvP Intelligence"
                )

                embed.timestamp = event_time

                killfeed_message = await killfeed_channel.send(
                    embed=embed
                )
                # ─── Killfeed reactions for engagement ──────────────
                for emoji in ("🔥", "🎯", "💀"):
                    try:
                        await killfeed_message.add_reaction(emoji)
                    except Exception:
                        break  # missing-perms or rate-limit; skip rest
                # ─── 🔫 Spree-ended embed if victim was on 3+ ────────
                if ended_spree >= 3:
                    spree_embed = discord.Embed(
                        title=f"🔫 {ended_spree}-KILL SPREE ENDED",
                        description=(
                            f"**{killer}** ended **{victim}**'s **{ended_spree}-kill** spree.\n"
                            f"Victim's personal best: **{best_spree} kills**."
                        ),
                        color=0xC0392B,
                    )
                    spree_embed.set_thumbnail(url=BOT_IMAGE)
                    spree_embed.set_footer(text="Wandering Bot Alpha — Spree Watch")
                    spree_embed.timestamp = event_time or datetime.now(UTC)
                    try:
                        await killfeed_channel.send(embed=style_embed(spree_embed))
                    except Exception:
                        pass

                # ─── 🎯 Daily challenge progress ─────────────────────
                completed_challenge = progress_daily_challenge(
                    guild_id, killer,
                    kill_distance=distance, headshot=is_headshot,
                    vehicle_kill=False, rampage_size=0,
                    event_time=event_time,
                )
                if completed_challenge and killfeed_channel:
                    # Reward in linked-user's wallet (if a Discord member is linked)
                    try:
                        reward = int(completed_challenge.get("reward", 0) or 0)
                        linked_user_id = linked_user_id_for_player(killer)
                        if linked_user_id and reward > 0:
                            wallet = wallets.setdefault(linked_user_id, {
                                "name": linked_players.get(linked_user_id, {}).get("discord_name", killer),
                                "balance": 0,
                                "daily_transactions": 0,
                            })
                            wallet["balance"] = int(wallet.get("balance", 0) or 0) + reward
                            save_wallets()
                    except Exception as wallet_err:
                        print(f"[CHALLENGE REWARD] failed: {wallet_err}")
                    cc_embed = discord.Embed(
                        title=f"🎯 DAILY CHALLENGE COMPLETE — {completed_challenge.get('name', '?')}",
                        description=(
                            f"**{killer}** finished today's challenge: *{completed_challenge.get('desc', '')}*\n"
                            f"Reward: **{int(completed_challenge.get('reward', 0)):,} Pennies**"
                        ),
                        color=0x2ECC71,
                    )
                    cc_embed.set_thumbnail(url=BOT_IMAGE)
                    cc_embed.set_footer(text="Wandering Bot Alpha — Daily Challenges")
                    cc_embed.timestamp = event_time or datetime.now(UTC)
                    try:
                        await killfeed_channel.send(embed=style_embed(cc_embed))
                    except Exception:
                        pass

                # ─── 🏆 Achievement evaluation ───────────────────────
                newly = evaluate_achievements_for_player(
                    guild_id, killer,
                    just_kill=True,
                    distance=distance,
                    headshot=is_headshot,
                    claimed_bounty=bool(bounty_claim),
                    nemesis_count=nemesis_count,
                )
                if newly:
                    await announce_achievements(killfeed_channel, guild_id, killer, newly)

                # Auto-thread on epic single-shot kills (300m+ headshot)
                if (
                    is_headshot
                    and distance >= LONGSHOT_ANNOUNCE_METERS
                    and isinstance(killfeed_channel, discord.TextChannel)
                ):
                    try:
                        await killfeed_message.create_thread(
                            name=f"💥 {killer} • {distance:.0f}m headshot"[:95],
                            auto_archive_duration=1440,
                        )
                    except Exception as thread_error:
                        print(f"[THREAD] headshot thread failed: {thread_error}")

                guild_longshot_records = longshot_records.get(guild_id, [])
                current_record_distance = float(
                    guild_longshot_records[0].get("distance", 0)
                ) if guild_longshot_records else 0

                is_new_record = distance > current_record_distance
                is_longshot = distance >= LONGSHOT_ANNOUNCE_METERS

                if is_longshot:
                    # Persist every 300m+ shot — not just the single
                    # current server record. This is what makes the
                    # leaderboard actually populate.
                    record_longshot(guild_id, {
                        "killer": killer,
                        "victim": victim,
                        "distance": distance,
                        "weapon": weapon,
                        "coords": coords,
                        "headshot": is_headshot,
                        "time": event_time.isoformat() if event_time else datetime.now(UTC).isoformat(),
                    })

                # ─── First-blood / Final-kill of the day ─────────────
                today_key = event_time.date().isoformat() if event_time else datetime.now(UTC).date().isoformat()
                fb_record = first_blood_today.get(guild_id) or {}
                if fb_record.get("date") != today_key:
                    first_blood_today[guild_id] = {
                        "date": today_key,
                        "killer": killer,
                        "victim": victim,
                        "weapon": weapon,
                        "distance": distance,
                        "coords": coords,
                        "time": (event_time or datetime.now(UTC)).isoformat(),
                    }
                    save_first_blood()
                    if killfeed_channel:
                        fb_embed = discord.Embed(
                            title="🥇 FIRST BLOOD OF THE DAY",
                            description=f"**{killer}** opens the day with a kill on **{victim}** at the worst possible moment for everyone else.",
                            color=0xC0392B,
                        )
                        fb_embed.add_field(name="Weapon", value=weapon, inline=True)
                        if distance > 0:
                            fb_embed.add_field(name="Distance", value=f"{distance}m", inline=True)
                        fb_embed.set_thumbnail(url=BOT_IMAGE)
                        fb_embed.set_footer(text="Wandering Bot Alpha — First Blood Tracker")
                        fb_embed.timestamp = event_time or datetime.now(UTC)
                        try:
                            await killfeed_channel.send(embed=style_embed(fb_embed))
                        except Exception:
                            pass

                # Always update final-kill (last kill seen for this date)
                final_kill_today[guild_id] = {
                    "date": today_key,
                    "killer": killer,
                    "victim": victim,
                    "weapon": weapon,
                    "distance": distance,
                    "coords": coords,
                    "time": (event_time or datetime.now(UTC)).isoformat(),
                }
                save_first_blood()

                # ─── Daily recap aggregate ───────────────────────────
                record_daily_kill(
                    guild_id,
                    killer=killer,
                    victim=victim,
                    weapon=weapon,
                    distance=distance,
                    headshot=is_headshot,
                    zone=zone_now,
                    vehicle=False,
                    event_time=event_time,
                )

                # ─── Multi-kill / Rampage detection ──────────────────
                now_ts = (event_time or datetime.now(UTC)).timestamp()
                guild_kill_log = recent_kills_by_killer.setdefault(guild_id, {})
                killer_kills = guild_kill_log.setdefault(killer, [])
                # purge stale entries outside the rolling window
                killer_kills[:] = [
                    k for k in killer_kills
                    if now_ts - k.get("ts", 0) <= RAMPAGE_WINDOW_SECONDS
                ]
                killer_kills.append({"ts": now_ts, "victim": victim, "weapon": weapon})
                streak_size = len(killer_kills)
                # Track personal-best multikill regardless of whether we
                # announce it.
                k_stats = ensure_player_stats_record(guild_id, killer)
                if k_stats and streak_size > int(k_stats.get("multikill_best", 0) or 0):
                    k_stats["multikill_best"] = streak_size
                    save_player_stats()
                # Only post on exact thresholds 3, 4, 5+ to avoid spam
                if streak_size >= RAMPAGE_MIN_KILLS and killfeed_channel:
                    streak_titles = {
                        3: ("🔥 TRIPLE KILL", 0xE67E22),
                        4: ("💥 QUAD KILL", 0xE74C3C),
                        5: ("🔥💥 RAMPAGE — 5 KILLS", 0xC0392B),
                    }
                    title, color = streak_titles.get(streak_size, (f"💀 UNSTOPPABLE — {streak_size} KILLS", 0x8E44AD))
                    if streak_size == RAMPAGE_MIN_KILLS:
                        # First time hitting a "rampage", count it
                        add_player_stat(guild_id, killer, "rampages")
                        save_player_stats()
                        # Progress rampage daily-challenge
                        try:
                            cc = progress_daily_challenge(
                                guild_id, killer, rampage_size=streak_size, event_time=event_time
                            )
                            if cc:
                                cc_embed = discord.Embed(
                                    title=f"🎯 DAILY CHALLENGE COMPLETE — {cc.get('name', '?')}",
                                    description=f"**{killer}** finished today's challenge: *{cc.get('desc', '')}*",
                                    color=0x2ECC71,
                                )
                                cc_embed.set_thumbnail(url=BOT_IMAGE)
                                cc_embed.set_footer(text="Wandering Bot Alpha — Daily Challenges")
                                cc_embed.timestamp = event_time or datetime.now(UTC)
                                await killfeed_channel.send(embed=style_embed(cc_embed))
                        except Exception:
                            pass
                    desc_lines = [
                        f"**{killer}** is on a tear — **{streak_size}** kills in under {RAMPAGE_WINDOW_SECONDS} seconds.",
                        "",
                        "**Victims:**",
                    ]
                    for k in killer_kills[-streak_size:]:
                        desc_lines.append(f"• {k['victim']} ({k['weapon']})")
                    streak_embed = discord.Embed(
                        title=title,
                        description="\n".join(desc_lines),
                        color=color,
                    )
                    streak_embed.set_thumbnail(url=BOT_IMAGE)
                    streak_embed.set_footer(text=f"Wandering Bot Alpha — Multi-Kill Window {RAMPAGE_WINDOW_SECONDS}s")
                    streak_embed.timestamp = event_time or datetime.now(UTC)
                    try:
                        streak_msg = await killfeed_channel.send(embed=style_embed(streak_embed))
                        # Auto-thread on serious rampages so survivors can
                        # talk it out without spamming killfeed.
                        if (
                            streak_size >= THREAD_ON_RAMPAGE_KILLS
                            and isinstance(killfeed_channel, discord.TextChannel)
                        ):
                            try:
                                await streak_msg.create_thread(
                                    name=f"🔥 {killer}'s rampage ({streak_size} kills)"[:95],
                                    auto_archive_duration=60,
                                )
                            except Exception as thread_error:
                                print(f"[THREAD] rampage thread failed: {thread_error}")
                    except Exception:
                        pass

                if is_longshot or is_new_record:

                    longshot_channel = bot.get_channel(
                        channels.get("longshots")
                    )

                    if longshot_channel:

                        longshot_embed = discord.Embed(
                            title="NEW SERVER LONGSHOT RECORD" if is_new_record else "LONGSHOT CONFIRMED",
                            description=(
                                f"{killer} dropped {victim} from {distance}m."
                            ),
                            color=0xF1C40F
                        )

                        longshot_embed.add_field(
                            name="Distance",
                            value=f"{distance}m",
                            inline=True
                        )

                        longshot_embed.add_field(
                            name="Weapon",
                            value=weapon,
                            inline=True
                        )

                        longshot_embed.add_field(
                            name="Victim",
                            value=victim,
                            inline=True
                        )

                        if coords:

                            map_link = build_izurvive_link(coords, guild_id)

                            if map_link:

                                longshot_embed.add_field(
                                    name="Kill Location",
                                    value=f"[Open Map](<{map_link}>)",
                                    inline=False
                                )

                        longshot_embed.set_thumbnail(url=BOT_IMAGE)

                        longshot_embed.set_footer(
                            text=f"Wandering Bot Alpha - Longshot Tracking - Threshold {LONGSHOT_ANNOUNCE_METERS}m"
                        )

                        longshot_embed.timestamp = event_time

                        ls_msg = await longshot_channel.send(
                            embed=style_embed(longshot_embed)
                        )
                        # Thread on epic 500m+ shots
                        if (
                            distance >= THREAD_ON_LONGSHOT_METERS
                            and isinstance(longshot_channel, discord.TextChannel)
                        ):
                            try:
                                await ls_msg.create_thread(
                                    name=f"🎯 {killer} • {distance:.0f}m on {victim}"[:95],
                                    auto_archive_duration=1440,
                                )
                            except Exception as thread_error:
                                print(f"[THREAD] longshot thread failed: {thread_error}")

# =========================================================
# ADM LOOP
# =========================================================

async def refresh_adm_for_guild(guild_id, config, *, force=False):

    guild_id = str(guild_id)

    # Per-guild lock prevents two concurrent ADM scans from racing each
    # other and posting the same line twice before either has marked it
    # as processed. Concurrent triggers used to come from: adm_loop (every
    # 3 min), on_ready re-firing on reconnect, !restartadm, /forcerefresh.
    lock = adm_scan_locks.setdefault(guild_id, asyncio.Lock())
    if lock.locked():
        return False, "ADM scan already in progress for this guild"

    async with lock:
        return await _refresh_adm_for_guild_locked(guild_id, config, force=force)


async def _refresh_adm_for_guild_locked(guild_id, config, *, force=False):

    ensure_guild_runtime(guild_id)

    if is_showcase_guild(guild_id):
        return False, "Showcase guild skipped; no ADM setup needed"

    if force:
        processed_lines[guild_id] = OrderedDict()
        save_processed_adm_lines()

    required_keys = ["nitrado_token", "service_id", "nitrado_user", "ftp_user", "ftp_password"]
    missing = [key for key in required_keys if not config.get(key)]

    if missing:
        return False, f"Missing setup values: {', '.join(missing)}"

    print(f"[ADM SEARCH] Searching latest ADM for {guild_display_name(guild_id)} ({guild_id})")

    latest_log = await asyncio.to_thread(
        ping_latest_adm_log,
        config
    )

    if not latest_log:
        return False, "No ADM log found"

    success = await asyncio.to_thread(
        download_latest_adm,
        guild_id,
        config,
        latest_log
    )

    if not success:
        return False, "ADM download failed"

    await parse_adm(
        guild_id,
        config
    )

    print(f"[ADM SEARCH] New ADM processed for {guild_display_name(guild_id)} ({guild_id})")
    return True, "ADM feed refreshed"


def guild_display_name(guild_id):
    guild_id = str(guild_id)
    guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None

    if guild:
        return guild.name

    return guild_configs.get(guild_id, {}).get("guild_name", guild_id)


def log_adm_protocol_results(results, label="ADM PROTOCOL"):
    if not results:
        print(f"[{label}] No active configured guilds to scan.")
        return

    for result_guild_id, result in results.items():
        success, message = result
        status = "OK" if success else "WAITING"
        print(f"[{label}] {guild_display_name(result_guild_id)} ({result_guild_id}) -> {status}: {message}")


async def refresh_adm_feeds(guild_id=None, *, force=False):
    results = {}

    if guild_id:
        guild_id = str(guild_id)

        if not is_active_guild(guild_id):
            return {guild_id: (False, "Bot is not in this guild anymore")}

        config = guild_configs.get(guild_id)
        if not config:
            return {guild_id: (False, "Guild is not setup yet")}

        results[guild_id] = await refresh_adm_for_guild(
            guild_id,
            config,
            force=force
        )
        return results

    for configured_guild_id, config in active_guild_config_items():
        try:
            results[configured_guild_id] = await refresh_adm_for_guild(
                configured_guild_id,
                config,
                force=force
            )
        except Exception as error:
            results[configured_guild_id] = (False, str(error))

    return results


@tasks.loop(minutes=3)
async def adm_loop():

    for guild_id, config in active_guild_config_items():

        try:
            success, message = await refresh_adm_for_guild(guild_id, config)

            if success:
                print(f"[ADM LOOP] {guild_display_name(guild_id)} ({guild_id}) -> OK: {message}")
            else:
                print(f"[ADM LOOP] {guild_display_name(guild_id)} ({guild_id}) -> WAITING: {message}")

        except Exception as error:

            print(f"[ADM LOOP ERROR] {guild_id}: {error}")


@tasks.loop(minutes=5)
async def temp_ban_expiry_loop():
    try:
        await process_temp_ban_expiries()
    except Exception as error:
        print(f"TEMP BAN LOOP ERROR: {error}")

# =========================================================
# SWEAR JAR
# =========================================================

@bot.event
async def on_member_join(member):

    guild_id = str(member.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    # ── Autonomous showcase welcome ──────────────────────
    if is_showcase_guild(guild_id):
        showcase_welcome_channel = None
        for key in ("general_chat", "welcome"):
            ch_id = channels.get(key)
            if ch_id:
                showcase_welcome_channel = bot.get_channel(ch_id)
                if showcase_welcome_channel:
                    break

        if not showcase_welcome_channel:
            for ch in member.guild.text_channels:
                if ch.permissions_for(member.guild.me).send_messages:
                    showcase_welcome_channel = ch
                    break

        if showcase_welcome_channel:
            welcome_text = random.choice(SHOWCASE_WELCOME_MESSAGES_EXTENDED)
            embed = discord.Embed(
                title="🤖 NEW ARRIVAL DETECTED",
                description=(
                    f"{member.mention}\n\n{welcome_text}\n\n"
                    "💬 Say `hi` to get started. Ask me to generate an image, explain a feature, or just chat.\n"
                    "📻 This server is run by the bot. The owner is here as backup only."
                ),
                color=0x9B59B6
            )
            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot • Autonomous Showcase • Fully bot-managed server")
            await showcase_welcome_channel.send(embed=style_embed(embed))

            # Generate a welcome image if OpenAI is available
            if OPENAI_API_KEY:
                await asyncio.sleep(2)
                await showcase_generate_and_post_image(
                    showcase_welcome_channel,
                    "gritty",
                    caption_prefix="Welcome postcard for the new arrival — "
                )
        return
    # ── Standard welcome ─────────────────────────────────

    welcome_channel = bot.get_channel(
        channels.get("welcome")
    )

    if not welcome_channel:
        return

    welcome_text = random.choice(WELCOME_MESSAGES)

    embed = discord.Embed(
        title="👋 NEW SURVIVOR ARRIVED",
        description=(
            f"{member.mention}\n\n{welcome_text}\n\n"
            "🔗 Please link your gamertag with `/linkgamer` in the required channel.\n"
            "Example: `/linkgamer gamertag: YourXboxName`"
        ),
        color=0x1ABC9C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Welcome System"
    )

    await welcome_channel.send(embed=style_embed(embed))


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    lower = message.content.lower()

    if await maybe_save_map_image_from_message(message, lower):
        return

    await maybe_translate_message(message)
    await apply_chat_reward_punishment_rules(message, lower)

    found_words = [
        word for word in SWEAR_WORDS
        if word in lower
    ]

    if found_words:

        user_id = str(message.author.id)

        if user_id not in swear_jar:

            swear_jar[user_id] = {
                "name": str(message.author),
                "count": 0,
                "balance": 0
            }

        swear_jar[user_id]["count"] += len(found_words)

        swear_jar[user_id]["balance"] += (
            len(found_words) * 100
        )

        pennies_total = swear_jar[user_id]["balance"]

        save_swear_jar()

        await send_swear_jar_feed(
            message,
            found_words,
            len(found_words) * 100,
            pennies_total
        )

    # Detect showcase guild early so DayZ-specific responses are suppressed
    _is_showcase = (
        message.guild is not None
        and guild_configs.get(str(message.guild.id), {}).get("is_showcase_guild", False)
    )
    now_ts = datetime.now(UTC).timestamp()

    if await maybe_handle_owner_natural_language(message, lower, now_ts):
        return

    if not _is_showcase:
        for keyword, response in AI_RESPONSES.items():

            if keyword in lower:

                guild_id = str(message.guild.id) if message.guild else "global"
                await message.channel.send(wb_text("ai", apply_owner_voice_to_text(guild_id, response)))

                break

    user_id = str(message.author.id)

    if user_id not in player_chat_tracker:

        player_chat_tracker[user_id] = {
            "recent_messages": 0,
            "recent_swears": 0,
            "clean_messages": 0,
            "eligible": False
        }

    # low-frequency fun chatter with anti-repeat + anti-spam guards
    # Suppressed in showcase guilds — showcase behaviour handles proactive messaging
    if not _is_showcase and now_ts - last_funny_message_time.get(user_id, 0) > 900:
        import random
        behavior = owner_behavior_config(str(message.guild.id) if message.guild else "global")
        fun_chance = max(0.001, min(0.2, float(behavior.get("fun_chatter_chance", 0.04))))
        if random.random() < fun_chance:
            idx = random.randrange(len(FUNNY_ROTATION))
            if idx == last_funny_index.get(user_id, -1):
                idx = (idx + 1) % len(FUNNY_ROTATION)
            last_funny_index[user_id] = idx
            last_funny_message_time[user_id] = now_ts
            guild_id = str(message.guild.id) if message.guild else "global"
            await message.channel.send(wb_text("spark", apply_owner_voice_to_text(guild_id, FUNNY_ROTATION[idx])))

    # ── Autonomous showcase handling ─────────────────────
    if message.guild and is_showcase_guild(str(message.guild.id)):
        await showcase_handle_message(message, lower, str(message.guild.id), now_ts)
        # Also run the keyword-based response matcher so the bot recognises
        # a wide range of topics (kills, factions, economy, loot, etc.)
        # without requiring slash commands. Internal cooldown prevents spam.
        await maybe_showcase_guild_response(message, lower)

    await maybe_reply_to_bot_mention(message, lower)
    await maybe_owner_mention_remark(message)
    await maybe_send_wandering_personality(message, now_ts)
    await maybe_send_ai_generated_picture(message, now_ts)

    tracker = player_chat_tracker[user_id]

    tracker["recent_messages"] += 1

    if found_words:

        tracker["recent_swears"] += len(found_words)
        tracker["clean_messages"] = 0

        if tracker["recent_swears"] >= SWEAR_REDEMPTION_THRESHOLD:
            tracker["eligible"] = True

    else:

        tracker["clean_messages"] += 1

        if (
            tracker["eligible"]
            and tracker["clean_messages"] >= SWEAR_REDEMPTION_MESSAGES_REQUIRED
        ):

            import random

            reward = random.randint(
                SWEAR_REWARD_MIN,
                SWEAR_REWARD_MAX
            )

            if user_id not in wallets:

                wallets[user_id] = {
                    "name": str(message.author),
                    "balance": 0,
                    "daily_transactions": 0
                }

            wallets[user_id]["balance"] += reward

            tracker["eligible"] = False
            tracker["recent_swears"] = 0
            tracker["clean_messages"] = 0
            tracker["recent_messages"] = 0

            save_wallets()

            redemption_messages = [
                f"🧼 {message.author.mention} finally cleaned up their language. Miracles do happen. +{reward} pennies 🪙",
                f"💰 Good behaviour detected from {message.author.mention}. Survivor rehabilitation successful. +{reward} pennies 🪙",
                f"🧠 AI Notice: {message.author.mention} survived {SWEAR_REDEMPTION_MESSAGES_REQUIRED} messages without swearing. Reward issued. +{reward} pennies 🪙",
                f"📻 Chernarus Radio: {message.author.mention} has temporarily stopped speaking like a lunatic. +{reward} pennies 🪙",
                f"🏆 Redemption Arc Complete: {message.author.mention} earned {reward} pennies for not swearing constantly."
            ]

            redemption_embed = discord.Embed(
                title="✨ SWEAR JAR REDEMPTION",
                description=random.choice(redemption_messages),
                color=0x2ECC71
            )

            redemption_embed.set_thumbnail(url=BOT_IMAGE)

            redemption_embed.set_footer(
                text="Wandering Bot Alpha • Behaviour System"
            )

            await message.channel.send(
                embed=style_embed(redemption_embed)
            )

    # Prefix commands disabled; slash commands only mode.

# =========================================================
# OWNER MONITORING SYSTEM
# =========================================================

BOT_OWNER_GUILD_ID = os.getenv("BOT_OWNER_GUILD_ID")
BOT_OWNER_CHANNEL_ID = os.getenv("BOT_OWNER_CHANNEL_ID")
BOT_OWNER_SECRET_CODE = os.getenv("BOT_OWNER_SECRET_CODE")


async def send_owner_notification(title, description):

    try:

        if not BOT_OWNER_CHANNEL_ID:
            return

        owner_channel = bot.get_channel(
            int(BOT_OWNER_CHANNEL_ID)
        )

        if not owner_channel:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x9B59B6
        )

        embed.set_thumbnail(url=BOT_IMAGE)

        embed.set_footer(
            text="Wandering Bot Alpha • Owner Monitoring"
        )

        await owner_channel.send(
            embed=style_embed(embed)
        )

    except Exception as error:
        print(error)




async def get_or_create_support_channel(guild):

    guild_id = str(guild.id)

    if guild_id not in guild_configs:
        guild_configs[guild_id] = {
            "guild_name": guild.name,
            "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
            "channels": {}
        }

    channels = guild_configs[guild_id].setdefault("channels", {})
    existing_id = channels.get("bot_support_tickets")

    if existing_id:
        existing_channel = guild.get_channel(existing_id)
        if existing_channel:
            return existing_channel

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.owner: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }

    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel = await guild.create_text_channel(
        "bot-support-tickets",
        overwrites=overwrites
    )

    channels["bot_support_tickets"] = channel.id
    save_guild_configs()

    return channel


def owner_secret_valid(interaction, secret_code):

    # Re-read env vars at call time so runtime changes are picked up
    live_secret = os.getenv("BOT_OWNER_SECRET_CODE")
    live_owner_ids = configured_bot_owner_ids()
    live_showcase_guild_id = os.getenv("SHOWCASE_GUILD_ID") or SHOWCASE_GUILD_ID
    live_showcase_channel_id = os.getenv("SHOWCASE_CHANNEL_ID") or SHOWCASE_CHANNEL_ID

    # Support multiple guild IDs via BOT_OWNER_GUILD_IDS (comma-separated).
    # Fall back to the legacy singular BOT_OWNER_GUILD_ID for backward compatibility.
    raw_guild_ids = os.getenv("BOT_OWNER_GUILD_IDS") or os.getenv("BOT_OWNER_GUILD_ID")
    live_guild_ids = [g.strip() for g in raw_guild_ids.split(",") if g.strip()] if raw_guild_ids else []
    raw_channel_ids = os.getenv("BOT_OWNER_CHANNEL_IDS") or os.getenv("BOT_OWNER_CHANNEL_ID")
    live_channel_ids = [c.strip() for c in raw_channel_ids.split(",") if c.strip()] if raw_channel_ids else []
    if live_showcase_channel_id:
        live_channel_ids.append(str(live_showcase_channel_id).strip())

    user_id = str(interaction.user.id)
    guild_id = str(interaction.guild_id) if interaction.guild_id else ""
    channel_id = str(getattr(interaction, "channel_id", "") or "")

    if not live_secret:
        print(f"[OWNER AUTH] REJECTED — BOT_OWNER_SECRET_CODE env var is not set")
        return False

    # Case-insensitive, whitespace-stripped comparison to avoid trivial mismatches
    if secret_code.strip().lower() != live_secret.strip().lower():
        print(f"[OWNER AUTH] REJECTED — secret code mismatch (user={user_id}, guild={guild_id})")
        return False

    # If BOT_OWNER_ID is configured, the calling user must match it
    if live_owner_ids and user_id not in live_owner_ids:
        print(f"[OWNER AUTH] REJECTED — user ID {user_id} is not in owner IDs {sorted(live_owner_ids)}")
        return False

    showcase_guild_ids = {
        str(value).strip()
        for value in [live_showcase_guild_id, live_showcase_channel_id]
        if str(value or "").strip()
    }
    allowed_by_showcase_guild = bool(guild_id and guild_id in showcase_guild_ids)
    allowed_by_channel = bool(channel_id and channel_id in set(live_channel_ids))

    # If one or more owner guild IDs are configured, the command must come from one of them
    # or from the configured owner/showcase channel.
    if live_guild_ids and guild_id not in live_guild_ids and not allowed_by_showcase_guild and not allowed_by_channel:
        print(f"[OWNER AUTH] REJECTED — guild ID {guild_id} is not in BOT_OWNER_GUILD_IDS {live_guild_ids}")
        return False

    print(f"[OWNER AUTH] APPROVED — user={user_id}, guild={guild_id}")
    return True


async def reject_owner_command(interaction):
    await interaction.response.send_message(
        "Owner command rejected. Verify your secret code and that you are running this command as the bot owner. Check bot logs for details.",
        ephemeral=True
    )


SENSITIVE_COMMAND_OPTION_NAMES = {
    "secret_code",
    "nitrado_token",
    "ftp_password",
    "token",
    "password",
    "api_key"
}


def format_interaction_options(options):
    lines = []

    for option in options or []:
        name = str(option.get("name", "option"))
        value = option.get("value")
        nested = option.get("options")

        if nested:
            nested_text = format_interaction_options(nested)
            lines.append(f"{name}: {nested_text}")
            continue

        if name.lower() in SENSITIVE_COMMAND_OPTION_NAMES:
            value = "[hidden]"

        lines.append(f"{name}: {value}")

    return ", ".join(lines) if lines else "No options"


async def log_slash_command_usage(interaction):
    if not interaction.guild or not interaction.command:
        return

    try:
        guild_id = str(interaction.guild.id)
        config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
        channels = config.setdefault("channels", {})
        command_log_channel = bot.get_channel(channels.get("command_logs"))

        if not command_log_channel:
            command_log_channel = await get_or_create_feed_channel(
                interaction.guild,
                config,
                "command_logs",
                DEFAULT_CHANNEL_NAMES["command_logs"],
                private=True
            )

        command_name = interaction.command.qualified_name if interaction.command else "unknown"
        options_text = format_interaction_options(interaction.data.get("options", []) if interaction.data else [])

        embed = discord.Embed(
            title="SLASH COMMAND USED",
            color=0x3498DB
        )
        embed.add_field(name="User", value=f"{interaction.user.mention}\n`{interaction.user}`", inline=False)
        embed.add_field(name="Channel", value=interaction.channel.mention if interaction.channel else "Unknown", inline=True)
        embed.add_field(name="Command", value=f"/{command_name}", inline=True)
        embed.add_field(name="Options", value=options_text[:1000], inline=False)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - Command Logs")
        await command_log_channel.send(embed=style_embed(embed))

    except Exception as error:
        print(f"SLASH COMMAND LOG ERROR: {error}")


@bot.tree.interaction_check
async def log_all_slash_commands(interaction: discord.Interaction):
    await log_slash_command_usage(interaction)
    return True


@bot.listen("on_command")
async def log_command_usage(ctx):

    try:
        if not ctx.guild:
            return

        guild_id = str(ctx.guild.id)

        config = guild_configs.setdefault(guild_id, {"guild_name": ctx.guild.name, "channels": {}})

        channels = config.setdefault("channels", {})

        command_log_channel = bot.get_channel(
            channels.get("command_logs")
        )

        if not command_log_channel:
            command_log_channel = await get_or_create_feed_channel(
                ctx.guild,
                config,
                "command_logs",
                DEFAULT_CHANNEL_NAMES["command_logs"],
                private=True
            )

        if command_log_channel:

            embed = discord.Embed(
                title="📜 COMMAND USED",
                color=0x3498DB
            )

            embed.add_field(
                name="👤 User",
                value=str(ctx.author),
                inline=False
            )

            embed.add_field(
                name="💬 Command",
                value=ctx.message.content,
                inline=False
            )

            await command_log_channel.send(
                embed=style_embed(embed)
            )

    except Exception as error:
        print(error)


@bot.event
async def on_command_error(ctx, error):

    try:

        guild_id = str(ctx.guild.id)

        config = guild_configs.get(guild_id, {})

        channels = config.get("channels", {})

        admin_log_channel = bot.get_channel(
            channels.get("admin_logs")
        )

        if admin_log_channel:

            embed = discord.Embed(
                title="⚠️ FAILED COMMAND",
                color=0xE74C3C
            )

            embed.add_field(
                name="👤 User",
                value=str(ctx.author),
                inline=False
            )

            embed.add_field(
                name="💬 Attempted Command",
                value=ctx.message.content,
                inline=False
            )

            embed.add_field(
                name="🧠 Error",
                value=str(error)[:1000],
                inline=False
            )

            await admin_log_channel.send(
                embed=style_embed(embed)
            )

    except Exception as inner_error:
        print(inner_error)

# =========================================================
# COMMANDS
# =========================================================


def command_parameter_usage(command):
    parts = []

    for parameter in getattr(command, "parameters", []):
        name = getattr(parameter, "display_name", None) or getattr(parameter, "name", "option")
        required = bool(getattr(parameter, "required", False))
        wrapper = "<{}>" if required else "[{}]"
        parts.append(wrapper.format(name))

    return " ".join(parts)


def iter_registered_slash_commands():
    def walk(command, parents=None):
        parents = parents or []
        name = getattr(command, "name", "")
        path = parents + [name]

        if isinstance(command, app_commands.Group):
            for child in getattr(command, "commands", []):
                yield from walk(child, path)
            return

        if not name:
            return

        yield " ".join(path), command

    for command in bot.tree.get_commands():
        yield from walk(command)


def command_guide_lines():
    lines = []

    for command_name, command in sorted(iter_registered_slash_commands(), key=lambda item: item[0]):
        usage = command_parameter_usage(command)
        description = getattr(command, "description", "") or "No description set."
        command_text = f"/{command_name}"
        if usage:
            command_text = f"{command_text} {usage}"
        lines.append(f"`{command_text}`\n{description}")

    return lines


async def send_command_guide_pages(destination, *, title="WANDERING BOT COMMAND GUIDE", intro=None, ephemeral=False):
    lines = command_guide_lines()
    commands_per_page = 12
    total_pages = max(1, (len(lines) + commands_per_page - 1) // commands_per_page)

    async def send_embed(embed):
        if ephemeral:
            try:
                await destination.send(embed=embed, ephemeral=True)
                return
            except TypeError:
                pass
        await destination.send(embed=embed)

    if intro:
        embed = discord.Embed(
            title=title,
            description=intro,
            color=0x3498DB
        )
        embed.add_field(
            name="How To Read This",
            value=(
                "`<option>` means Discord requires it. `[option]` means it is optional.\n"
                "Use Discord autocomplete for channels, members, roles, and choices."
            ),
            inline=False
        )
        embed.add_field(name="Commands Listed", value=str(len(lines)), inline=True)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - Command Guide")
        await send_embed(style_embed(embed))

    for page_index in range(total_pages):
        start = page_index * commands_per_page
        chunk = lines[start:start + commands_per_page]
        embed = discord.Embed(
            title=f"{title} - Page {page_index + 1}/{total_pages}",
            description="\n\n".join(chunk)[:4000] if chunk else "No slash commands registered.",
            color=0x3498DB
        )
        embed.set_footer(text="Required options use <angle brackets>; optional options use [square brackets].")
        await send_embed(style_embed(embed))


@bot.command()
async def helpme(ctx):

    embed = discord.Embed(
        title="WANDERING BOT ALPHA - COMMAND CENTER",
        description=(
            "Admin and owner quick guide. Use slash commands where possible.\n"
            "All controls are available as slash commands."
        ),
        color=0xF1C40F
    )

    embed.add_field(
        name="📊 Stats & Leaderboards",
        value=(
            "`/playercard [name]` — full career dossier (omit name for your own)\n"
            "`/leaderboard setup` — admin: hourly Server + Global leaderboard (10 feeds: kills, deaths, time played, builds, kill streak, longest shot, swearing, flags raised, animal deaths, zombie deaths)\n"
            "`/leaderboard hall` — 🏅 all-time Hall of Fame for this server\n"
            "`/leaderboard challenges` — 🎯 today's daily challenge + progress\n"
            "`/leaderboard refresh / unset` — admin\n"
            "`/topkills`, `/toplongshots`, `/online`"
        ),
        inline=False,
    )

    embed.add_field(
        name="💰 Bounties",
        value=(
            "`/bounty set <player> <amount>` — place a bounty (pool-style)\n"
            "`/bounty list` — show active bounties\n"
            "`/bounty clear <player>` — admin only\n"
            "_Bounties auto-claim when the target dies in the killfeed._"
        ),
        inline=False,
    )

    embed.add_field(
        name="🔥 Killfeed Flavour (auto)",
        value=(
            "• 💥 Headshot embeds + Hit Zone field\n"
            "• 🔫 Kill-spree tracking + 'SPREE ENDED' embeds\n"
            "• 👹 Nemesis rivalry alerts (3/5/10/25 kill milestones)\n"
            "• 🛡️ Squad detection in same zone\n"
            "• 🪖 Squad-inbound alert on 5+ connects in 60s\n"
            "• 🩸 Streak Broken field when 7+ day survivor dies\n"
            "• 🚗💥 Vehicle-kill embeds\n"
            "• 💀 Session recap on disconnect\n"
            "• 🎁 Auto-reactions on kill embeds (🔥🎯💀)\n"
            "• 🏆 Achievement unlocks announced live\n"
            "• 🧵 Auto-threads on epic events (300m+ HS / 500m+ longshot / 5+ rampage)"
        ),
        inline=False,
    )

    embed.add_field(
        name="📰 Recaps & News",
        value=(
            "`/extra recap [today|yesterday|week]` — manual recap pull\n"
            "`/extra setrecapchannel` — pick auto-post channel\n"
            "`/extra spectator` — live who-is-online + last 10 min of kills\n"
            "_Daily recap + AI news bulletin auto-posts at the configured UTC hour._"
        ),
        inline=False,
    )

    embed.add_field(
        name="🤖 AI Roasts",
        value=(
            "`/extra setroasts on|off` — admin opt-in per guild\n"
            "`/extra setroasttone <mixed|edgy|pg13|brutal_clean>` — live switch\n"
            "_Requires `EMERGENT_LLM_KEY` Railway env var (free fallback works without)._"
        ),
        inline=False,
    )

    embed.add_field(
        name="Live Intelligence",
        value=(
            "`/online` - online survivors\n"
            "`/serverstatus` - bot status\n"
            "`/map` - admin-only live survivor map\n"
            "`/heatmap` - PvP heatmap summary\n"
            "`/backfilladmstats` - add up to 14 days of ADM history into leaderboard stats\n"
            "`/backfillkills` - fill killfeed/longshots from recent ADM history\n"
            "`/setaiimages`, `/aiimagepostnow`"
        ),
        inline=False
    )

    embed.add_field(
        name="Railway Map Fix",
        value=(
            "If heatmaps use the drawn fallback map, Railway probably cannot read a Windows file path. Use public map URLs:\n"
            "`/setheatmapimage map_name: chernarus image_source: https://i.redd.it/a2mn8bzx93gd1.jpeg`\n"
            "`/setheatmapimage map_name: livonia image_source: https://i.imgur.com/nzEp9wF.jpeg`\n"
            "Then check `/mapimagestatus`."
        ),
        inline=False
    )

    embed.add_field(
        name="Admin Tools",
        value=(
            "`/tools setadminrole role`\n"
            "`/tools addstaffrole role`\n"
            "`/tools staffroles`\n"
            "`/shamesetup`, `/adminban`, `/admintempban`, `/adminunban`\n"
            "`/cheatchecksetup`, `/cheatcheckconfig`, `/cheatcheckstatus`\n"
            "`/purge amount`\n"
            "`/purgeuser member amount`\n"
            "`/tools purgebots amount`\n"
            "`/tools giverole member role`, `/tools removerole member role`\n"
            "`/tools channelstatus`, `/tools channelpacks`\n"
            "`/tools restorechannels channel_key`, `/tools restorechannelpack pack`"
        ),
        inline=False
    )

    embed.add_field(
        name="Server Control",
        value=(
            "`/restartserver`, `/admstatus`, `/restartadm force`\n"
            "`/server setrestartinterval`, `/server setrestartstart`\n"
            "`/server cancelrestarts`, `/server listrestarts`\n"
            "`/server togglebasedamage state`\n"
            "`/server sendmessage <text>` — broadcast in-game chat (via Nitrado)\n"
            "`/extra reloadguilds`\n"
            "`/setradarchannel channel`, `/radarping x y reason`\n"
            "`/addradarzone`, `/radarstatus`, `/forcelinkgamer`\n"
            "`/setdayzmessages` - owner-only in-game message XML upload\n"
            "`/botupdates`"
        ),
        inline=False
    )

    embed.add_field(
        name="DayZ Restart Deliveries",
        value=(
            "Items: add shop entries with `/addshopitem`; players use `/buy item_name x y`; the bot writes delivery XML for restart.\n"
            "Vehicles: players use `/tools rentvehicle vehicle_name rental_hours x y`; the bot writes vehicle spawns into the restart XML.\n"
            "PC/custom hosts: add `SpawnWanderingDeliveries();` to your DayZ `init.c` after weather setup, or use owner-only `/installdayzbridge`.\n"
            "Console hosts: `init.c` is not exposed. Use `/console setupobjects`, `/console addobject`, and `/console exportobjects` for the `cfggameplay.json` object-spawner flow."
        ),
        inline=False
    )

    embed.add_field(
        name="Economy & Rules",
        value=(
            "`/wallet`, `/shop`, `/buy`, `/tools rentvehicle`\n"
            "`/addreward keyword amount`\n"
            "`/addpunishment keyword amount`\n"
            "`/listrules`\n"
            "`/removerule rule_number`\n"
            "`/tools importtypesxml source_path default_price`\n"
            "`/addshopitem item_name price category`\n"
            "`/editshopitem item_name price category`\n"
            "`/toggleshopitem item_name`, `/removeshopitem item_name`\n"
            "`/givepennies member amount`, `/tools shopcategories`, `/tools swearjar`"
        ),
        inline=False
    )

    embed.add_field(
        name="Translation, Factions & Support",
        value=(
            "`/translationconfig` - automatic translation: `same`, `channel`, or `off`\n"
            "`/linkgamer gamertag`, `/mylink`\n"
            "`/factionticket faction_name`, `/factionapprove message_id`\n"
            "`/supportbot issue` - admin ticket to the bot owner"
        ),
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering System created by CraneMonkey6273")

    await ctx.send(embed=style_embed(embed))

@bot.command()
async def online(ctx):

    guild_id = str(ctx.guild.id)

    ensure_guild_runtime(guild_id)

    guild_online = online_players[guild_id]

    if guild_online:

        player_list = "\n".join(
            f"🟢 {player}"
            for player in sorted(guild_online)
        )

    else:

        player_list = "No players online."

    embed = discord.Embed(
        title=f"✅🎮 ONLINE SURVIVORS 🎮✅ ({len(guild_online)})",
        description=player_list,
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def swearjar(ctx):

    if not swear_jar:

        await ctx.send(
            "Swear jar is empty."
        )

        return

    sorted_users = sorted(
        swear_jar.values(),
        key=lambda x: x["balance"],
        reverse=True
    )

    leaderboard = []

    for index, user in enumerate(
        sorted_users[:10],
        start=1
    ):

        leaderboard.append(
            f"{index}. {user['name']} - £{user['balance']} ({user['count']} swears)"
        )

    embed = discord.Embed(
        title="💸 SWEAR JAR LEADERBOARD",
        description="\n".join(leaderboard),
        color=0xF1C40F
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def heatmap(ctx):

    guild_id = str(ctx.guild.id)

    ensure_guild_runtime(guild_id)

    if not territory_heat[guild_id]:

        await ctx.send(
            "No territory activity yet."
        )

        return

    sorted_zones = sorted(
        territory_heat[guild_id].items(),
        key=lambda x: x[1],
        reverse=True
    )

    lines = []

    for zone, count in sorted_zones:

        lines.append(
            f"🔥 {zone} - {count}"
        )

    embed = discord.Embed(
        title="🗺️ TERRITORY HEATMAP",
        description="\n".join(lines),
        color=0xE74C3C
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def toplongshots(ctx):

    if not longshot_records:

        await ctx.send(
            "No longshot records yet."
        )

        return

    sorted_records = sorted(
        longshot_records.items(),
        key=lambda x: x[1].get("distance", 0),
        reverse=True
    )

    lines = []

    for index, (guild_id, data) in enumerate(
        sorted_records[:10],
        start=1
    ):

        guild_name = guild_configs.get(
            guild_id,
            {}
        ).get("guild_name", "Unknown Server")

        lines.append(
            f"{index}. {data.get('killer')} — 🎯 {data.get('distance')}m — {guild_name}"
        )

    embed = discord.Embed(
        title="🎯 GLOBAL LONGSHOT LEADERBOARD",
        description="\n".join(lines),
        color=0xF1C40F
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Longshot Intelligence"
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def topkills(ctx):

    if not player_stats:

        await ctx.send(
            "No stats available."
        )

        return

    guild_id = str(ctx.guild.id)
    guild_players = [
        (player, stats)
        for player, stats in player_stats.items()
        if str(stats.get("guild_id", "")) == guild_id
    ]
    rows = guild_players or list(player_stats.items())

    sorted_players = sorted(
        rows,
        key=lambda x: x[1].get("kills", 0),
        reverse=True
    )

    lines = []
    medals = ["🥇", "🥈", "🥉"]

    for index, (player, stats) in enumerate(
        sorted_players[:10],
        start=1
    ):
        rank = medals[index - 1] if index <= len(medals) else f"{index}."

        lines.append(
            f"{rank} **{player}** - `{stats.get('kills', 0)}` kills | `{stats.get('deaths', 0)}` deaths | `{format_duration(stats.get('time_online_seconds', 0))}` online"
        )

    embed = discord.Embed(
        title="☠️ SERVER TOP KILLS",
        description="\n".join(lines),
        color=0x992D22
    )
    embed.add_field(
        name="Scope",
        value="This server" if guild_players else "Global fallback until this server has ADM stats",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# CUSTOM ROLE CONFIGURATION
# =========================================================

@bot.command()
async def setadminrole(ctx, *, role_name: str):

    if not can_modify_admin_roles(ctx.author):
        await ctx.send("Only a Discord administrator or the guild owner can change bot admin roles.")
        return

    role = resolve_guild_role(ctx.guild, role_name)
    if not role:
        await ctx.send(f"No Discord role named `{role_name}` exists in this server.")
        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["admin_roles"] = [role.name]

    save_guild_configs()

    embed = discord.Embed(
        title="🛡️ PRIMARY ADMIN ROLE SET",
        description=f"Primary bot admin role is now: `{role.name}`",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def addstaffrole(ctx, *, role_name: str):

    if not can_modify_admin_roles(ctx.author):
        await ctx.send("Only a Discord administrator or the guild owner can change bot admin roles.")
        return

    role = resolve_guild_role(ctx.guild, role_name)
    if not role:
        await ctx.send(f"No Discord role named `{role_name}` exists in this server.")
        return

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    roles = config.get(
        "admin_roles",
        DEFAULT_ADMIN_ROLES.copy()
    )

    if role.name not in roles:
        roles.append(role.name)

    guild_configs[guild_id]["admin_roles"] = roles

    save_guild_configs()

    embed = discord.Embed(
        title="➕ STAFF ROLE ADDED",
        description=f"`{role.name}` can now use admin bot commands.",
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def staffroles(ctx):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    roles = config.get(
        "admin_roles",
        DEFAULT_ADMIN_ROLES
    )

    embed = discord.Embed(
        title="🛡️ BOT STAFF ROLES",
        description="\n".join([
            f"• {role}"
            for role in roles
        ]),
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))

# =========================================================
# FACTION TICKET SYSTEM
# =========================================================

@bot.command()
async def factionticket(ctx, *, faction_name: str):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    ticket_channel = bot.get_channel(
        channels.get("faction_tickets")
    )

    if not ticket_channel:

        await ctx.send(
            "Faction ticket system is not configured."
        )

        return

    linked_data = linked_players.get(
        str(ctx.author.id),
        {}
    )

    gamertag = linked_data.get(
        "gamertag",
        "Not Linked"
    )

    embed = discord.Embed(
        title="🎫 NEW FACTION REQUEST",
        description=(
            f"{ctx.author.mention} has submitted a faction request."
        ),
        color=0x9B59B6
    )

    embed.add_field(
        name="🏴 Proposed Faction",
        value=faction_name,
        inline=False
    )

    embed.add_field(
        name="👤 Discord User",
        value=str(ctx.author),
        inline=True
    )

    embed.add_field(
        name="🎮 Linked Gamertag",
        value=gamertag,
        inline=True
    )

    embed.add_field(
        name="👑 Faction Owner",
        value=ctx.author.mention,
        inline=False
    )

    embed.add_field(
        name="📜 Status",
        value="🟡 Pending Staff Review",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Faction Intelligence"
    )

    ticket_message = await ticket_channel.send(
        embed=style_embed(embed)
    )

    staff_channel = bot.get_channel(
        channels.get("faction_staff")
    )

    if staff_channel:

        staff_embed = discord.Embed(
            title="🚨 NEW FACTION TICKET",
            description=(
                f"A new faction application has been submitted by {ctx.author.mention}."
            ),
            color=0xE67E22
        )

        staff_embed.add_field(
            name="🏴 Faction",
            value=faction_name,
            inline=True
        )

        staff_embed.add_field(
            name="🎫 Ticket ID",
            value=str(ticket_message.id),
            inline=True
        )

        staff_embed.add_field(
            name="👑 Owner",
            value=str(ctx.author),
            inline=False
        )

        staff_embed.set_thumbnail(url=BOT_IMAGE)

        staff_embed.set_footer(
            text="Wandering Bot Alpha • Staff Notification"
        )

        await staff_channel.send(
            embed=style_embed(staff_embed)
        )

    confirmation = discord.Embed(
        title="✅ FACTION REQUEST SUBMITTED",
        description=(
            f"Your faction request for `{faction_name}` has been sent to server staff."
        ),
        color=0x2ECC71
    )

    confirmation.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(confirmation)
    )


@bot.command()
async def factionapprove(ctx, message_id: int):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    ticket_channel = bot.get_channel(
        channels.get("faction_tickets")
    )

    if not ticket_channel:
        return

    try:

        message = await ticket_channel.fetch_message(message_id)

        embed = message.embeds[0]

        approved_embed = discord.Embed(
            title="✅ FACTION APPROVED",
            description=embed.description,
            color=0x2ECC71
        )

        for field in embed.fields:

            approved_embed.add_field(
                name=field.name,
                value=field.value,
                inline=field.inline
            )

        approved_embed.set_thumbnail(url=BOT_IMAGE)

        approved_embed.set_footer(
            text="Wandering Bot Alpha • Staff Approved"
        )

        await message.edit(
            embed=style_embed(approved_embed)
        )

        await ctx.send(
            "✅ Faction request approved."
        )

    except Exception as error:

        await ctx.send(
            f"❌ Failed to approve ticket: {error}"
        )


# =========================================================
# CHAT MANAGEMENT SYSTEM
# =========================================================

@bot.command()
async def purge(ctx, amount: int = 10):

    if not has_staff_permissions(ctx):
        return

    if amount < 1:
        amount = 1

    if amount > 500:
        amount = 500

    deleted = await ctx.channel.purge(limit=amount + 1)

    embed = discord.Embed(
        title="🧹 CHAT PURGED",
        description=(
            f"Removed {len(deleted) - 1} messages from {ctx.channel.mention}"
        ),
        color=0xE67E22
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    confirmation = await ctx.send(
        embed=style_embed(embed)
    )

    await asyncio.sleep(5)

    await confirmation.delete()


@bot.command()
async def purgeuser(ctx, member: discord.Member, amount: int = 50):

    if not has_staff_permissions(ctx):
        return

    deleted = []

    async for message in ctx.channel.history(limit=500):

        if message.author == member:

            deleted.append(message)

            if len(deleted) >= amount:
                break

    for message in deleted:

        try:
            await message.delete()
        except:
            pass

    embed = discord.Embed(
        title="🧹 USER MESSAGES PURGED",
        description=(
            f"Removed {len(deleted)} messages from {member.mention}"
        ),
        color=0xE74C3C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    confirmation = await ctx.send(
        embed=style_embed(embed)
    )

    await asyncio.sleep(5)

    await confirmation.delete()


@bot.command()
async def purgebots(ctx, amount: int = 100):

    if not has_staff_permissions(ctx):
        return

    deleted = []

    async for message in ctx.channel.history(limit=1000):

        if message.author.bot:

            deleted.append(message)

            if len(deleted) >= amount:
                break

    for message in deleted:

        try:
            await message.delete()
        except:
            pass

    embed = discord.Embed(
        title="🤖 BOT MESSAGES PURGED",
        description=f"Removed {len(deleted)} bot messages.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    confirmation = await ctx.send(
        embed=style_embed(embed)
    )

    await asyncio.sleep(5)

    await confirmation.delete()

# =========================================================
# RADAR PING SYSTEM
# =========================================================

RADAR_PINGS = {}


def parse_xy_coords(coords):
    try:
        x_text, y_text = str(coords).split(",")[:2]
        return float(x_text.strip()), float(y_text.strip())
    except Exception:
        return None


def parse_gamertag_list(value):
    if not value:
        return []

    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[,;\n]+", str(value))

    clean_items = []
    seen = set()
    for item in raw_items:
        gamertag = str(item).strip()
        key = normalize_discord_name(gamertag)
        if not key or key in seen:
            continue
        clean_items.append(gamertag)
        seen.add(key)

    return clean_items


def radar_zone_ignored_gamertags(zone):
    return parse_gamertag_list(
        zone.get("ignored_gamertags")
        or zone.get("ignore_gamertags")
        or zone.get("ignored_players")
        or []
    )


def radar_zone_ignores_player(zone, player_name):
    player_key = normalize_discord_name(player_name)
    if not player_key:
        return False

    ignored_keys = {
        normalize_discord_name(gamertag)
        for gamertag in radar_zone_ignored_gamertags(zone)
    }
    return player_key in ignored_keys


async def check_radar_zones_for_adm(guild_id, config, event_type, line):
    zones = config.get("radar_zones", [])
    if not zones:
        return

    coords = extract_adm_coords(line)
    point = parse_xy_coords(coords)
    if not point:
        return

    player_name = extract_player_name(line)
    now_ts = datetime.now(UTC).timestamp()
    channels = config.get("channels", {})
    radar_channel = bot.get_channel(channels.get("radar"))
    if not radar_channel:
        return

    px, py = point
    for zone in zones:
        if not zone.get("enabled", True):
            continue

        zx = float(zone.get("x", 0))
        zy = float(zone.get("y", 0))
        radius = float(zone.get("radius", 0))
        distance = ((px - zx) ** 2 + (py - zy) ** 2) ** 0.5
        if distance > radius:
            continue

        zone_id = str(zone.get("id"))
        if radar_zone_ignores_player(zone, player_name):
            continue

        throttle_key = f"{guild_id}:{zone_id}:{player_name}"
        if now_ts - RADAR_PINGS.get(throttle_key, 0) < int(zone.get("cooldown_seconds", 600)):
            continue

        RADAR_PINGS[throttle_key] = now_ts
        map_link = f"https://dayz.ginfo.gg/{izurvive_map_path(guild_id)}#location={zx};{zy}"
        player_link = build_izurvive_link(coords, guild_id)
        embed = discord.Embed(
            title="RADAR ZONE TRIGGERED",
            description=f"**{player_name}** entered **{zone.get('name', 'Radar Zone')}**.",
            color=0xE74C3C
        )
        embed.add_field(name="Event", value=event_type or "activity", inline=True)
        embed.add_field(name="Distance From Center", value=f"{distance:.0f}m / {radius:.0f}m", inline=True)
        embed.add_field(name="Zone Center", value=f"[Open Zone](<{map_link}>)", inline=False)
        if player_link:
            embed.add_field(name="Player Location", value=f"[Open Player Location](<{player_link}>)", inline=False)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - Radar Intelligence")
        await radar_channel.send(embed=style_embed(embed))


@bot.command()
async def setradarchannel(ctx, channel: discord.TextChannel):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["channels"]["radar"] = channel.id

    save_guild_configs()

    embed = discord.Embed(
        title="📡 RADAR CHANNEL CONFIGURED",
        description=f"Radar alerts will now go to {channel.mention}",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def radarping(ctx, x: str, y: str, *, reason: str = "Survivor Activity"):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    radar_channel = bot.get_channel(
        channels.get("radar")
    )

    if not radar_channel:

        await ctx.send("❌ Radar channel not configured.")
        return

    map_link = f"https://dayz.ginfo.gg/#location={x};{y}"

    embed = discord.Embed(
        title="📡 MANUAL RADAR PING",
        description="Suspicious activity detected.",
        color=0xE74C3C
    )

    embed.add_field(
        name="🎯 Activity",
        value=reason,
        inline=False
    )

    embed.add_field(
        name="📍 Coordinates",
        value=f"[🔵 Open Map](<{map_link}>)",
        inline=False
    )

    embed.add_field(
        name="🛡️ Triggered By",
        value=ctx.author.mention,
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Radar Intelligence"
    )

    await radar_channel.send(
        embed=style_embed(embed)
    )

    await ctx.send("✅ Radar ping sent.")

# =========================================================
# ADMIN SERVER CONTROLS
# =========================================================

@bot.command()
async def admstatus(ctx):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)
    config = guild_configs.get(guild_id, {})
    channels = config.get("channels", {})

    configured = all(
        config.get(key)
        for key in ["nitrado_token", "service_id", "nitrado_user", "ftp_user", "ftp_password"]
    )

    active = is_active_guild(guild_id)

    embed = discord.Embed(
        title="📡 ADM FEED STATUS",
        color=0x3498DB
    )

    embed.add_field(
        name="Guild Loaded",
        value="Yes" if guild_id in guild_configs else "No",
        inline=True
    )

    embed.add_field(
        name="Active Guild",
        value="Yes" if active else "No",
        inline=True
    )

    embed.add_field(
        name="Nitrado Setup",
        value="Ready" if configured else "Missing setup",
        inline=True
    )

    embed.add_field(
        name="ADM Loop",
        value="Running" if adm_loop.is_running() else "Stopped",
        inline=True
    )

    embed.add_field(
        name="Remembered ADM Lines",
        value=str(len(processed_lines.get(guild_id, set()))),
        inline=True
    )

    embed.add_field(
        name="Killfeed Channel",
        value="Set" if channels.get("killfeed") else "Missing",
        inline=True
    )

    embed.set_thumbnail(url=BOT_IMAGE)
    await ctx.send(embed=style_embed(embed))
    await send_command_guide_pages(
        ctx,
        title="ALL SLASH COMMANDS",
        intro="Full command list with what each command does and how to type it."
    )


@bot.command()
async def reloadguilds(ctx):

    if not has_staff_permissions(ctx):
        return

    load_guild_configs()
    load_processed_adm_lines()
    bootstrap_runtime_from_connected_guilds()
    await start_background_tasks()

    print("STARTING ADM STARTUP PROTOCOL")
    startup_results = await refresh_adm_feeds()
    log_adm_protocol_results(startup_results, "ADM STARTUP")

    embed = discord.Embed(
        title="🔄 GUILD CONFIGS RELOADED",
        description=(
            f"Loaded `{len(list(active_guild_config_items()))}` active configured guilds "
            f"out of `{len(guild_configs)}` saved configs and restarted background tasks."
        ),
        color=0x1ABC9C
    )

    embed.set_thumbnail(url=BOT_IMAGE)
    await ctx.send(embed=style_embed(embed))


@bot.command()
async def restartadm(ctx, force: str = "no"):

    if not has_staff_permissions(ctx):
        return

    force_refresh = force.lower() in ["force", "yes", "true", "1"]

    load_guild_configs()
    load_processed_adm_lines()
    bootstrap_runtime_from_connected_guilds()

    if adm_loop.is_running():
        adm_loop.restart()
    else:
        adm_loop.start()

    results = await refresh_adm_feeds(str(ctx.guild.id), force=force_refresh)
    log_adm_protocol_results(results, "ADM RESTART")
    success, message = results.get(str(ctx.guild.id), (False, "No result"))

    embed = discord.Embed(
        title="📡 ADM FEED RESTARTED",
        description=message,
        color=0x2ECC71 if success else 0xE74C3C
    )

    embed.add_field(
        name="Force Mode",
        value="On" if force_refresh else "Off",
        inline=True
    )

    embed.add_field(
        name="ADM Loop",
        value="Running" if adm_loop.is_running() else "Stopped",
        inline=True
    )

    embed.set_thumbnail(url=BOT_IMAGE)
    await ctx.send(embed=style_embed(embed))


@bot.tree.command(name="backfillkills", description="Admin: post recent ADM kill history into killfeed and longshots")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    limit="Maximum historical kills to post, 1 to 500",
    hours="How far back to scan ADM files, defaults to 14 days",
    force="Repost kills already backfilled by this command"
)
async def backfillkills(interaction: discord.Interaction, limit: int = 100, hours: int = 336, force: bool = False):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id)
    if not config:
        await interaction.followup.send("This server is not setup yet.", ephemeral=True)
        return

    required_keys = ["nitrado_token", "service_id", "nitrado_user"]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        await interaction.followup.send(f"Missing setup values: {', '.join(missing)}", ephemeral=True)
        return

    limit = max(1, min(500, int(limit or 100)))
    hours = max(1, min(336, int(hours or 336)))
    ensure_guild_runtime(guild_id)

    adm_logs = await asyncio.to_thread(list_adm_logs, config, hours)
    if not adm_logs:
        latest_log = await asyncio.to_thread(ping_latest_adm_log, config)
        adm_logs = [latest_log] if latest_log else []

    if not adm_logs:
        await interaction.followup.send(f"No ADM logs found to backfill from in the last `{hours}` hours.", ephemeral=True)
        return

    history_hashes = set(str(item) for item in config.setdefault("killfeed_history_hashes", []))
    selected = []
    seen_signatures = set()
    scanned_logs = 0
    failed_downloads = 0

    for adm_log in adm_logs:
        if len(selected) >= limit:
            break

        downloaded = await asyncio.to_thread(download_latest_adm, guild_id, config, adm_log)
        if not downloaded:
            failed_downloads += 1
            continue

        adm_path = os.path.join(GUILD_DATA_FOLDER, f"{guild_id}.ADM")
        if not os.path.exists(adm_path):
            failed_downloads += 1
            continue

        scanned_logs += 1
        with open(adm_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]

        for line in reversed(lines):
            if classify_event(line) != "kill":
                continue

            details = extract_pvp_kill_details(line)
            if not details:
                continue

            line_hash = stable_line_hash(line)
            if not force and line_hash in history_hashes:
                continue

            signature = pvp_kill_signature(guild_id, details)
            if signature in seen_signatures:
                continue

            seen_signatures.add(signature)
            selected.append((line, line_hash))

            if len(selected) >= limit:
                break

    if not selected:
        await interaction.followup.send(
            f"No new historical PvP kills found after scanning `{scanned_logs}` ADM files over `{hours}` hours.",
            ephemeral=True
        )
        return

    selected.reverse()
    posted = 0
    longshots_posted = 0
    stats_added = 0

    for line, line_hash in selected:
        already_counted = line_hash in processed_lines[guild_id]
        sent, sent_longshot = await send_pvp_kill_feed_message(guild_id, config, line, history=True)
        if sent:
            posted += 1
            if sent_longshot:
                longshots_posted += 1
            if force or not already_counted:
                update_player_stats_from_adm(guild_id, "kill", line)
                stats_added += 1
            history_hashes.add(line_hash)
            remember_processed_line(guild_id, line_hash)

    save_player_stats()
    save_processed_adm_lines()
    config["killfeed_history_hashes"] = list(history_hashes)[-500:]
    save_guild_configs()

    await interaction.followup.send(
        f"Backfilled `{posted}` historical PvP kills after scanning `{scanned_logs}` ADM files over `{hours}` hours. `{stats_added}` were added to leaderboard stats and `{longshots_posted}` also went to longshots. Failed downloads: `{failed_downloads}`.",
        ephemeral=True
    )


@bot.tree.command(name="backfilladmstats", description="Admin: rebuild leaderboard stats from recent ADM history")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    hours="How far back to scan ADM files, defaults to 14 days",
    force="Count lines even if this bot already processed them"
)
async def backfilladmstats(interaction: discord.Interaction, hours: int = 336, force: bool = False):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id)
    if not config:
        await interaction.followup.send("This server is not setup yet.", ephemeral=True)
        return

    required_keys = ["nitrado_token", "service_id", "nitrado_user"]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        await interaction.followup.send(f"Missing setup values: {', '.join(missing)}", ephemeral=True)
        return

    hours = max(1, min(336, int(hours or 336)))
    ensure_guild_runtime(guild_id)

    adm_logs = await asyncio.to_thread(list_adm_logs, config, hours)
    if not adm_logs:
        latest_log = await asyncio.to_thread(ping_latest_adm_log, config)
        adm_logs = [latest_log] if latest_log else []

    if not adm_logs:
        await interaction.followup.send(f"No ADM logs found to backfill from in the last `{hours}` hours.", ephemeral=True)
        return

    scanned_logs = 0
    failed_downloads = 0
    counted_events = 0
    counted_kills = 0
    skipped_existing = 0

    for adm_log in reversed(adm_logs):
        if not adm_log:
            continue

        downloaded = await asyncio.to_thread(download_latest_adm, guild_id, config, adm_log)
        if not downloaded:
            failed_downloads += 1
            continue

        adm_path = os.path.join(GUILD_DATA_FOLDER, f"{guild_id}.ADM")
        if not os.path.exists(adm_path):
            failed_downloads += 1
            continue

        scanned_logs += 1
        with open(adm_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]

        for line in lines:
            event_type = classify_event(line)
            if not event_type:
                continue

            if event_type == "kill" and not extract_pvp_kill_details(line):
                continue

            line_hash = stable_line_hash(line)
            if not force and line_hash in processed_lines[guild_id]:
                skipped_existing += 1
                continue

            remember_player_location_from_adm(guild_id, line)
            update_player_stats_from_adm(guild_id, event_type, line)
            remember_processed_line(guild_id, line_hash)
            counted_events += 1
            if event_type == "kill":
                counted_kills += 1

    save_player_stats()
    save_processed_adm_lines()

    await interaction.followup.send(
        f"Backfilled leaderboard stats from `{scanned_logs}` ADM files over `{hours}` hours. Counted `{counted_events}` events including `{counted_kills}` PvP kills. Skipped `{skipped_existing}` already-processed events. Failed downloads: `{failed_downloads}`.",
        ephemeral=True
    )


@bot.command()
async def restartserver(ctx):

    if not has_staff_permissions(ctx):
        return

    embed = discord.Embed(
        title="🔄 SERVER RESTART REQUESTED",
        description="Live restart request sent to Nitrado server.",
        color=0xE67E22
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

    print("SERVER RESTART REQUESTED")

    guild_id = str(ctx.guild.id)
    config = guild_configs.get(guild_id, {})

    token = config.get("nitrado_token")
    service_id = config.get("service_id")

    if not token or not service_id:
        return

    try:

        url = (
            f"https://api.nitrado.net/services/"
            f"{service_id}/gameservers/restart"
        )

        headers = {
            "Authorization": f"Bearer {token}"
        }

        restart_response = requests.post(
            url,
            headers=headers,
            timeout=30
        )

        print(f"RESTART STATUS: {restart_response.status_code}")

    except Exception as error:
        print(error)


@bot.command()
async def togglebasedamage(ctx, state: str):

    if not has_staff_permissions(ctx):
        return

    state = state.lower()

    if state not in ["on", "off"]:

        await ctx.send(
            "Usage: `/togglebasedamage state:on` or `/togglebasedamage state:off`"
        )

        return

    guild_id = str(ctx.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": ctx.guild.name, "channels": {}})
    config["base_damage_state"] = state
    save_guild_configs()

    embed = discord.Embed(
        title="🛡️ BASE DAMAGE SETTINGS",
        description=f"Base damage turned {state.upper()}.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

    print(f"BASE DAMAGE {state.upper()}")

# =========================================================
# RESTART SCHEDULER COMMANDS
# =========================================================

@bot.command()
async def setrestartinterval(ctx, hours: int):

    if not has_staff_permissions(ctx):
        return

    if hours < 1 or hours > 24:

        await ctx.send(
            "Restart interval must be between 1 and 24 hours."
        )

        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["restart_interval_hours"] = hours
    guild_configs[guild_id]["restart_schedule_enabled"] = True

    save_guild_configs()

    embed = discord.Embed(
        title="⏰ RESTART INTERVAL UPDATED",
        description=f"Server will now restart every {hours} hours.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def setrestartstart(ctx, hour: int):

    if not has_staff_permissions(ctx):
        return

    if hour < 0 or hour > 23:

        await ctx.send(
            "Start hour must be between 0 and 23 UTC."
        )

        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["restart_start_hour"] = hour
    guild_configs[guild_id]["restart_schedule_enabled"] = True

    save_guild_configs()

    embed = discord.Embed(
        title="🕒 RESTART START HOUR UPDATED",
        description=f"Restart schedule now begins at {hour}:00 UTC.",
        color=0x1ABC9C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def listrestarts(ctx):

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    if config.get("restart_schedule_enabled", True) is False:
        embed = discord.Embed(
            title="RESTART SCHEDULE OFF",
            description="Automatic recurring restarts are disabled. Use `/setrestartinterval` and `/setrestartstart` to set them up again.",
            color=0x95A5A6
        )
        embed.set_thumbnail(url=BOT_IMAGE)
        await ctx.send(embed=style_embed(embed))
        return

    interval = config.get(
        "restart_interval_hours",
        DEFAULT_RESTART_INTERVAL_HOURS
    )

    start_hour = config.get(
        "restart_start_hour",
        0
    )

    times = []

    current = start_hour

    while current < 24:

        times.append(f"{current:02d}:00 UTC")

        current += interval

    embed = discord.Embed(
        title="📢 ACTIVE RESTART SCHEDULE",
        description="\n".join(times),
        color=0xE67E22
    )

    embed.add_field(
        name="Interval",
        value=f"Every {interval} hours",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def cancelrestarts(ctx):

    if not has_staff_permissions(ctx):
        return

    guild_id = str(ctx.guild.id)

    if guild_id not in guild_configs:
        return

    guild_configs[guild_id]["restart_schedule_enabled"] = False
    save_guild_configs()

    embed = discord.Embed(
        title="RESTART SCHEDULE CANCELLED",
        description="Automatic recurring server restarts are now disabled. Manual `/restartserver` still works.",
        color=0xE74C3C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))

# =========================================================
# SCHEDULED RESTART LOOP
# =========================================================

DEFAULT_RESTART_INTERVAL_HOURS = 4

last_restart_hour = {}
restart_warning_tracker = {}


RESTART_COUNTDOWN_WARNINGS = {
    30: {
        "title": "⏰ HEADS UP — SERVER RESTARTING IN 30 MINUTES",
        "body": (
            "Wrap up any firefights, head back toward base, and start "
            "thinking about logging out somewhere safe.\n\n"
            "If you don't, you'll respawn somewhere you didn't want to be."
        ),
        "color": 0x2ECC71,
    },
    15: {
        "title": "⚠️ 15 MINUTES TO RESTART",
        "body": (
            "Stash your loot. Don't start anything new. Drive your car "
            "into a bush you can remember. Avoid logout zones with "
            "zombies camped on top of you."
        ),
        "color": 0xF1C40F,
    },
    5: {
        "title": "🚨 5 MINUTES — TIME TO SAVE YO SHIT",
        "body": (
            "If you're not in a tent or building **right now**, you're "
            "about to lose things. Log out **NOW**. Bushes don't count."
        ),
        "color": 0xE67E22,
    },
    1: {
        "title": "💥 RESTART IN 60 SECONDS",
        "body": (
            "Server restart imminent. Disconnect immediately if you value "
            "your gear. See you on the other side, survivor."
        ),
        "color": 0xE74C3C,
    },
}


RESTART_DOWN_FUNNIES = [
    "Server's down — go touch some grass. The real kind, not the in-game kind. 🌱",
    "Restart in progress. Use this time to question every life decision that led you here.",
    "Server is napping. Maybe make a sandwich? Drink some water? Pretend you have hobbies?",
    "Wandering Bot is rebooting the apocalypse. Please hold while we re-spawn the suffering.",
    "Server is restarting. If you blame the bot, the bot blames you back. It's a healthy relationship.",
    "Off you go, survivor. Stretch, hydrate, and don't punch anyone over a tent location.",
    "Server's having a moment. Give it 5. Don't @ Dave about it.",
    "Restart underway. Touch grass, pet a dog, do laundry, anything except waiting in queue.",
]


def _minutes_until_next_restart(now, restart_offset, restart_interval):
    """Return minutes until the next scheduled restart hour, or None if
    the next restart is further away than the largest configured warning
    threshold."""
    try:
        restart_offset = int(restart_offset or 0) % 24
        restart_interval = int(restart_interval or 0)
    except Exception:
        return None

    if restart_interval <= 0:
        return None

    restart_hours = [
        h for h in range(24)
        if h >= restart_offset and ((h - restart_offset) % restart_interval == 0)
    ]
    if not restart_hours:
        return None

    current_minutes = now.hour * 60 + now.minute
    candidates = []
    for h in restart_hours:
        candidate = h * 60
        delta = candidate - current_minutes
        if delta <= 0:
            delta += 24 * 60
        candidates.append(delta)

    minutes_left = min(candidates) if candidates else None
    if minutes_left is None or minutes_left > max(RESTART_COUNTDOWN_WARNINGS):
        return None
    return minutes_left


@tasks.loop(minutes=1)
async def scheduled_restart_loop():

    global last_restart_hour

    now = datetime.now(UTC)

    current_hour = now.hour
    current_minute = now.minute

    # ────────────────────────────────────────────────────────────────
    # PRE-RESTART COUNTDOWN WARNINGS in general_chat
    # Fires at 30, 15, 5 and 1 minutes before each scheduled restart.
    # Each new warning deletes the previous one so chat never gets
    # spammed with multiple countdowns from the same cycle.
    # ────────────────────────────────────────────────────────────────
    for guild_id, config in active_guild_config_items():
        try:
            if config.get("restart_schedule_enabled", True) is False:
                continue

            restart_interval = int(config.get(
                "restart_interval_hours",
                DEFAULT_RESTART_INTERVAL_HOURS
            ) or DEFAULT_RESTART_INTERVAL_HOURS)
            restart_offset = int(config.get("restart_start_hour", 0) or 0)
            if restart_interval <= 0:
                continue

            minutes_until = _minutes_until_next_restart(now, restart_offset, restart_interval)
            if minutes_until is None:
                continue

            warning = RESTART_COUNTDOWN_WARNINGS.get(minutes_until)
            if not warning:
                continue

            channels = config.get("channels", {})
            # Honour per-guild override: admins can set the countdown to
            # post in a dedicated channel via /extra setcountdownchannel.
            # Falls back to general_chat if no override is configured.
            countdown_channel_id = (
                channels.get("restart_countdown")
                or channels.get("general_chat")
            )
            chat_channel = bot.get_channel(countdown_channel_id)
            if not chat_channel:
                continue

            fired = restart_warning_tracker.setdefault(guild_id, {})
            cycle_key = (current_hour + (minutes_until // 60)) % 24
            cycle_marker = f"{now.date().isoformat()}-{cycle_key:02d}"
            already_fired = fired.setdefault(cycle_marker, set())
            if minutes_until in already_fired:
                continue
            already_fired.add(minutes_until)

            today_marker = now.date().isoformat()
            for stale_key in [k for k in fired if not k.startswith(today_marker)]:
                fired.pop(stale_key, None)

            embed = discord.Embed(
                title=warning["title"],
                description=warning["body"],
                color=warning["color"]
            )
            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Alpha — Pre-Restart Warning")
            embed.timestamp = now

            previous_id = last_restart_countdown_message_ids.get(guild_id)
            if previous_id:
                try:
                    previous_msg = await chat_channel.fetch_message(previous_id)
                    await previous_msg.delete()
                except Exception:
                    pass

            sent = await chat_channel.send(embed=style_embed(embed))
            last_restart_countdown_message_ids[guild_id] = sent.id

        except Exception as countdown_error:
            print(f"RESTART COUNTDOWN ERROR {guild_id}: {countdown_error}")

    for guild_id, config in active_guild_config_items():

        if config.get("restart_schedule_enabled", True) is False:
            continue

        restart_interval = config.get(
            "restart_interval_hours",
            DEFAULT_RESTART_INTERVAL_HOURS
        )

        restart_offset = config.get(
            "restart_start_hour",
            0
        )

        should_restart = (
            current_hour >= restart_offset
            and ((current_hour - restart_offset) % restart_interval == 0)
            and current_minute == 0
        )

        if not should_restart:
            continue

        if last_restart_hour.get(guild_id) == current_hour:
            continue

        last_restart_hour[guild_id] = current_hour

        print(f"SCHEDULED RESTART TRIGGERED {guild_id} @ {current_hour}:00")

        try:

            channels = config.get("channels", {})

            announce_channel = bot.get_channel(
                channels.get("restart_alerts")
            )

            if announce_channel:

                embed = discord.Embed(
                    title="⚠️ SCHEDULED RESTART",
                    description=(
                        f"Automatic restart triggered.\n\n"
                        f"⏰ Interval: Every {restart_interval} hours\n"
                        f"🕒 Current Restart: {current_hour}:00 UTC"
                    ),
                    color=0xE74C3C
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                # Self-clean: delete previous restart-alerts message so
                # at most one is ever visible in the channel.
                previous_alert_id = last_restart_message_ids.get(guild_id)
                if previous_alert_id:
                    try:
                        previous_alert = await announce_channel.fetch_message(previous_alert_id)
                        await previous_alert.delete()
                    except Exception:
                        pass

                sent_alert = await announce_channel.send(
                    embed=style_embed(embed)
                )
                last_restart_message_ids[guild_id] = sent_alert.id

                # Post the "go touch grass" follow-up to the same channel
                # the countdown was using (honours the per-guild override).
                countdown_channel_id = (
                    channels.get("restart_countdown")
                    or channels.get("general_chat")
                )
                chat_channel = bot.get_channel(countdown_channel_id)
                if chat_channel:
                    final_embed = discord.Embed(
                        title="💥 SERVER IS RESTARTING NOW",
                        description=random.choice(RESTART_DOWN_FUNNIES),
                        color=0x95A5A6
                    )
                    final_embed.set_thumbnail(url=BOT_IMAGE)
                    final_embed.set_footer(text="Wandering Bot Alpha — Restart Notice")
                    final_embed.timestamp = now

                    previous_countdown_id = last_restart_countdown_message_ids.get(guild_id)
                    if previous_countdown_id:
                        try:
                            previous_countdown = await chat_channel.fetch_message(previous_countdown_id)
                            await previous_countdown.delete()
                        except Exception:
                            pass

                    sent_final = await chat_channel.send(embed=style_embed(final_embed))
                    last_restart_countdown_message_ids[guild_id] = sent_final.id

                restart_warning_tracker[guild_id] = {}

                token = config.get("nitrado_token")
                service_id = config.get("service_id")

                if token and service_id:

                    try:
                        if delivery_queue or vehicle_rentals_queue or has_active_scenario_events(config):
                            upload_success, _ = await asyncio.to_thread(
                                write_and_upload_delivery_xml,
                                guild_id,
                                config,
                                now
                            )
                            print(f"PRE-RESTART DELIVERY XML UPLOAD {guild_id}: {upload_success}")

                        url = (
                            f"https://api.nitrado.net/services/"
                            f"{service_id}/gameservers/restart"
                        )

                        headers = {
                            "Authorization": f"Bearer {token}"
                        }

                        restart_response = requests.post(
                            url,
                            headers=headers,
                            timeout=30
                        )

                        print(f"AUTO RESTART STATUS: {restart_response.status_code}")

                    except Exception as restart_error:
                        print(restart_error)

        except Exception as error:

            print(error)

# =========================================================
# AI ALERT SYSTEM
# =========================================================

WELCOME_MESSAGES = [
    "Welcome to the apocalypse, survivor. Trust nobody. Especially Dave.",
    "Fresh spawn detected. Someone hide the baked beans.",
    "Welcome in survivor. The wolves can smell fear already.",
    "Another poor soul has entered Chernarus willingly.",
    "Welcome survivor. If you hear footsteps, start panicking.",

    "Welcome to the wasteland, survivor. Try not to die immediately.",
    "Fresh meat has arrived. Someone hide the loot.",
    "Another survivor enters Chernarus with terrible decision making.",
    "Welcome in. Watch out for wolves, snipers, and your own teammates.",
    "Good luck survivor. You're absolutely going to need it."
]

AI_RESPONSES = {
    "angry": "🧠 Maybe log off before you challenge a door to a fist fight.",
    "trash": "💀 DayZ humbles everybody eventually.",
    "lag": "📡 AI Notice: If desync hits, avoid driving unless you enjoy orbiting into space.",
    "hungry": "🥫 Tip: Fishing gear is more valuable than most guns early game.",
    "bear": "🐻 AI Warning: If you hear the bear first, it's probably too late.",
    "raid": "🧠 Tip: Metal doors buy time. Hidden loot buys survival.",
    "loot": "🧠 Tip: Medical buildings and hunting camps are usually worth checking.",
    "base": "🧠 Tip: Small hidden stashes survive longer than giant compounds.",
    "cheater": "🧠 AI Watch: Record clips and timestamps before reporting suspicious activity.",
    "dead": "💀 DayZ teaches lessons the painful way.",
    "fuck": "💸 Calm down survivor, the swear jar is getting rich.",
    "shit": "🧠 Tactical advice: panicking rarely improves aim."
}

AI_KEYWORDS = [
    "raid",
    "explosive",
    "helicrash",
    "admin",
    "cheater",
    "speedhack",
    "base damage"
]

FUNNY_ROTATION = [
    "🧠 Pro tip: if you hear wolves, you are the side quest.",
    "💀 DayZ is 10% aim and 90% bad life choices.",
    "🥫 Beans are temporary. Trauma is forever.",
    "📻 If your friend says 'trust me', do not trust them.",
    "🧤 Helpful advice: carry bandages before ego."
]

async def send_ai_alert(guild_id, config, line):

    channels = config.get("channels", {})

    ai_channel = bot.get_channel(
        channels.get("ai_chat")
    )

    if not ai_channel:
        return

    embed = discord.Embed(
        title="🧠 AI ALERT",
        description=line,
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ai_channel.send(
        embed=style_embed(embed)
    )


# =========================================================
# CUSTOM SCHEDULED FEEDS
# =========================================================

def custom_feeds_for_config(config):
    return config.setdefault("custom_feeds", [])


def next_custom_feed_id(config):
    existing = [int(feed.get("id", 0)) for feed in custom_feeds_for_config(config)]
    return (max(existing) if existing else 0) + 1


async def send_custom_feed_message(guild_id, config, feed):
    channel = bot.get_channel(int(feed.get("channel_id", 0)))
    if not channel:
        return False, "Channel missing"

    feed_type = str(feed.get("feed_type", "text")).lower()
    message = str(feed.get("message", "")).strip()
    color = 0x1ABC9C
    title = "WANDERING FEED"
    description = message or "Scheduled feed pulse."

    if feed_type == "restart":
        interval = config.get("restart_interval_hours", DEFAULT_RESTART_INTERVAL_HOURS)
        start_hour = config.get("restart_start_hour", 0)
        title = "SCHEDULED RESTART FEED"
        description = message or f"Restart schedule is every {interval} hours starting at {start_hour:02d}:00 UTC."
        color = 0xE67E22
    elif feed_type == "basedamage":
        state = str(config.get("base_damage_state", "unknown")).upper()
        title = "BASE DAMAGE FEED"
        description = message or f"Base damage is currently `{state}`."
        color = 0x3498DB
    elif feed_type == "serverstatus":
        ensure_guild_runtime(guild_id)
        title = "SERVER STATUS FEED"
        description = message or f"Tracked survivors online: `{len(online_players.get(str(guild_id), set()))}`. ADM loop: `{'running' if adm_loop.is_running() else 'stopped'}`."
        color = 0x2ECC71
    elif feed_type == "heatmap":
        heatmap_mode = guild_heatmap_mode(guild_id)
        title = f"{server_map_key(guild_id).upper()} {heatmap_mode.upper()} HEATMAP FEED"
        counts = heat_counts_for_mode(guild_id, heatmap_mode)
        hottest = sorted(counts.items(), key=lambda row: row[1], reverse=True)[:5]
        description = message or "\n".join(f"{zone}: {count}" for zone, count in hottest) or f"No {heatmap_mode} activity yet."
        color = 0x9B59B6

    embed = discord.Embed(title=title, description=description[:1800], color=color)
    embed.add_field(name="Feed Type", value=feed_type, inline=True)
    embed.add_field(name="Interval", value=f"{feed.get('interval_minutes')} minutes", inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Custom Scheduled Feed")

    if feed_type == "heatmap":
        heatmap_path = generate_guild_heatmap_image(guild_id, guild_heatmap_mode(guild_id))
        file = discord.File(heatmap_path, filename="custom_heatmap.png")
        embed.set_image(url="attachment://custom_heatmap.png")
        await channel.send(embed=style_embed(embed), file=file)
        try:
            os.remove(heatmap_path)
        except Exception:
            pass
    else:
        await channel.send(embed=style_embed(embed))

    return True, "Sent"


@tasks.loop(minutes=1)
async def custom_feed_loop():
    now_ts = datetime.now(UTC).timestamp()

    for guild_id, config in active_guild_config_items():
        for feed in custom_feeds_for_config(config):
            try:
                if not feed.get("enabled", True):
                    continue
                interval_minutes = int(feed.get("interval_minutes", 60))
                interval_minutes = max(5, min(10080, interval_minutes))
                last_post = float(feed.get("last_post_ts", 0))
                if now_ts - last_post < interval_minutes * 60:
                    continue
                success, message = await send_custom_feed_message(guild_id, config, feed)
                feed["last_post_ts"] = now_ts
                feed["last_result"] = message
                feed["last_success"] = success
                save_guild_configs()
            except Exception as error:
                feed["last_result"] = str(error)
                feed["last_success"] = False
                save_guild_configs()
                print(f"CUSTOM FEED ERROR {guild_id}: {error}")


@tasks.loop(minutes=1)
async def wage_loop():
    now_ts = datetime.now(UTC).timestamp()

    for guild_id, config in active_guild_config_items():
        changed = False
        for wage in config.get("recurring_wages", []):
            try:
                if not wage.get("enabled", True):
                    continue

                interval_seconds = max(3600, int(wage.get("interval_hours", 24)) * 3600)
                last_paid = float(wage.get("last_paid_ts", 0))
                if now_ts - last_paid < interval_seconds:
                    continue

                user_id = str(wage.get("user_id"))
                wallet = wallets.setdefault(user_id, {
                    "name": wage.get("name", user_id),
                    "balance": 0,
                    "daily_transactions": 0
                })
                amount = int(wage.get("amount", 0))
                if amount <= 0:
                    continue

                wallet["balance"] = wallet.get("balance", 0) + amount
                wage["last_paid_ts"] = now_ts
                changed = True

                channel = bot.get_channel(config.get("channels", {}).get("economy"))
                if channel:
                    embed = discord.Embed(
                        title="RECURRING WAGE PAID",
                        description=f"<@{user_id}> received `{amount}` pennies.",
                        color=0x2ECC71
                    )
                    embed.add_field(name="Reason", value=wage.get("reason", "Server wage"), inline=False)
                    embed.add_field(name="New Balance", value=f"{wallet['balance']} pennies", inline=True)
                    embed.set_thumbnail(url=BOT_IMAGE)
                    embed.set_footer(text="Wandering Bot Alpha - Economy Payroll")
                    await channel.send(embed=style_embed(embed))

            except Exception as error:
                print(f"WAGE LOOP ERROR {guild_id}: {error}")

        if changed:
            save_wallets()
            save_guild_configs()


@bot.tree.command(name="addfeed", description="Admin: create a scheduled custom feed in a channel")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Channel to post into", feed_type="text, restart, basedamage, serverstatus, or heatmap", interval_minutes="How often to post, 5 to 10080 minutes", message="Optional custom text for the feed")
async def addfeed(interaction: discord.Interaction, channel: discord.TextChannel, feed_type: str, interval_minutes: int, message: str = ""):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    feed_type = feed_type.lower().strip()
    if feed_type not in CUSTOM_FEED_TYPES:
        await interaction.response.send_message(f"Feed type must be one of: {', '.join(CUSTOM_FEED_TYPES)}", ephemeral=True)
        return
    interval_minutes = max(5, min(10080, int(interval_minutes)))
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    feed = {"id": next_custom_feed_id(config), "channel_id": channel.id, "feed_type": feed_type, "interval_minutes": interval_minutes, "message": message[:1800], "enabled": True, "created_by": str(interaction.user.id), "last_post_ts": 0}
    custom_feeds_for_config(config).append(feed)
    save_guild_configs()
    await interaction.response.send_message(f"Feed `{feed['id']}` created: `{feed_type}` into {channel.mention} every {interval_minutes} minutes.", ephemeral=True)


@bot.tree.command(name="listfeeds", description="Admin: list scheduled custom feeds")
@app_commands.default_permissions(administrator=True)
async def listfeeds(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    config = guild_configs.get(str(interaction.guild.id), {})
    feeds = custom_feeds_for_config(config)
    if not feeds:
        await interaction.response.send_message("No custom feeds configured.", ephemeral=True)
        return
    lines = []
    for feed in feeds[:20]:
        channel = interaction.guild.get_channel(int(feed.get("channel_id", 0)))
        channel_name = channel.mention if channel else "missing-channel"
        state = "on" if feed.get("enabled", True) else "off"
        lines.append(f"`{feed.get('id')}` {state} `{feed.get('feed_type')}` -> {channel_name} every {feed.get('interval_minutes')}m")
    embed = discord.Embed(title="CUSTOM FEEDS", description="\n".join(lines), color=0x1ABC9C)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="togglefeed", description="Admin: turn a custom feed on or off")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feed_id="Feed ID from /listfeeds", enabled="True to enable, false to disable")
async def togglefeed(interaction: discord.Interaction, feed_id: int, enabled: bool):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    config = guild_configs.get(str(interaction.guild.id), {})
    for feed in custom_feeds_for_config(config):
        if int(feed.get("id", 0)) == int(feed_id):
            feed["enabled"] = bool(enabled)
            save_guild_configs()
            await interaction.response.send_message(f"Feed `{feed_id}` is now {'on' if enabled else 'off'}.", ephemeral=True)
            return
    await interaction.response.send_message("Feed ID not found.", ephemeral=True)


@bot.tree.command(name="removefeed", description="Admin: remove a custom scheduled feed")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(feed_id="Feed ID from /listfeeds")
async def removefeed(interaction: discord.Interaction, feed_id: int):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    config = guild_configs.get(str(interaction.guild.id), {})
    feeds = custom_feeds_for_config(config)
    kept = [feed for feed in feeds if int(feed.get("id", 0)) != int(feed_id)]
    if len(kept) == len(feeds):
        await interaction.response.send_message("Feed ID not found.", ephemeral=True)
        return
    config["custom_feeds"] = kept
    save_guild_configs()
    await interaction.response.send_message(f"Feed `{feed_id}` removed.", ephemeral=True)


@bot.tree.command(name="setaiimages", description="Admin: configure occasional AI generated DayZ-style pictures")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    enabled="Turn occasional AI pictures on or off",
    channel="Channel where pictures should be posted",
    style="funny, gritty, or pinup",
    cooldown_hours="Minimum hours between random picture posts, 1 to 72"
)
async def setaiimages(
    interaction: discord.Interaction,
    enabled: bool,
    channel: discord.TextChannel = None,
    style: str = "funny",
    cooldown_hours: int = 6
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    style = str(style or "funny").lower().strip()
    if style not in AI_IMAGE_PROMPTS:
        await interaction.response.send_message("Style must be `funny`, `gritty`, or `pinup`.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    settings = ai_image_config(config)
    settings["enabled"] = bool(enabled)
    settings["style"] = style
    settings["cooldown_seconds"] = max(1, min(72, int(cooldown_hours or 6))) * 3600

    if channel:
        settings["channel_id"] = channel.id

    save_guild_configs()

    target_channel = channel.mention if channel else "auto-selected chat channel"
    api_note = "" if OPENAI_API_KEY else "\nWarning: `OPENAI_API_KEY` is not set, so images will not generate until it is added."
    await interaction.response.send_message(
        f"AI pictures are now `{'on' if enabled else 'off'}`. Style: `{style}`. Channel: {target_channel}. Cooldown: `{settings['cooldown_seconds'] // 3600}`h.{api_note}",
        ephemeral=True
    )


@bot.tree.command(name="aiimagepostnow", description="Admin: post one AI generated DayZ-style picture now")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(style="Optional style override: funny, gritty, or pinup")
async def aiimagepostnow(interaction: discord.Interaction, style: str = ""):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id, {})
    settings = ai_image_config(config)
    chosen_style = str(style or settings.get("style") or "funny").lower().strip()

    if chosen_style not in AI_IMAGE_PROMPTS:
        await interaction.response.send_message("Style must be `funny`, `gritty`, or `pinup`.", ephemeral=True)
        return

    if not OPENAI_API_KEY:
        await interaction.response.send_message("`OPENAI_API_KEY` is not set, so I cannot generate images yet.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    image_bytes, error = await asyncio.to_thread(generate_ai_image_bytes, chosen_style)
    if error:
        await interaction.followup.send(f"Image generation failed: `{error[:900]}`", ephemeral=True)
        return

    file = discord.File(io.BytesIO(image_bytes), filename="wandering_postcard.png")
    embed = discord.Embed(
        title="WANDERING BOT POSTCARD",
        description=random.choice(AI_IMAGE_CAPTIONS),
        color=0x9B59B6
    )
    embed.set_image(url="attachment://wandering_postcard.png")
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - AI Generated DayZ-Inspired Art")
    embed.timestamp = datetime.now(UTC)
    await interaction.channel.send(embed=style_embed(embed), file=file)
    last_ai_image_time[guild_id] = datetime.now(UTC).timestamp()
    await interaction.followup.send("Posted one AI picture.", ephemeral=True)
# =========================================================
# PVE QUEST SYSTEM
# =========================================================

PVE_CHALLENGE_BANK = [
    {
        "kind": "Hunting",
        "title": "Campfire Supper",
        "goal": "Hunt {count} deer, boar, goat, sheep, cow, or stag and bring proof to staff.",
        "reward": "Admin-chosen pennies, food, ammo, or medical kit.",
        "tips": "Try forest edges, open fields near farms, and quiet inland valleys."
    },
    {
        "kind": "Hunting",
        "title": "Predator Control",
        "goal": "Clear {count} wolves or bears as a group challenge.",
        "reward": "Admin-chosen weapons, ammo, or faction supplies.",
        "tips": "Travel warm, carry bandages, and do not fight predators in thick trees unless you enjoy screaming."
    },
    {
        "kind": "Collection",
        "title": "Medical Run",
        "goal": "Collect {count} medical items: tetra, charcoal, vitamins, bandages, saline, or morphine.",
        "reward": "Admin-chosen medical bundle or pennies.",
        "tips": "Clinics, hospitals, summer camps, and hunting camps are worth checking."
    },
    {
        "kind": "Collection",
        "title": "Pantry Raid",
        "goal": "Collect {count} sealed food or drink items for a survivor stash.",
        "reward": "Admin-chosen food crate or shop credit.",
        "tips": "Coastal towns are fine early, but inland houses and hunting cabins are usually less picked clean."
    },
    {
        "kind": "Repair",
        "title": "Roadside Rescue",
        "goal": "Find and repair one working vehicle part set: spark plug, battery, radiator, and fuel.",
        "reward": "Admin-chosen vehicle supplies or fuel reward.",
        "tips": "Industrial sheds, garages, and vehicle wrecks are your best bet."
    },
    {
        "kind": "Explorer",
        "title": "Quiet Places",
        "goal": "Visit {count} named towns or landmarks and post screenshots.",
        "reward": "Admin-chosen exploration reward.",
        "tips": "Move light, avoid obvious roads, and mark your route before the server teaches you humility."
    },
    {
        "kind": "Survival",
        "title": "Off-Grid Night",
        "goal": "Survive one full night cycle with only hunted, fished, or foraged food.",
        "reward": "Admin-chosen survival bundle.",
        "tips": "A knife, rope, bones, hooks, and patience. That last one is usually where people fall apart."
    },
    {
        "kind": "Fishing",
        "title": "River Supper",
        "goal": "Catch {count} fish and cook them at a campfire.",
        "reward": "Admin-chosen food reward, cooking kit, or pennies.",
        "tips": "Bones make hooks, rope makes a fishing rod, and quiet water beats sprinting around hungry like a muppet."
    },
    {
        "kind": "Fishing",
        "title": "Coastal Angler",
        "goal": "Catch {count} fish from coastal water and post proof of the catch.",
        "reward": "Admin-chosen coastal survivor kit.",
        "tips": "The coast can feed you if you stop treating it like a loading screen."
    },
    {
        "kind": "Crafting",
        "title": "Bushcraft Basics",
        "goal": "Craft a fireplace, hand drill kit, improvised fishing rod, and stone knife.",
        "reward": "Admin-chosen survival tools or shop credit.",
        "tips": "Small stones, bark, sticks, rope, and bones are worth more than panic."
    },
    {
        "kind": "Crafting",
        "title": "Field Medic",
        "goal": "Prepare {count} clean bandages or medical supplies and deliver them to a safe stash.",
        "reward": "Admin-chosen medical reward.",
        "tips": "Disinfected gear saves lives. Dirty rags save nobody, except maybe the infection."
    },
    {
        "kind": "Collection",
        "title": "Mechanic's Shopping List",
        "goal": "Collect a spark plug, car battery, truck battery, radiator, tire repair kit, and fuel can.",
        "reward": "Admin-chosen vehicle reward.",
        "tips": "Garages, sheds, industrial yards, and wrecks are the places to haunt."
    },
    {
        "kind": "Collection",
        "title": "Warm Hands, Warm Head",
        "goal": "Collect {count} warm clothing items: gloves, hats, jackets, boots, or hunting clothes.",
        "reward": "Admin-chosen winter kit or pennies.",
        "tips": "Hunting cabins and inland villages are usually better than coastal leftovers."
    },
    {
        "kind": "Explorer",
        "title": "Radio Tower Run",
        "goal": "Visit {count} radio towers, castles, camps, or named landmarks and post screenshots.",
        "reward": "Admin-chosen expedition reward.",
        "tips": "Bring binoculars, food, and enough sense to leave before the shooting starts."
    },
    {
        "kind": "Explorer",
        "title": "Pilgrim Trail",
        "goal": "Travel from the coast to an inland safe zone without using a vehicle.",
        "reward": "Admin-chosen travel reward.",
        "tips": "Navigation, water stops, and not sprinting everywhere like an idiot are the real challenge."
    },
    {
        "kind": "Rescue",
        "title": "Medic Escort",
        "goal": "Escort another survivor to a clinic, camp, or safe base and keep them alive.",
        "reward": "Admin-chosen team reward.",
        "tips": "A good escort watches tree lines. A bad escort asks why everyone is dead."
    },
    {
        "kind": "Base Support",
        "title": "Camp Builder",
        "goal": "Gather {count} base supplies: nails, planks, rope, wire, tools, or code locks.",
        "reward": "Admin-chosen building supply reward.",
        "tips": "Industrial zones, sheds, and lumber piles make builders happy. Raiders are also happy, but ignore that."
    },
    {
        "kind": "Zombie Control",
        "title": "Town Cleanup",
        "goal": "Clear {count} infected from a town, clinic, police station, or military camp.",
        "reward": "Admin-chosen ammo, food, or medical reward.",
        "tips": "Use doors, spacing, and quiet weapons. Running into the street yelling is a lifestyle choice, not a tactic."
    },
    {
        "kind": "Treasure Hunt",
        "title": "Cache Finder",
        "goal": "Find a buried stash, hidden crate, or abandoned camp and post proof without revealing the exact spot publicly.",
        "reward": "Admin-chosen discovery reward.",
        "tips": "Look for disturbed ground, odd tree lines, and places players think are clever. They usually are not."
    },
]


PVE_GENERATED_QUEST_SEEDS = [
    ("Hunting", "Deer Trail", "Hunt {count} deer, stag, or doe and return with proof.", "animal_kill", 500, "Easy", "Move along forest edges and listen more than you sprint."),
    ("Hunting", "Farmyard Forager", "Hunt {count} chickens, goats, sheep, cows, or pigs.", "animal_kill", 450, "Easy", "Farms and small villages are better than wandering in circles swearing at bushes."),
    ("Hunting", "Wolf Line", "Survive and clear {count} wolves.", "animal_kill", 900, "Medium", "Bandages first, confidence second. Wolves love idiots with empty stamina."),
    ("Hunting", "Bear Story", "Bring down {count} bear as a squad and live to brag about it.", "animal_kill", 1800, "Hard", "Shoot together, spread out, and avoid heroic solo nonsense."),
    ("Zombie Control", "Clinic Sweep", "Clear {count} infected near medical buildings.", "zombie_kill", 650, "Easy", "Doors, blades, stamina. The holy trinity of not getting slapped silly."),
    ("Zombie Control", "Police Station Cleanup", "Clear {count} infected around police or security buildings.", "zombie_kill", 750, "Medium", "Keep it quiet unless you want every infected in town joining your committee meeting."),
    ("Zombie Control", "Camp Sanitiser", "Clear {count} infected from camps, checkpoints, or military tents.", "zombie_kill", 1100, "Hard", "Good loot usually has bad neighbours."),
    ("Base Support", "Quiet Builder", "Place or build {count} useful camp structures or storage items.", "placed", 700, "Easy", "Small camps make better stories than giant raid invitations."),
    ("Base Support", "Supply Stacker", "Place {count} crates, barrels, tents, shelters, or storage pieces.", "placed", 850, "Medium", "Hide it like you care about keeping it."),
    ("Crafting", "Camp Hands", "Craft or place {count} camp utility items.", "placed", 800, "Medium", "Fireplaces, shelters and storage turn panic into a plan."),
    ("Explorer", "Northern Drift", "Visit {count} northern landmarks and post screenshots.", None, 900, "Medium", "The north rewards patience and punishes tourist behaviour."),
    ("Explorer", "Coastal Memory", "Visit {count} coastal landmarks without using a vehicle.", None, 500, "Easy", "The coast is not just where people yell for apples."),
    ("Explorer", "Castle Loop", "Visit {count} castles, towers, or ruins and post proof.", None, 1000, "Medium", "Old stones, good views, terrible ambush potential."),
    ("Fishing", "Still Water", "Catch and cook {count} fish.", None, 600, "Easy", "Fish quests are peace with a side order of bone hooks."),
    ("Fishing", "Feast Prep", "Catch {count} fish and deliver them to a camp or faction stash.", None, 900, "Medium", "A fed group makes fewer stupid decisions. Usually."),
    ("Collection", "Medicine Cabinet", "Collect {count} medical supplies and post proof.", None, 700, "Easy", "Tetra, charcoal, vitamins, saline, morphine, bandages. Hoard responsibly."),
    ("Collection", "Warm Kit", "Collect {count} warm clothing pieces for cold-weather survivors.", None, 650, "Easy", "Gloves are not glamorous, but neither is frostbite."),
    ("Collection", "Builder's Bundle", "Collect {count} building supplies: nails, planks, wire, rope, locks, or tools.", None, 900, "Medium", "Every nail has a destiny. Usually in a wall someone later complains about."),
    ("Repair", "Garage Goblin", "Find a working vehicle part set and post proof.", None, 1200, "Hard", "Battery, plug, radiator, fuel. Then the car may still betray you."),
    ("Rescue", "Good Samaritan", "Escort or resupply another survivor and post proof.", None, 1000, "Medium", "PVE is better when someone else survives because you showed up."),
    ("Treasure Hunt", "Little Mystery", "Find a scenic, hidden, or strange spot and post a screenshot clue.", None, 600, "Easy", "Discovery counts. Not everything needs to bleed."),
    ("Treasure Hunt", "Lost Cache", "Find or create a small hidden cache for another survivor to discover.", None, 1300, "Hard", "Leave a story, not just loot."),
    ("Survival", "Rainwalk", "Travel during bad weather and reach shelter with proof.", None, 800, "Medium", "Sometimes the mission is just getting warm again."),
    ("Survival", "No-Shop Supper", "Feed yourself from hunting, fishing, or foraging only.", None, 900, "Medium", "Escape, not grind. Make a little camp and breathe for once."),
]

PVE_CHAIN_QUESTS = [
    {
        "kind": "Quest Line",
        "title": "The Hermit's Map I",
        "goal": "Find a quiet landmark and post a screenshot clue. This starts the Hermit's Map line.",
        "reward": "700 pennies and access to the next story step.",
        "tips": "Look for places people pass without seeing.",
        "difficulty": "Easy",
        "reward_pennies": 700,
        "quest_line": "The Hermit's Map",
        "target_event": None,
    },
    {
        "kind": "Quest Line",
        "title": "The Hermit's Map II",
        "goal": "Travel to a second landmark at least one region away and post proof.",
        "reward": "1200 pennies and a larger expedition reward.",
        "tips": "A journey feels better when it has a reason.",
        "difficulty": "Medium",
        "reward_pennies": 1200,
        "quest_line": "The Hermit's Map",
        "target_event": None,
    },
    {
        "kind": "Quest Line",
        "title": "The Hermit's Map III",
        "goal": "Build a tiny traveller cache with food, fire, and one useful tool for the next survivor.",
        "reward": "2500 pennies and admin-chosen rare reward.",
        "tips": "The best PVE stories leave something behind.",
        "difficulty": "Hard",
        "reward_pennies": 2500,
        "quest_line": "The Hermit's Map",
        "target_event": "placed",
        "target_count": 3,
    },
    {
        "kind": "Quest Line",
        "title": "Warden of the Woods I",
        "goal": "Hunt {count} wild animals without dying.",
        "reward": "900 pennies and the next hunt unlock.",
        "tips": "The woods pay attention. Try doing the same.",
        "difficulty": "Medium",
        "reward_pennies": 900,
        "quest_line": "Warden of the Woods",
        "target_event": "animal_kill",
    },
    {
        "kind": "Quest Line",
        "title": "Warden of the Woods II",
        "goal": "Clear {count} predators or infected from a wilderness route.",
        "reward": "1800 pennies and admin-chosen hunter gear.",
        "tips": "This is where the woods start negotiating with your ammo count.",
        "difficulty": "Hard",
        "reward_pennies": 1800,
        "quest_line": "Warden of the Woods",
        "target_event": "animal_kill",
    },
]

for idx, seed in enumerate(PVE_GENERATED_QUEST_SEEDS, start=1):
    kind, title, goal, target_event, reward_pennies, difficulty, tips = seed
    for variant in range(1, 4):
        PVE_CHALLENGE_BANK.append({
            "kind": kind,
            "title": f"{title} {variant}",
            "goal": goal,
            "reward": f"{reward_pennies + (variant * 75)} pennies plus any admin bonus.",
            "tips": tips,
            "difficulty": difficulty,
            "reward_pennies": reward_pennies + (variant * 75),
            "target_event": target_event,
        })

PVE_CHALLENGE_BANK.extend(PVE_CHAIN_QUESTS)

PVE_INFO_TOPICS = {
    "loot": (
        "Loot tip: food and knives first, meds second, weapons third. Police stations, hunting camps, "
        "medical buildings, summer camps, and military tents all have different value. Stop checking the same empty shed like it owes you rent."
    ),
    "hunting": (
        "Hunting tip: animals like open fields, forest edges, farms, and quiet inland routes. Listen before sprinting in. "
        "Wolves mean free meat if you are prepared, and a funeral if you are not."
    ),
    "medical": (
        "Medical tip: keep disinfected bandages, tetra, charcoal, vitamins, and a blood/saline plan. "
        "Dirty rags and mystery pond water are how survivors become cautionary decoration."
    ),
    "building": (
        "Building tip: hidden, ugly, and boring survives longer than huge and shiny. Stash smart, keep tools split, and do not advertise your life savings with walls."
    ),
    "vehicles": (
        "Vehicle tip: spark plug, battery, radiator, fuel, water in the radiator, then drive gently. "
        "DayZ cars punish confidence with physics lessons."
    ),
    "fishing": (
        "Fishing tip: bones make hooks, rope makes a rod, and worms help. Cook the fish before eating unless your survivor is auditioning for stomach problems."
    ),
    "crafting": (
        "Crafting tip: bark, sticks, rope, bones, stones, rags, and duct tape solve more problems than people admit. Carry a blade and stop binning useful junk."
    ),
    "expeditions": (
        "Expedition tip: plan water stops, move through cover, carry a compass, and leave space for loot. The long way round is often the alive way round."
    ),
    "collections": (
        "Collection tip: split the shopping list between players. One person checks medical, one hits sheds, one covers food. Teamwork, tragically, works."
    ),
    "zombies": (
        "Infected tip: doors are weapons, stamina is life, and loud guns invite an audience. A quiet blade saves ammo and dignity."
    ),
}

PVE_DAILY_HELP_LINES = [
    ("Quest Proof", "For collection, fishing, crafting, and exploration quests, screenshots or clips make staff approval painless. Show the item, place, or finished craft clearly."),
    ("Tracking", "Hunting, infected, placement, and some building quests can be tracked from ADM logs. Link your gamertag with `/linkgamer` so rewards can pay automatically."),
    ("PVE Loadout", "Carry a blade, bandages, food, water, rope, and a quiet weapon. PVE is calmer than PvP until it suddenly is not."),
    ("Team Runs", "Split collection quests between players. One survivor handles medical, one handles food, one handles sheds and tools."),
    ("Expeditions", "For long travel quests, plan water stops first. The quickest route is not always the route that gets everyone home.")
]

PVP_INTEL_LINES = [
    "PvP reminder: distance, cover, and patience win more fights than panic spraying at a moving tree line.",
    "Longshot hunters: good angles matter. If you can see the whole valley, the whole valley can sometimes see you back.",
    "Raid-zone wisdom: record clips, timestamps, and coordinates before the argument starts.",
    "If the shot sounds close, move first and investigate second. Curiosity has a terrible K/D ratio.",
    "Check your exits before you start looting a body. The second survivor is often the expensive one."
]


def pve_config(config):
    return config.setdefault("pve", {"enabled": True, "interval_hours": 12})


def pve_reward_for_difficulty(difficulty):
    return {
        "Easy": 350,
        "Medium": 800,
        "Hard": 1500,
        "Legendary": 3000,
    }.get(difficulty, 600)


def pve_target_count(template, count):
    if template.get("target_count"):
        return int(template.get("target_count"))
    if template.get("target_event"):
        return int(count)
    return 0


def generate_pve_quest_code():
    existing_codes = {
        str(quest.get("quest_code", "")).upper()
        for guild_quests in pve_challenges.values()
        for quest in guild_quests
    }

    for _ in range(25):
        code = f"PVE-{random.randint(100000, 999999)}"
        if code not in existing_codes:
            return code

    return f"PVE-{int(datetime.now(UTC).timestamp())}"


def pve_quest_code(challenge):
    code = str(challenge.get("quest_code") or "").strip().upper()
    if code:
        return code

    old_id = str(challenge.get("id") or "").strip()
    if old_id:
        suffix = re.sub(r"\D", "", old_id)[-6:]
        code = f"PVE-{suffix or old_id[-6:].upper()}"
    else:
        code = generate_pve_quest_code()

    challenge["quest_code"] = code
    return code


def find_active_pve_quest_by_code(guild_id, quest_code):
    wanted = str(quest_code or "").strip().upper()
    if wanted.isdigit():
        wanted = f"PVE-{wanted}"

    for challenge in pve_challenges.get(str(guild_id), []):
        if challenge.get("status") != "active":
            continue
        if pve_quest_code(challenge) == wanted:
            return challenge

    return None


def generate_pve_challenge(kind=None, difficulty=None):
    candidates = PVE_CHALLENGE_BANK
    if kind:
        wanted = str(kind).lower()
        candidates = [
            challenge for challenge in PVE_CHALLENGE_BANK
            if str(challenge.get("kind", "")).lower() == wanted
        ] or PVE_CHALLENGE_BANK

    if difficulty:
        wanted_difficulty = str(difficulty).title()
        difficulty_candidates = [
            challenge for challenge in candidates
            if str(challenge.get("difficulty", "")).title() == wanted_difficulty
        ]
        if difficulty_candidates:
            candidates = difficulty_candidates

    template = random.choice(candidates)
    difficulty = str(difficulty or template.get("difficulty") or random.choice(["Easy", "Easy", "Medium", "Medium", "Hard"])).title()
    count_choices = {
        "Easy": [2, 3, 4, 5],
        "Medium": [5, 7, 8, 10],
        "Hard": [10, 12, 15],
        "Legendary": [15, 20, 25],
    }.get(difficulty, [3, 5, 7])
    count = random.choice(count_choices)
    reward_pennies = int(template.get("reward_pennies", pve_reward_for_difficulty(difficulty)))
    target_count = pve_target_count(template, count)
    return {
        "id": f"pve-{int(datetime.now(UTC).timestamp())}-{random.randint(1000, 9999)}",
        "quest_code": generate_pve_quest_code(),
        "kind": template["kind"],
        "title": template["title"],
        "goal": template["goal"].format(count=count),
        "reward": template.get("reward", f"{reward_pennies} pennies plus any admin bonus."),
        "reward_pennies": reward_pennies,
        "difficulty": difficulty,
        "tips": template["tips"],
        "target_event": template.get("target_event"),
        "target_count": target_count,
        "progress": {},
        "quest_line": template.get("quest_line"),
        "created": str(datetime.now(UTC)),
        "status": "active"
    }


def pve_themed_channel_key(challenge):
    return {
        "hunting": "pve_hunting",
        "fishing": "pve_fishing",
        "collection": "pve_collection",
        "crafting": "pve_crafting",
        "repair": "pve_crafting",
        "explorer": "pve_expeditions",
        "survival": "pve_expeditions",
        "rescue": "pve_expeditions",
        "base support": "pve_crafting",
        "zombie control": "pve_expeditions",
        "treasure hunt": "pve_expeditions",
        "quest line": "pve_expeditions",
    }.get(str(challenge.get("kind", "")).lower())


def pve_channel_for_kind(kind):
    return {
        "hunting": "pve_hunting",
        "collection": "pve_collection",
        "fishing": "pve_fishing",
        "crafting": "pve_crafting",
        "repair": "pve_crafting",
        "explorer": "pve_expeditions",
        "survival": "pve_expeditions",
        "rescue": "pve_expeditions",
        "treasure hunt": "pve_expeditions",
        "quest line": "pve_expeditions",
    }.get(str(kind).lower())


def pve_active_quest_for_channel(guild_id, channel_key, difficulty=None):
    wanted_difficulty = str(difficulty).title() if difficulty else None
    for challenge in reversed(pve_challenges.get(str(guild_id), [])):
        if challenge.get("status") != "active" or challenge.get("channel_key") != channel_key:
            continue
        if wanted_difficulty and str(challenge.get("difficulty", "")).title() != wanted_difficulty:
            continue
        return challenge
    return None


def has_active_pve_kind(guild_id, kind):
    wanted = str(kind).lower()
    for challenge in pve_challenges.get(str(guild_id), []):
        if challenge.get("status") == "active" and str(challenge.get("kind", "")).lower() == wanted:
            return True
    return False


def linked_user_id_for_player(player_name):
    wanted = normalize_discord_name(player_name)
    for user_id, data in linked_players.items():
        if data.get("verified_by") != "ADM":
            continue
        if normalize_discord_name(data.get("gamertag", "")) == wanted:
            return str(user_id)
    return None


def award_pve_pennies(player_name, challenge):
    user_id = linked_user_id_for_player(player_name)
    if not user_id:
        return False, "No linked Discord member found"

    wallet = wallets.setdefault(user_id, {
        "name": linked_players.get(user_id, {}).get("discord_name", player_name),
        "balance": 0,
        "daily_transactions": 0
    })
    reward = int(challenge.get("reward_pennies", 0))
    wallet["balance"] = wallet.get("balance", 0) + reward
    save_wallets()
    return True, f"{reward} pennies paid"


def pve_progress_text(challenge):
    target_count = int(challenge.get("target_count", 0) or 0)
    if not target_count:
        return "Manual approval"

    progress = challenge.get("progress", {})
    if not progress:
        return f"0/{target_count}"

    leader, amount = max(progress.items(), key=lambda row: row[1])
    return f"{leader}: {amount}/{target_count}"


async def post_pve_challenge(guild_id, config, *, manual=False):
    guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if not guild:
        return False, "Guild not found"

    channels = config.setdefault("channels", {})
    quest_channel = bot.get_channel(channels.get("pve_quests"))
    if not quest_channel:
        created = await ensure_pve_channels(guild, config)
        quest_channel = created.get("pve_quests")

    if not quest_channel:
        return False, "PVE quest channel missing"

    challenge = generate_pve_challenge()
    guild_challenges = pve_challenges.setdefault(str(guild_id), [])
    guild_challenges.append(challenge)
    pve_challenges[str(guild_id)] = guild_challenges[-25:]
    save_pve_challenges()

    embed = discord.Embed(
        title=f"🌲 PVE QUEST: {challenge['title']}",
        color=0x2ECC71
    )
    embed.add_field(name="Type", value=challenge["kind"], inline=True)
    embed.add_field(name="Quest ID", value=f"`{pve_quest_code(challenge)}`", inline=True)
    embed.add_field(name="Difficulty", value=challenge.get("difficulty", "Medium"), inline=True)
    embed.add_field(name="Status", value="Manual Post" if manual else "Auto Generated", inline=False)
    embed.add_field(name="Objective", value=challenge["goal"], inline=False)
    embed.add_field(name="Reward", value=challenge["reward"], inline=False)
    if challenge.get("target_event"):
        embed.add_field(
            name="Auto Tracking",
            value=f"ADM tracked: `{challenge['target_event']}` events, target `{challenge.get('target_count', 0)}`.",
            inline=False
        )
    else:
        embed.add_field(
            name="Completion",
            value=f"Post proof for staff. Admins approve with `/pvecomplete quest_id:{pve_quest_code(challenge)}`.",
            inline=False
        )
    if challenge.get("quest_line"):
        embed.add_field(name="Quest Line", value=challenge["quest_line"], inline=True)
    embed.add_field(name="Survival Tip", value=challenge["tips"], inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - PVE Mission Board")

    await quest_channel.send(embed=style_embed(embed))

    themed_channel_key = pve_themed_channel_key(challenge)

    if themed_channel_key:
        themed_channel = bot.get_channel(channels.get(themed_channel_key))
        if themed_channel and themed_channel.id != quest_channel.id:
            themed_embed = discord.Embed.from_dict(embed.to_dict())
            await themed_channel.send(embed=style_embed(themed_embed))

    return True, challenge["title"]


async def post_pve_themed_challenge(guild_id, config, kind, *, manual=False, difficulty=None):
    guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if not guild:
        return False, "Guild not found"

    channel_key = pve_channel_for_kind(kind)
    if not channel_key:
        return False, f"No themed PVE channel for {kind}"

    difficulty = str(difficulty or random.choice(PVE_SLOT_DIFFICULTIES)).title()

    if not manual and pve_active_quest_for_channel(guild_id, channel_key, difficulty):
        return False, f"Active {difficulty} {kind} quest already exists"

    channels = config.setdefault("channels", {})
    if not channels.get(channel_key):
        await ensure_pve_channels(guild, config)

    challenge = generate_pve_challenge(kind, difficulty)
    challenge["channel_key"] = channel_key
    challenge["slot_difficulty"] = difficulty
    channel = bot.get_channel(channels.get(channel_key))
    if not channel:
        return False, "PVE channel missing"

    guild_challenges = pve_challenges.setdefault(str(guild_id), [])
    guild_challenges.append(challenge)
    pve_challenges[str(guild_id)] = guild_challenges[-50:]
    save_pve_challenges()

    embed = discord.Embed(
        title=f"{challenge['kind'].upper()} QUEST: {challenge['title']}",
        color=0x2ECC71
    )
    embed.add_field(name="Quest Slot", value=channel.mention, inline=True)
    embed.add_field(name="Quest ID", value=f"`{pve_quest_code(challenge)}`", inline=True)
    embed.add_field(name="Difficulty", value=challenge.get("difficulty", "Medium"), inline=True)
    embed.add_field(name="Reward", value=challenge["reward"], inline=False)
    embed.add_field(name="Objective", value=challenge["goal"], inline=False)
    embed.add_field(
        name="Completion",
        value=f"This is the {difficulty} slot. Staff approve it with `/pvecomplete quest_id:{pve_quest_code(challenge)}`, then I post a new {difficulty} quest here.",
        inline=False
    )
    embed.add_field(name="Survival Tip", value=challenge["tips"], inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Channel PVE Quest Feed")
    await channel.send(embed=style_embed(embed))
    return True, challenge["title"]


async def post_pve_daily_pack(guild_id, config):
    posted = []
    for kind in PVE_THEMED_QUEST_KINDS.values():
        for difficulty in PVE_SLOT_DIFFICULTIES:
            success, title = await post_pve_themed_challenge(guild_id, config, kind, difficulty=difficulty)
            if success:
                posted.append(title)
    return posted


async def ensure_pve_channel_quests(guild_id, config):
    posted = []
    for kind in PVE_THEMED_QUEST_KINDS.values():
        for difficulty in PVE_SLOT_DIFFICULTIES:
            success, title = await post_pve_themed_challenge(guild_id, config, kind, difficulty=difficulty)
            if success:
                posted.append(title)
    return posted


async def send_pve_completion_feed(guild_id, config, player_name, challenge, reward_status):
    channels = config.get("channels", {})
    quest_channel = bot.get_channel(channels.get("pve_quests"))
    themed_channel = bot.get_channel(channels.get(pve_themed_channel_key(challenge)))

    embed = discord.Embed(
        title="🏕️ PVE QUEST COMPLETE",
        description=f"**{player_name}** completed **{challenge.get('title')}**.",
        color=0xF1C40F
    )
    embed.add_field(name="Quest ID", value=f"`{pve_quest_code(challenge)}`", inline=True)
    embed.add_field(name="Type", value=challenge.get("kind", "PVE"), inline=True)
    embed.add_field(name="Difficulty", value=challenge.get("difficulty", "Medium"), inline=True)
    embed.add_field(name="Reward", value=reward_status, inline=False)
    if challenge.get("quest_line"):
        embed.add_field(name="Quest Line", value=challenge["quest_line"], inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - PVE Rewards")

    sent = False
    for channel in [quest_channel, themed_channel]:
        if channel and (not sent or channel.id != quest_channel.id):
            await channel.send(embed=style_embed(discord.Embed.from_dict(embed.to_dict())))
            sent = True


async def process_pve_progress_from_adm(guild_id, config, event_type, line):
    guild_quests = pve_challenges.get(str(guild_id), [])
    if not guild_quests:
        return

    player_name = extract_player_name(line)
    if not player_name or player_name == "Unknown":
        return

    changed = False

    for challenge in guild_quests:
        if challenge.get("status") != "active":
            continue

        target_event = challenge.get("target_event")
        if not target_event or target_event != event_type:
            continue

        target_count = int(challenge.get("target_count", 0) or 0)
        if target_count <= 0:
            continue

        progress = challenge.setdefault("progress", {})
        progress[player_name] = int(progress.get(player_name, 0)) + 1
        changed = True

        if progress[player_name] >= target_count:
            challenge["status"] = "completed"
            challenge["completed_by"] = player_name
            challenge["completed"] = str(datetime.now(UTC))
            paid, reward_status = award_pve_pennies(player_name, challenge)
            if not paid:
                reward_status = f"{challenge.get('reward_pennies', 0)} pennies pending. Survivor must link gamertag with `/linkgamer`."
            await send_pve_completion_feed(guild_id, config, player_name, challenge, reward_status)
            channel_key = challenge.get("channel_key") or pve_themed_channel_key(challenge)
            next_kind = PVE_THEMED_QUEST_KINDS.get(channel_key)
            if next_kind:
                await post_pve_themed_challenge(
                    guild_id,
                    config,
                    next_kind,
                    manual=True,
                    difficulty=challenge.get("slot_difficulty") or challenge.get("difficulty")
                )

    if changed:
        save_pve_challenges()


@tasks.loop(minutes=30)
async def pve_challenge_loop():
    for guild_id, config in active_guild_config_items():
        try:
            settings = pve_config(config)
            if not settings.get("enabled", True):
                continue

            posted = await ensure_pve_channel_quests(guild_id, config)
            if posted:
                settings["last_post_ts"] = datetime.now(UTC).timestamp()
                save_guild_configs()

        except Exception as error:
            print(f"PVE CHALLENGE LOOP ERROR {guild_id}: {error}")


@tasks.loop(minutes=60)
async def pve_pvp_advice_loop():
    now_ts = datetime.now(UTC).timestamp()

    for guild_id, config in active_guild_config_items():
        try:
            channels = config.setdefault("channels", {})

            pve_settings = pve_config(config)
            last_pve_help = float(pve_settings.get("last_help_ts", 0))
            if now_ts - last_pve_help >= 24 * 3600:
                guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
                if guild and not channels.get("pve_help"):
                    await ensure_pve_channels(guild, config)

                pve_help_channel = bot.get_channel(channels.get("pve_help"))
                if pve_help_channel:
                    title, body = random.choice(PVE_DAILY_HELP_LINES)
                    embed = discord.Embed(
                        title=f"PVE HELP: {title}",
                        description=body,
                        color=0x1ABC9C
                    )
                    embed.set_thumbnail(url=BOT_IMAGE)
                    embed.set_footer(text="Wandering Bot Alpha - Daily PVE Help")
                    await pve_help_channel.send(embed=style_embed(embed))
                    pve_settings["last_help_ts"] = now_ts
                    save_guild_configs()

            pvp_settings = config.setdefault("pvp_intel", {})
            last_pvp_tip = float(pvp_settings.get("last_tip_ts", 0))
            if now_ts - last_pvp_tip >= 24 * 3600:
                pvp_channel = bot.get_channel(channels.get("pvp_intel"))
                if pvp_channel:
                    embed = discord.Embed(
                        title="PVP FIELD NOTE",
                        description=random.choice(PVP_INTEL_LINES),
                        color=0x992D22
                    )
                    embed.set_thumbnail(url=BOT_IMAGE)
                    embed.set_footer(text="Wandering Bot Alpha - PvP Intelligence")
                    await pvp_channel.send(embed=style_embed(embed))
                    pvp_settings["last_tip_ts"] = now_ts
                    save_guild_configs()

        except Exception as error:
            print(f"PVE/PVP ADVICE LOOP ERROR {guild_id}: {error}")


@bot.tree.command(name="pvesetup", description="Admin: create or repair the PVE category and channels")
@app_commands.default_permissions(administrator=True)
async def pvesetup(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    channels = await ensure_pve_channels(interaction.guild, config, force=True)

    info_channel = channels.get("pve_info")
    if info_channel:
        embed = discord.Embed(
            title="PVE MISSIONS ONLINE",
            description="PVE hunting, collection, fishing, crafting, and expedition quest channels are ready.",
            color=0x2ECC71
        )
        embed.add_field(name="Quest Slots", value="Each themed channel keeps one Easy, one Medium, and one Hard quest active.", inline=False)
        embed.add_field(name="Auto Replacement", value="When staff approves a quest ID with `/pvecomplete`, I post the next random quest for that same difficulty.", inline=False)
        embed.add_field(name="Admin Controls", value="Use `/pvequests`, `/pvecomplete quest_id:PVE-123456`, and `/pveconfig` to manage the board.", inline=False)
        embed.set_thumbnail(url=BOT_IMAGE)
        await info_channel.send(embed=style_embed(embed))

    posted = await ensure_pve_channel_quests(guild_id, config)

    await interaction.response.send_message(
        f"PVE category and channels are ready. Posted `{len(posted)}` missing channel quests.",
        ephemeral=True
    )


@bot.tree.command(name="pveconfig", description="Admin: configure automatic PVE quest posting")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(enabled="Turn auto PVE quests on or off", interval_hours="Hours between themed quest packs, 6 to 168")
async def pveconfig_command(interaction: discord.Interaction, enabled: bool = True, interval_hours: int = 12):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    interval_hours = max(6, min(168, int(interval_hours)))
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    settings = pve_config(config)
    settings["enabled"] = enabled
    settings["interval_hours"] = interval_hours
    save_guild_configs()

    posted = await ensure_pve_channel_quests(guild_id, config) if enabled else []

    await interaction.response.send_message(
        f"PVE themed quest slots are {'on' if enabled else 'off'}. Posted `{len(posted)}` missing quests.",
        ephemeral=True
    )


@bot.tree.command(name="pvequestnow", description="Admin: post a random PVE quest now")
@app_commands.default_permissions(administrator=True)
async def pvequestnow(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    success, message = await post_pve_challenge(guild_id, config, manual=True)
    await interaction.followup.send(
        f"PVE quest posted: {message}" if success else f"PVE quest failed: {message}",
        ephemeral=True
    )


@bot.tree.command(name="pvequests", description="Show recent PVE quests")
async def pvequests(interaction: discord.Interaction):
    guild_quests = pve_challenges.get(str(interaction.guild.id), [])
    if not guild_quests:
        await interaction.response.send_message("No PVE quests have been posted yet.", ephemeral=True)
        return

    active = [quest for quest in guild_quests if quest.get("status") == "active"]
    completed = [quest for quest in guild_quests if quest.get("status") != "active"]
    display_quests = active + list(reversed(completed[-10:]))

    lines = [
        (
            f"`{pve_quest_code(quest)}` - **{quest.get('title')}** - {quest.get('kind')} - "
            f"{quest.get('status', 'active')} - {pve_progress_text(quest)} - "
            f"{quest.get('reward_pennies', 0)} pennies"
        )
        for quest in display_quests[:15]
    ]
    embed = discord.Embed(
        title="RECENT PVE QUESTS",
        description="\n".join(lines),
        color=0x2ECC71
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="pvecomplete", description="Admin: approve a PVE quest and pay the linked member")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(quest_id="Quest ID shown on the quest embed, for example PVE-123456", member="Discord member who completed it")
async def pvecomplete(interaction: discord.Interaction, quest_id: str, member: discord.Member):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    guild_quests = pve_challenges.get(guild_id, [])
    changed_codes = False
    for quest in guild_quests:
        if not quest.get("quest_code"):
            pve_quest_code(quest)
            changed_codes = True
    if changed_codes:
        save_pve_challenges()

    challenge = find_active_pve_quest_by_code(guild_id, quest_id)

    if not challenge:
        await interaction.response.send_message(
            "Active quest ID not found. Use `/pvequests` and copy the exact `PVE-123456` ID from the quest.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    user_id = str(member.id)
    linked = linked_players.get(user_id, {})
    player_name = linked.get("gamertag") or str(member)

    challenge["status"] = "completed"
    challenge["completed_by"] = player_name
    challenge["completed_discord_id"] = user_id
    challenge["completed"] = str(datetime.now(UTC))

    wallet = wallets.setdefault(user_id, {
        "name": str(member),
        "balance": 0,
        "daily_transactions": 0
    })
    reward = int(challenge.get("reward_pennies", 0))
    wallet["balance"] = wallet.get("balance", 0) + reward
    save_wallets()
    save_pve_challenges()

    await send_pve_completion_feed(
        guild_id,
        guild_configs.get(guild_id, {}),
        player_name,
        challenge,
        f"{reward} pennies paid to {member.mention}"
    )

    channel_key = challenge.get("channel_key") or pve_themed_channel_key(challenge)
    next_kind = PVE_THEMED_QUEST_KINDS.get(channel_key)
    if next_kind:
        await post_pve_themed_challenge(
            guild_id,
            guild_configs.get(guild_id, {}),
            next_kind,
            manual=True,
            difficulty=challenge.get("slot_difficulty") or challenge.get("difficulty")
        )

    await interaction.followup.send(
        f"Approved `{pve_quest_code(challenge)}` - `{challenge.get('title')}` for {member.mention} and paid {reward} pennies.",
        ephemeral=True
    )


@bot.tree.command(name="pveguide", description="Get AI-style guidance for a recent PVE quest")
@app_commands.describe(quest_number="Number from /pvequests")
async def pveguide(interaction: discord.Interaction, quest_number: int = 1):
    guild_quests = pve_challenges.get(str(interaction.guild.id), [])
    recent = list(reversed(guild_quests[-10:]))

    if not recent or quest_number < 1 or quest_number > len(recent):
        await interaction.response.send_message("No matching quest found. Use `/pvequests` first.", ephemeral=True)
        return

    quest = recent[quest_number - 1]
    tracked = (
        f"I can track this one from ADM logs when I see `{quest.get('target_event')}` events."
        if quest.get("target_event")
        else "This one needs screenshots, clips, or staff approval because logs cannot prove the fun bits."
    )
    line = (
        f"**{quest.get('title')}**\n"
        f"{quest.get('goal')}\n\n"
        f"{quest.get('tips')}\n\n"
        f"{tracked}\n"
        f"Reward: `{quest.get('reward_pennies', 0)}` pennies. Link your gamertag so I can pay you without making everyone do paperwork."
    )
    embed = discord.Embed(
        title="🧠 PVE QUEST GUIDE",
        description=line,
        color=0x1ABC9C
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="pverewards", description="Show how PVE rewards work")
async def pverewards(interaction: discord.Interaction):
    embed = discord.Embed(
        title="PVE REWARDS",
        description=(
            "Tracked quests pay automatically when your Discord is linked to your gamertag. "
            "Story, collection, exploration, and shenanigan quests can be approved by staff with `/pvecomplete`."
        ),
        color=0xF1C40F
    )
    embed.add_field(name="Easy", value="Around 350-700 pennies", inline=True)
    embed.add_field(name="Medium", value="Around 800-1300 pennies", inline=True)
    embed.add_field(name="Hard", value="Around 1500+ pennies", inline=True)
    embed.add_field(name="Quest Lines", value="Multi-step stories can lead to bigger admin rewards.", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="pveinfo", description="Get PVE survival advice")
@app_commands.describe(topic="loot, hunting, medical, building, vehicles, fishing, crafting, expeditions, collections, or zombies")
async def pveinfo(interaction: discord.Interaction, topic: str = "loot"):
    key = topic.lower().strip()
    advice = PVE_INFO_TOPICS.get(key)
    if not advice:
        advice = "Pick one of: loot, hunting, medical, building, vehicles, fishing, crafting, expeditions, collections, zombies."

    embed = discord.Embed(
        title=f"PVE INFO: {key.upper()}",
        description=advice,
        color=0x1ABC9C
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)

# =========================================================
# LIVE SERVER STATUS
# =========================================================

@bot.command()
async def serverstatus(ctx):

    total_guilds = len(guild_configs)

    total_players = sum(len(players) for players in online_players.values())

    embed = discord.Embed(
        title="📡 WANDERING BOT STATUS",
        color=0x3498DB
    )

    embed.add_field(
        name="Connected Servers",
        value=str(total_guilds),
        inline=True
    )

    embed.add_field(
        name="Tracked Players",
        value=str(total_players),
        inline=True
    )

    embed.add_field(
        name="ADM Parser",
        value="🟢 ONLINE",
        inline=False
    )

    embed.add_field(
        name="API Status",
        value="🟢 CONNECTED",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# DISCORD ↔ GAMERTAG LINKING
# =========================================================

@bot.command()
async def linkgamer(ctx, *, gamertag: str):

    success, result = await link_verified_gamertag_for_member(ctx.guild, ctx.author, gamertag)
    if not success:
        await ctx.send(result)
        return
    gamertag = result
    await ctx.send(embed=style_embed(build_linkgamer_confirmation_embed(ctx.author, gamertag)))
    return

    embed = discord.Embed(
        title="VERIFIED GAMERTAG LINKED",
        description=(
            f"Your Discord account is now linked to ADM verified survivor: `{gamertag}`"
        ),
        color=0x2ECC71
    )

    embed.add_field(
        name="🎮 Linked Survivor",
        value=gamertag,
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Identity System"
    )

    await ctx.send(embed=style_embed(embed))


@bot.tree.command(
    name="linkgamer",
    description="Link your Discord account to your Xbox gamertag"
)
@app_commands.describe(gamertag="Your Xbox gamertag")
async def slash_linkgamer(interaction: discord.Interaction, gamertag: str):
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(
        "Checking saved ADM stats first. If needed, I will scan recent ADM history for that Xbox gamertag.",
        ephemeral=True
    )

    success, result = await link_verified_gamertag_for_member(interaction.guild, interaction.user, gamertag)
    if not success:
        await interaction.followup.send(result, ephemeral=True)
        return
    gamertag = result
    confirmation = style_embed(
        build_linkgamer_confirmation_embed(interaction.user, gamertag)
    )

    if interaction.channel:
        await interaction.channel.send(embed=confirmation)
        await interaction.followup.send(
            f"Linked `{gamertag}` and posted the confirmation in this channel.",
            ephemeral=True
        )
    else:
        await interaction.followup.send(embed=confirmation, ephemeral=True)
    return

    embed = discord.Embed(
        title="🔗 GAMERTAG LINKED",
        description=f"Linked to: `{gamertag}`",
        color=0x2ECC71
    )
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


async def force_link_gamertag_for_member(guild, admin_member, target_member, gamertag):
    guild_id = str(guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": guild.name, "channels": {}})
    verified_name = str(gamertag).strip()
    if not verified_name:
        return False, "Gamertag cannot be empty."

    wanted = normalize_discord_name(verified_name)
    for linked_user_id, data in list(linked_players.items()):
        if str(linked_user_id) != str(target_member.id) and normalize_discord_name(data.get("gamertag", "")) == wanted:
            linked_players.pop(linked_user_id, None)

    linked_players[str(target_member.id)] = {
        "discord_name": str(target_member),
        "discord_id": str(target_member.id),
        "guild_id": guild_id,
        "gamertag": verified_name,
        "verified_by": f"FORCED_BY_ADMIN:{admin_member.id}",
        "linked_at": str(datetime.now(UTC))
    }
    save_linked_players()

    stats = ensure_player_stats_record(guild_id, verified_name)
    if stats:
        stats["last_adm_seen"] = stats.get("last_adm_seen") or str(datetime.now(UTC))
        save_player_stats()

    await announce_verified_gamer_link(guild, config, target_member, verified_name)
    return True, verified_name


@bot.tree.command(name="forcelinkgamer", description="Admin: force link a Discord member to an Xbox gamertag")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(member="Discord member to link", gamertag="Xbox gamertag to link")
async def forcelinkgamer(interaction: discord.Interaction, member: discord.Member, gamertag: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    success, result = await force_link_gamertag_for_member(
        interaction.guild,
        interaction.user,
        member,
        gamertag
    )
    if not success:
        await interaction.response.send_message(result, ephemeral=True)
        return

    embed = build_linkgamer_confirmation_embed(member, result)
    embed.title = "ADMIN VERIFIED GAMERTAG LINKED"
    embed.add_field(name="Linked By", value=interaction.user.mention, inline=False)
    await interaction.response.send_message("Forced link saved. Public confirmation posted below.", ephemeral=True)
    await interaction.channel.send(embed=style_embed(embed))


@bot.tree.command(name="refreshadmplayers", description="Admin: rescan recent ADM logs for linkable player names")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(hours="How far back to scan, max 336", max_logs="Maximum ADM files to scan, max 80")
async def refreshadmplayers(interaction: discord.Interaction, hours: int = 168, max_logs: int = 40):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id)
    if not config:
        await interaction.followup.send("This server is not setup yet.", ephemeral=True)
        return

    hours = max(1, min(336, int(hours or 168)))
    max_logs = max(1, min(80, int(max_logs or 40)))
    learned, scanned = await asyncio.to_thread(
        learn_recent_adm_players_for_linking,
        guild_id,
        config,
        hours,
        max_logs
    )
    await interaction.followup.send(
        f"ADM player refresh complete. Scanned `{scanned}` log(s), learned `{learned}` player name entry/entries. Now try `/admplayers search:yourname` or `/linkgamer` again.",
        ephemeral=True
    )


@bot.tree.command(name="admplayers", description="Admin: show ADM player names the bot has learned")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(search="Optional text to filter gamertags")
async def admplayers(interaction: discord.Interaction, search: str = ""):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    wanted = normalize_discord_name(search)
    rows = [
        (player, stats)
        for player, stats in player_stats.items()
        if str(stats.get("guild_id", "")) == guild_id
        and (not wanted or wanted in normalize_discord_name(player))
    ]
    rows.sort(
        key=lambda row: parse_saved_datetime(row[1].get("last_adm_seen") or row[1].get("last_seen")) or datetime.min.replace(tzinfo=UTC),
        reverse=True
    )

    if not rows:
        await interaction.response.send_message(
            "No ADM player names found for this server yet. Run `/restartadm force` after someone joins, then try again.",
            ephemeral=True
        )
        return

    lines = ["#  Gamertag              Last ADM Seen"]
    for index, (player, stats) in enumerate(rows[:25], start=1):
        seen = parse_saved_datetime(stats.get("last_adm_seen") or stats.get("last_seen"))
        seen_text = seen.strftime("%Y-%m-%d %H:%M") if seen else "unknown"
        lines.append(f"{index:<2} {trim_table_text(player, 21)} {seen_text}")

    embed = discord.Embed(
        title="ADM LEARNED PLAYERS",
        description="These are the Xbox/ADM names the bot can currently match for `/linkgamer`.\n```text\n" + "\n".join(lines) + "\n```",
        color=0x3498DB
    )
    embed.add_field(name="Matches", value=str(len(rows)), inline=True)
    embed.add_field(name="Filter", value=search or "None", inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.command()
async def mylink(ctx):

    user_id = str(ctx.author.id)

    if user_id not in linked_players:

        await ctx.send(
            "❌ No linked gamertag found. Use `/linkgamer gamertag:YourName`"
        )

        return

    data = linked_players[user_id]

    embed = discord.Embed(
        title="🎮 LINKED SURVIVOR PROFILE",
        color=0x3498DB
    )

    embed.add_field(
        name="Discord",
        value=str(ctx.author),
        inline=False
    )

    embed.add_field(
        name="Gamertag",
        value=data['gamertag'],
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def unlinkgamer(ctx, member: discord.Member):

    user_id = str(member.id)

    if user_id not in linked_players:

        await ctx.send("No linked gamertag found.")
        return

    del linked_players[user_id]

    save_linked_players()

    await ctx.send(
        f"🗑️ Removed linked gamertag for {member.mention}"
    )

# =========================================================
# PLAYER LOOKUP
# =========================================================

@bot.command()
async def playerstats(ctx, *, player_name: str):

    if player_name not in player_stats:

        await ctx.send(
            "Player not found."
        )

        return

    stats = player_stats[player_name]

    embed = discord.Embed(
        title=f"📊 PLAYER STATS - {player_name}",
        color=0x1ABC9C
    )

    embed.add_field(
        name="Kills",
        value=str(stats.get("kills", 0)),
        inline=True
    )

    embed.add_field(
        name="Deaths",
        value=str(stats.get("deaths", 0)),
        inline=True
    )

    embed.add_field(
        name="Raids",
        value=str(stats.get("raids", 0)),
        inline=True
    )

    embed.add_field(
        name="Builds",
        value=str(stats.get("builds", 0)),
        inline=True
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# PERSISTENT MULTI-GUILD STORAGE
# =========================================================

# Guild setups are permanently stored in DATA_ROOT:
# guild_configs.json
# guild_data/guilds/<guild_id>.json
#
# This means if the bot restarts, redeploys,
# crashes, or updates, every server remains linked
# automatically without requiring /setup again.
#
# Server owners only need to run /setup once.
#
# The only time setup is needed again is if:
# - guild_configs.json is deleted
# - the bot is kicked from a server
# - the hosting storage is wiped manually
#
# =========================================================
# AUTO START TASKS
# =========================================================

async def start_background_tasks():

    try:

        if not adm_loop.is_running():
            adm_loop.start()

        if not online_dashboard_loop.is_running():
            online_dashboard_loop.start()

        if not leaderboard_loop.is_running():
            leaderboard_loop.start()

        if not heatmap_loop.is_running():
            heatmap_loop.start()

        if not scheduled_restart_loop.is_running():
            scheduled_restart_loop.start()

        if not restart_delivery_processor.is_running():
            restart_delivery_processor.start()

        if not pve_challenge_loop.is_running():
            pve_challenge_loop.start()

        if not pve_pvp_advice_loop.is_running():
            pve_pvp_advice_loop.start()

        if not custom_feed_loop.is_running():
            custom_feed_loop.start()

        if not wage_loop.is_running():
            wage_loop.start()

        if not showcase_autonomous_loop.is_running():
            showcase_autonomous_loop.start()

        if not temp_ban_expiry_loop.is_running():
            temp_ban_expiry_loop.start()

        if not recap_loop.is_running():
            recap_loop.start()

        if not mega_leaderboard_loop.is_running():
            mega_leaderboard_loop.start()

    except RuntimeError:
        pass

# =========================================================
# LIVE ONLINE DASHBOARD
# =========================================================


async def purge_self_dashboard_messages(channel, limit=10):
    """Delete recent bot-authored messages in a dashboard-style channel.

    Used at the top of dashboard refresh loops (online, heatmap, pve_heatmap,
    leaderboards, restart_alerts) so orphan messages from previous bot
    sessions or stale in-memory `last_*_message_ids` state get cleaned up
    before a new dashboard message is posted.

    Idempotent — safe to call before every post. Tries the fast bulk-purge
    API first, falls back to manual per-message deletion if the bot lacks
    the Manage Messages permission.
    """
    if not channel:
        return
    try:
        # Fast path: requires Manage Messages permission. Bulk-deletes up to
        # `limit` of the most recent bot messages in one API call.
        await channel.purge(limit=limit, check=lambda m: m.author == bot.user)
        return
    except Exception:
        pass
    # Fallback: iterate history and delete one at a time. Works without
    # Manage Messages, but only for messages younger than 14 days.
    try:
        async for old_msg in channel.history(limit=limit):
            if old_msg.author == bot.user:
                try:
                    await old_msg.delete()
                except Exception:
                    pass
    except Exception:
        pass


@tasks.loop(minutes=ONLINE_UPDATE_MINUTES)
async def online_dashboard_loop():

    for guild_id, config in active_guild_config_items():

        try:

            channels = config.get("channels", {})

            online_channel = bot.get_channel(
                channels.get("online")
            )

            if not online_channel:
                continue

            ensure_guild_runtime(guild_id)

            guild_online = online_players[guild_id]

            if guild_online:

                player_text = "\n".join([
                    f"🟢 {player}"
                    for player in sorted(guild_online)
                ])

            else:

                player_text = "No survivors online."

            embed = discord.Embed(
                title=f"✅🎮 LIVE SURVIVORS ONLINE 🎮✅ ({len(guild_online)})",
                description=player_text,
                color=0x2ECC71
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha - Auto Refresh Every 30 Minutes"
            )

            embed.timestamp = datetime.now(UTC)

            # Defensively purge any stale bot messages in this channel
            # (orphans from previous sessions where the in-memory message
            # ID was lost on bot restart). Then post the fresh dashboard.
            await purge_self_dashboard_messages(online_channel, limit=10)

            sent_message = await online_channel.send(embed=embed)
            last_online_message_ids[guild_id] = sent_message.id

        except Exception as error:
            print(error)

# =========================================================
# LIVE PVP HEATMAP DASHBOARD
# =========================================================

@tasks.loop(minutes=HEATMAP_UPDATE_MINUTES)
async def heatmap_loop():

    for guild_id, config in active_guild_config_items():

        try:

            channels = config.get("channels", {})

            heatmap_channel = bot.get_channel(
                channels.get("heatmap")
            )

            if not heatmap_channel:
                continue

            ensure_guild_runtime(guild_id)

            heatmap_mode = guild_heatmap_mode(guild_id)
            mode_counts = heat_counts_for_mode(guild_id, heatmap_mode)

            hottest_zones = sorted(
                mode_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            lines = []

            for zone, count in hottest_zones:
                lines.append(
                    f"🔥 {zone} — {count} {heatmap_mode} events"
                )

            embed = discord.Embed(
                title=f"🔥 LIVE {heatmap_mode.upper()} HEATMAP",
                description=(
                    "\n".join(lines)
                    if lines else f"No {heatmap_mode} activity detected yet."
                ),
                color=0x9B59B6
            )

            embed.add_field(
                name="📡 Status",
                value=f"Tracking `{heatmap_mode}` activity across the server.",
                inline=False
            )

            heatmap_path = generate_guild_heatmap_image(guild_id, heatmap_mode)
            file = discord.File(heatmap_path, filename="heatmap.png")
            embed.set_image(url="attachment://heatmap.png")
            embed.add_field(
                name="Map Image",
                value=heatmap_render_status(guild_id, heatmap_mode)[:1000],
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha - Heatmap Refresh Every 1 Hour"
            )

            embed.timestamp = datetime.now(UTC)

            # Purge any stale bot heatmaps (including orphans from prior
            # bot sessions) before posting the fresh one.
            await purge_self_dashboard_messages(heatmap_channel, limit=10)

            sent_message = await heatmap_channel.send(embed=embed, file=file)
            last_heatmap_message_ids[guild_id] = sent_message.id

            pve_heatmap_channel = bot.get_channel(
                channels.get("pve_heatmap")
            )

            if pve_heatmap_channel:
                pve_counts = heat_counts_for_mode(guild_id, "pve")
                pve_lines = [
                    f"🦌 {zone} — {count} PVE events"
                    for zone, count in sorted(pve_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                ]
                pve_embed = discord.Embed(
                    title="🦌 LIVE PVE HUNTING HEATMAP",
                    description="\n".join(pve_lines) if pve_lines else "No PVE hunting activity detected yet.",
                    color=0x2ECC71
                )
                pve_embed.add_field(
                    name="Status",
                    value="Tracking animal and PVE hunting activity across the server.",
                    inline=False
                )
                pve_heatmap_path = generate_guild_heatmap_image(guild_id, "pve")
                pve_file = discord.File(pve_heatmap_path, filename="pve_heatmap.png")
                pve_embed.set_image(url="attachment://pve_heatmap.png")
                pve_embed.add_field(
                    name="Map Image",
                    value=heatmap_render_status(guild_id, "pve")[:1000],
                    inline=False
                )
                pve_embed.set_thumbnail(url=BOT_IMAGE)
                pve_embed.set_footer(text="Wandering Bot Alpha - PVE Heatmap Refresh Every 1 Hour")

                # Purge stale PVE heatmaps before posting the fresh one.
                await purge_self_dashboard_messages(pve_heatmap_channel, limit=10)

                pve_sent_message = await pve_heatmap_channel.send(embed=pve_embed, file=pve_file)
                last_pve_heatmap_message_ids[guild_id] = pve_sent_message.id
                try:
                    os.remove(pve_heatmap_path)
                except Exception:
                    pass

            try:
                os.remove(heatmap_path)
            except Exception:
                pass

        except Exception as error:
            print(error)

# =========================================================
# LIVE LEADERBOARD DASHBOARD
# =========================================================

@tasks.loop(minutes=LEADERBOARD_UPDATE_MINUTES)
async def leaderboard_loop():

    for guild_id, config in active_guild_config_items():

        try:

            channels = config.get("channels", {})

            leaderboard_channel = bot.get_channel(
                channels.get("leaderboards")
            )

            if not leaderboard_channel:
                continue

            guild_only = [
                (player, stats)
                for player, stats in player_stats.items()
                if str(stats.get("guild_id", "")) == guild_id
            ]

            def board_lines(stat_key, label, limit=5, formatter=None, source_rows=None):
                rows = source_rows if source_rows is not None else guild_only
                sorted_rows = sorted(
                    rows,
                    key=lambda row: row[1].get(stat_key, 0),
                    reverse=True
                )
                lines = [f"#  Survivor              {label}"]
                medals = ["🥇", "🥈", "🥉", "4.", "5."]
                for idx, (player, stats) in enumerate(sorted_rows[:limit], start=1):
                    value = stats.get(stat_key, 0)
                    if formatter:
                        value = formatter(value)
                    rank = medals[idx - 1] if idx <= len(medals) else f"{idx}."
                    lines.append(f"{idx:<2} {trim_table_text(player, 21)} {str(value):>8}")
                if len(lines) == 1:
                    return "No data yet. ADM activity will fill this in."
                return "```text\n" + "\n".join(lines) + "\n```"

            global_rows = list(player_stats.items())
            global_longshots = sorted(
                longshot_records.items(),
                key=lambda row: row[1].get("distance", 0),
                reverse=True
            )[:5]
            global_longshot_lines = ["#  Shooter               Dist"]
            medals = ["🥇", "🥈", "🥉", "4.", "5."]
            for idx, (record_guild_id, record) in enumerate(global_longshots, start=1):
                rank = medals[idx - 1] if idx <= len(medals) else f"{idx}."
                global_longshot_lines.append(
                    f"{idx:<2} {trim_table_text(record.get('killer', 'Unknown'), 21)} {str(record.get('distance', 0)) + 'm':>6}"
                )

            embed = discord.Embed(
                title="🏆 DAYZ SERVER COMMAND BOARD",
                description=(
                    "Server rankings, global bragging rights, and survival stats refreshed automatically."
                ),
                color=0xF1C40F
            )
            embed.add_field(
                name="☠️ Server Kills",
                value=board_lines("kills", "Kills"),
                inline=True
            )
            embed.add_field(
                name="💀 Server Deaths",
                value=board_lines("deaths", "Deaths"),
                inline=True
            )
            embed.add_field(
                name="⏱️ Server Time",
                value=board_lines("time_online_seconds", "Time", formatter=format_duration),
                inline=True
            )
            embed.add_field(
                name="🔨 Builders",
                value=board_lines("builds", "Builds"),
                inline=True
            )
            embed.add_field(
                name="📦 Placements",
                value=board_lines("placements", "Placed"),
                inline=True
            )
            embed.add_field(
                name="🏹 PVE Hunting",
                value=board_lines("animals_hunted", "Hunts"),
                inline=True
            )
            embed.add_field(
                name="🌍 Global Kills",
                value=board_lines("kills", "Kills", source_rows=global_rows),
                inline=True
            )
            embed.add_field(
                name="🌍 Global Time",
                value=board_lines("time_online_seconds", "Time", formatter=format_duration, source_rows=global_rows),
                inline=True
            )
            embed.add_field(
                name="🎯 Global Longshots",
                value=(
                    "```text\n" + "\n".join(global_longshot_lines) + "\n```"
                    if len(global_longshot_lines) > 1 else "No longshot data yet."
                ),
                inline=True
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha - Leaderboards Refresh Every 1 Hour"
            )

            embed.timestamp = datetime.now(UTC)

            # Purge stale leaderboards (including orphans from previous
            # bot sessions) before posting the fresh one.
            await purge_self_dashboard_messages(leaderboard_channel, limit=10)

            sent_message = await leaderboard_channel.send(embed=embed)
            last_leaderboard_message_ids[guild_id] = [sent_message.id]

        except Exception as error:
            print(error)

# READY BLOCK MOVED TO BOTTOM OF FILE

# =========================================================
# ECONOMY SYSTEM FOUNDATION
# =========================================================

SHOP_FILE = data_path("shop.json")
WALLETS_FILE = data_path("wallets.json")
DELIVERY_QUEUE_FILE = data_path("delivery_queue.json")
TYPES_XML_CANDIDATES = [
    data_path("types.xml"),
    os.path.join(GUILD_DATA_FOLDER, "types.xml"),
    os.path.join(os.getcwd(), "types.xml"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "types.xml"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "types.xml.xml"),
    os.path.join(os.path.expanduser("~"), "Downloads", "types.xml"),
]

shop_items = {}
wallets = {}
delivery_queue = []
vehicle_rentals_queue = []


def find_types_xml(source_path=None):
    candidates = []

    if source_path:
        source_path = str(source_path).strip().strip('"')
        candidates.append(source_path)

        if not source_path.lower().endswith(".xml"):
            candidates.append(f"{source_path}.xml")

        if os.path.isdir(source_path):
            candidates.append(os.path.join(source_path, "types.xml"))

    candidates.extend(TYPES_XML_CANDIDATES)

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    search_roots = [
        DATA_ROOT,
        GUILD_DATA_FOLDER,
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
    ]

    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue

        try:
            for current_root, _, files in os.walk(root):
                for file_name in files:
                    if file_name.lower() == "types.xml":
                        return os.path.join(current_root, file_name)
        except Exception:
            continue

    return None


def guess_shop_category(item_name, xml_category=None, usage=None):
    if xml_category:
        return xml_category.title()

    lower = item_name.lower()

    if any(word in lower for word in ["car", "truck", "sedan", "hatchback", "offroad", "ada", "olga", "sarka", "gunter"]):
        return "Vehicles"

    if any(word in lower for word in ["rifle", "ak", "m4", "m16", "mosin", "shotgun", "pistol", "magnum", "ammo", "mag_"]):
        return "Weapons"

    if any(word in lower for word in ["jacket", "pants", "boots", "gloves", "helmet", "vest", "backpack", "cap"]):
        return "Clothing"

    if any(word in lower for word in ["bandage", "saline", "morphine", "epinephrine", "vitamin", "charcoal", "tetracycline"]):
        return "Medical"

    if any(word in lower for word in ["apple", "beans", "food", "meat", "water", "soda", "zucchini", "seeds"]):
        return "Food"

    if usage:
        return usage.title()

    return "General"


def load_shop_items_from_types_xml(source_path=None, default_price=100, overwrite=False):
    types_path = find_types_xml(source_path)

    if not types_path:
        return 0, 0, None

    tree = ET.parse(types_path)
    root = tree.getroot()
    added = 0
    updated = 0

    for type_node in root.findall(".//type"):
        item_name = type_node.get("name")

        if not item_name:
            continue

        category_node = type_node.find("category")
        usage_node = type_node.find("usage")
        cost_node = type_node.find("cost")

        xml_category = category_node.get("name") if category_node is not None else None
        usage = usage_node.get("name") if usage_node is not None else None

        try:
            price = int(cost_node.text.strip()) if cost_node is not None and cost_node.text else default_price
        except Exception:
            price = default_price

        if price <= 0:
            price = default_price

        item_data = {
            "price": price,
            "category": guess_shop_category(item_name, xml_category, usage),
            "enabled": True
        }

        if item_name in shop_items:
            if overwrite:
                shop_items[item_name].update(item_data)
                updated += 1
            continue

        shop_items[item_name] = item_data
        added += 1

    if added or updated:
        save_shop()

    return added, updated, types_path


def load_shop():
    global shop_items
    shop_items = load_json(SHOP_FILE)

    if not shop_items:
        load_shop_items_from_types_xml()


def save_shop():
    save_json(SHOP_FILE, shop_items)


def load_wallets():
    global wallets
    wallets = load_json(WALLETS_FILE)


def save_wallets():
    save_json(WALLETS_FILE, wallets)


def load_delivery_queue():
    global delivery_queue, vehicle_rentals_queue

    if os.path.exists(DELIVERY_QUEUE_FILE):

        with open(DELIVERY_QUEUE_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        if isinstance(loaded, dict):
            delivery_queue = loaded.get("items", [])
            vehicle_rentals_queue = loaded.get("vehicles", [])
        elif isinstance(loaded, list):
            delivery_queue = loaded
            vehicle_rentals_queue = []


def save_delivery_queue():

    save_json(
        DELIVERY_QUEUE_FILE,
        {
            "items": delivery_queue,
            "vehicles": vehicle_rentals_queue
        }
    )


DEFAULT_DAILY_TRANSACTION_LIMIT = 5
VEHICLE_RENTAL_FILE = "vehicle_rentals.json"
DEFAULT_VEHICLE_RESET_CLASSES = [
    "OffroadHatchback",
    "OffroadHatchback_Blue",
    "OffroadHatchback_White",
    "CivilianSedan",
    "CivilianSedan_Black",
    "CivilianSedan_Wine",
    "CivilianSedan_White",
    "Hatchback_02",
    "Hatchback_02_Black",
    "Hatchback_02_Blue",
    "Sedan_02",
    "Sedan_02_Grey",
    "Sedan_02_Red",
    "Truck_01_Covered",
    "Truck_01_Covered_Blue",
    "Truck_01_Covered_Orange",
    "Truck_01_Covered_Camo",
    "Truck_01_Covered_Yellow",
    "Truck_01_Open",
    "Truck_01_Open_Blue",
    "Truck_01_Open_Orange",
    "Truck_01_Open_Camo",
    "Truck_01_Open_Yellow",
    "M1025",
    "M1025_Black",
]

SCENARIO_LOCATION_PRESETS = {
    "nwaf": {"name": "NWAF", "x": 4500, "y": 0, "z": 10300},
    "tisy": {"name": "Tisy Military Base", "x": 1680, "y": 0, "z": 14100},
    "vmc": {"name": "Vybor Military Base", "x": 4550, "y": 0, "z": 8300},
    "balota": {"name": "Balota Airfield", "x": 4700, "y": 0, "z": 2500},
    "prison": {"name": "Prison Island", "x": 2700, "y": 0, "z": 1300},
    "kamensk": {"name": "Kamensk Military", "x": 7900, "y": 0, "z": 14600},
    "zeleno": {"name": "Zelenogorsk", "x": 2750, "y": 0, "z": 5300},
    "chernogorsk": {"name": "Chernogorsk", "x": 6600, "y": 0, "z": 2500},
    "elektro": {"name": "Elektrozavodsk", "x": 10400, "y": 0, "z": 2300},
    "berezino": {"name": "Berezino", "x": 12200, "y": 0, "z": 9500},
    "severograd": {"name": "Severograd", "x": 8000, "y": 0, "z": 12600},
    "custom": {"name": "Custom Coordinates", "x": None, "y": None, "z": None},
}

SCENARIO_LOCATION_PRESETS_BY_MAP = {
    "chernarus": SCENARIO_LOCATION_PRESETS,
    "livonia": {
        "brena": {"name": "Brena", "x": 6660, "y": 0, "z": 11160},
        "nadbor": {"name": "Nadbor", "x": 6050, "y": 0, "z": 3920},
        "lembork": {"name": "Lembork", "x": 8500, "y": 0, "z": 8700},
        "lukow": {"name": "Lukow", "x": 3560, "y": 0, "z": 11880},
        "topolin": {"name": "Topolin", "x": 1150, "y": 0, "z": 7300},
        "radunin": {"name": "Radunin", "x": 9130, "y": 0, "z": 3500},
        "swarog": {"name": "Swarog", "x": 4800, "y": 0, "z": 2270},
        "custom": {"name": "Custom Coordinates", "x": None, "y": None, "z": None},
    },
}

SCENARIO_SPAWN_PRESETS = {
    "civilian_zombie": {"label": "Civilian infected", "class": "ZmbM_CitizenASkinny_Brown", "event_type": "zombie_horde"},
    "military_zombie": {"label": "Military infected", "class": "ZmbM_SoldierNormal", "event_type": "zombie_horde"},
    "heavy_military_zombie": {"label": "Heavy military infected", "class": "ZmbM_usSoldier_Heavy_Woodland", "event_type": "zombie_horde"},
    "police_zombie": {"label": "Police infected", "class": "ZmbM_PolicemanFat", "event_type": "zombie_horde"},
    "medical_zombie": {"label": "Medical infected", "class": "ZmbM_DoctorFat", "event_type": "zombie_horde"},
    "firefighter_zombie": {"label": "Firefighter infected", "class": "ZmbM_FirefighterNormal", "event_type": "zombie_horde"},
    "wolf": {"label": "Wolves", "class": "Animal_CanisLupus_Grey", "event_type": "animal_pack"},
    "bear": {"label": "Bears", "class": "Animal_UrsusArctos", "event_type": "animal_pack"},
    "deer": {"label": "Deer", "class": "Animal_CervusElaphus", "event_type": "animal_pack"},
    "boar": {"label": "Boar", "class": "Animal_SusScrofa", "event_type": "animal_pack"},
    "military_crate": {"label": "Military loot crate", "class": "WoodenCrate", "event_type": "loot_crate"},
    "medical_crate": {"label": "Medical loot crate", "class": "WoodenCrate", "event_type": "loot_crate"},
    "survival_crate": {"label": "Survival loot crate", "class": "WoodenCrate", "event_type": "loot_crate"},
    "building_crate": {"label": "Building loot crate", "class": "WoodenCrate", "event_type": "loot_crate"},
    "custom": {"label": "Custom classname", "class": "", "event_type": "custom_spawn"},
}

SCENARIO_LOOT_PRESETS = {
    "none": [],
    "military": ["M4A1", "Mag_STANAG_30Rnd", "Ammo_556x45", "BandageDressing", "Canteen"],
    "military_high": [
        "M4A1", "AKM", "SVD", "PlateCarrierVest", "BallisticHelmet_Green",
        "Mag_STANAG_30Rnd", "Mag_AKM_30Rnd", "Ammo_556x45", "Ammo_762x39", "Ammo_762x54",
        "Grenade_ChemGas", "NVGoggles", "BandageDressing"
    ],
    "medical": ["BandageDressing", "TetracyclineAntibiotics", "CharcoalTablets", "SalineBagIV", "Morphine"],
    "survival": ["Canteen", "TacticalBaconCan", "HuntingKnife", "Matchbox", "Rope"],
    "building": ["NailBox", "Hammer", "Handsaw", "Hatchet", "MetalWire"],
    "food": ["BakedBeansCan", "PeachesCan", "SpaghettiCan", "SodaCan_Cola", "WaterBottle"],
}

SCENARIO_VEHICLE_PRESETS = {
    "ada": {"label": "Ada 4x4", "class": "OffroadHatchback"},
    "gunter": {"label": "Gunter 2", "class": "Hatchback_02"},
    "sarka": {"label": "Sarka 120", "class": "CivilianSedan"},
    "olga": {"label": "Olga 24", "class": "Sedan_02"},
    "m3s": {"label": "M3S covered truck", "class": "Truck_01_Covered"},
    "custom": {"label": "Custom vehicle classname", "class": ""},
}

SCENARIO_VEHICLE_CONDITIONS = {
    "full": "Full fuel, fluids, and common parts",
    "no_parts": "Body only, no parts added",
    "random_parts": "Random chance of common parts",
}

SCENARIO_AIRDROP_MARKER_CLASS = "Land_Wreck_Caravan_MGreen"

DAYZ_REFERENCE_MAP_FOLDERS = {
    "chernarus": "dayzOffline.chernarusplus",
    "livonia": "dayzOffline.enoch",
    "sakhal": "dayzOffline.sakhal",
}
dayz_reference_cache = {}

CONSOLE_CE_EVENT_PREFIX = "WanderingBot_"


def dayz_reference_path(map_key, *parts):
    folder = DAYZ_REFERENCE_MAP_FOLDERS.get(map_key)
    if not folder:
        return None
    return os.path.join(DAYZ_REFERENCE_FOLDER, folder, *parts)


def load_dayz_reference_text(map_key, *parts):
    path = dayz_reference_path(map_key, *parts)
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as source:
            return source.read()
    return ""


def load_dayz_reference(map_key):
    map_key = "livonia" if map_key == "livonia" else "chernarus"
    if map_key in dayz_reference_cache:
        return dayz_reference_cache[map_key]

    reference = {
        "map_key": map_key,
        "available": False,
        "types": set(),
        "zombies": [],
        "animals": [],
        "containers": [],
    }

    types_path = dayz_reference_path(map_key, "db", "types.xml")
    if not types_path or not os.path.exists(types_path):
        dayz_reference_cache[map_key] = reference
        return reference

    try:
        root = ET.parse(types_path).getroot()
        for type_node in root.findall(".//type"):
            class_name = str(type_node.get("name") or "").strip()
            if not class_name:
                continue

            lower = class_name.lower()
            reference["types"].add(class_name)
            if class_name.startswith(("ZmbM_", "ZmbF_")):
                reference["zombies"].append(class_name)
            elif class_name.startswith("Animal_"):
                reference["animals"].append(class_name)
            elif any(term in lower for term in ["barrel", "chest", "crate", "firstaidkit"]):
                reference["containers"].append(class_name)

        reference["zombies"].sort()
        reference["animals"].sort()
        reference["containers"].sort()
        reference["available"] = True
    except Exception as error:
        print(f"DAYZ REFERENCE LOAD ERROR {map_key}: {error}")

    dayz_reference_cache[map_key] = reference
    return reference


def scenario_location_presets_for_map(map_key):
    return SCENARIO_LOCATION_PRESETS_BY_MAP.get(map_key, SCENARIO_LOCATION_PRESETS)


def infer_scenario_type_from_class(class_name):
    lower = normalize_discord_name(class_name)
    if lower.startswith("zmb") or "zmb" in lower:
        return "zombie_horde"
    if lower.startswith("animal") or any(term in lower for term in ["canislupus", "ursus", "cervus", "sus", "gallus", "bos", "capra"]):
        return "animal_pack"
    if any(term in lower for term in ["crate", "barrel", "chest", "firstaidkit"]):
        return "loot_crate"
    return "custom_spawn"


def scenario_spawn_preset_options(map_key, event_type=None):
    reference = load_dayz_reference(map_key)
    options = []

    for key, preset in SCENARIO_SPAWN_PRESETS.items():
        if key == "custom":
            continue
        preset_type = preset.get("event_type")
        if event_type and not (preset_type == event_type or (event_type == "airdrop" and preset_type == "loot_crate")):
            continue
        options.append((preset.get("label", key), key))

    if reference.get("available"):
        if event_type in (None, "zombie_horde", "custom_spawn"):
            for class_name in reference["zombies"][:60]:
                options.append((class_name.replace("_", " "), f"class:{class_name}"))
        if event_type in (None, "animal_pack", "custom_spawn"):
            for class_name in reference["animals"][:40]:
                options.append((class_name.replace("_", " "), f"class:{class_name}"))
        if event_type in (None, "loot_crate", "airdrop", "custom_spawn"):
            for class_name in reference["containers"][:30]:
                options.append((class_name.replace("_", " "), f"class:{class_name}"))

    options.append(("Custom classname", "custom"))
    return options


def scenario_vehicle_preset_options():
    return [
        (preset.get("label", key), key)
        for key, preset in SCENARIO_VEHICLE_PRESETS.items()
    ]


def scenario_guard_preset_options():
    options = [("No guards", "none")]
    for key, preset in SCENARIO_SPAWN_PRESETS.items():
        if key == "custom" or preset.get("event_type") != "zombie_horde":
            continue
        options.append((preset.get("label", key), key))
    options.append(("Custom zombie classname", "custom"))
    return options


def resolve_scenario_spawn_preset(map_key, spawn_preset, custom_class=""):
    spawn_preset = str(spawn_preset or "").strip()
    if spawn_preset.startswith("class:"):
        class_name = spawn_preset.split(":", 1)[1].strip()
        return {
            "class": class_name,
            "label": class_name,
            "event_type": infer_scenario_type_from_class(class_name),
        }

    preset = dict(SCENARIO_SPAWN_PRESETS.get(spawn_preset, {}))
    if preset:
        return preset

    reference = load_dayz_reference(map_key)
    if spawn_preset in reference.get("types", set()):
        return {
            "class": spawn_preset,
            "label": spawn_preset,
            "event_type": infer_scenario_type_from_class(spawn_preset),
        }

    if custom_class:
        class_name = str(custom_class or "").strip()
        return {
            "class": class_name,
            "label": class_name,
            "event_type": infer_scenario_type_from_class(class_name),
        }

    return dict(SCENARIO_SPAWN_PRESETS["custom"])


def resolve_scenario_vehicle_preset(vehicle_preset, custom_class=""):
    vehicle_preset = str(vehicle_preset or "").strip()
    preset = dict(SCENARIO_VEHICLE_PRESETS.get(vehicle_preset, {}))
    if preset:
        if vehicle_preset == "custom" and custom_class:
            preset["class"] = str(custom_class or "").strip()
            preset["label"] = preset["class"]
        return preset

    if custom_class:
        class_name = str(custom_class or "").strip()
        return {"label": class_name, "class": class_name}

    return dict(SCENARIO_VEHICLE_PRESETS["custom"])


def resolve_scenario_guard_class(guard_preset, custom_class=""):
    guard_preset = str(guard_preset or "none").strip()
    if guard_preset == "none":
        return "", "No guards"

    if guard_preset == "custom":
        class_name = str(custom_class or "").strip()
        return class_name, class_name or "Custom guard"

    preset = SCENARIO_SPAWN_PRESETS.get(guard_preset, {})
    return preset.get("class", ""), preset.get("label", guard_preset)


def scenario_events_for_config(config):
    events = config.setdefault("scenario_events", [])
    if not isinstance(events, list):
        events = []
        config["scenario_events"] = events
    return events


def next_scenario_event_id(config):
    existing_ids = []
    for event in scenario_events_for_config(config):
        try:
            existing_ids.append(int(event.get("id", 0)))
        except Exception:
            pass
    return (max(existing_ids) if existing_ids else 0) + 1


def active_scenario_events(config):
    return [
        event
        for event in scenario_events_for_config(config)
        if event.get("enabled", True)
    ]


def has_active_scenario_events(config):
    return bool(active_scenario_events(config))


CONSOLE_OBJECT_SPAWNER_REF = "./custom/WanderingBotObjects.json"
CONSOLE_OBJECT_SPAWNER_PATH = "/dayzxb/custom/WanderingBotObjects.json"
CONSOLE_CFGGAMEPLAY_CANDIDATES = [
    "/dayzxb/cfggameplay.json",
    "/dayzxb/config/cfggameplay.json",
    "/dayzps/cfggameplay.json",
    "/dayzps/config/cfggameplay.json",
]


def console_object_spawner_config(config):
    settings = config.setdefault("console_object_spawner", {})
    settings.setdefault("enabled", False)
    settings.setdefault("object_path", CONSOLE_OBJECT_SPAWNER_PATH)
    settings.setdefault("spawner_ref", CONSOLE_OBJECT_SPAWNER_REF)
    settings.setdefault("cfggameplay_path", "")
    settings.setdefault("objects", [])
    if not isinstance(settings.get("objects"), list):
        settings["objects"] = []
    return settings


def next_console_object_id(settings):
    existing_ids = []
    for item in settings.get("objects", []):
        try:
            existing_ids.append(int(item.get("id", 0)))
        except Exception:
            pass
    return (max(existing_ids) if existing_ids else 0) + 1


def dayz_object_record(class_name, x, z, y=0, yaw=0, pitch=0, roll=0, scale=1.0, persistent=False, object_id=None):
    x_value = parse_dayz_map_number(x)
    y_value = parse_dayz_map_number(y)
    z_value = parse_dayz_map_number(z)
    yaw_value = parse_dayz_map_number(yaw)
    pitch_value = parse_dayz_map_number(pitch)
    roll_value = parse_dayz_map_number(roll)
    scale_value = parse_dayz_map_number(scale)

    if not str(class_name or "").strip() or x_value is None or z_value is None:
        return None

    return {
        "id": object_id,
        "name": str(class_name).strip(),
        "pos": [x_value, y_value or 0, z_value],
        "ypr": [yaw_value or 0, pitch_value or 0, roll_value or 0],
        "scale": scale_value or 1.0,
        "enableCEPersistency": bool(persistent),
    }


def build_console_object_spawner_json(objects):
    output = {"Objects": []}
    for item in objects or []:
        record = dayz_object_record(
            item.get("name"),
            (item.get("pos") or [None, None, None])[0] if isinstance(item.get("pos"), list) else item.get("x"),
            (item.get("pos") or [None, None, None])[2] if isinstance(item.get("pos"), list) and len(item.get("pos")) >= 3 else item.get("z"),
            (item.get("pos") or [None, 0, None])[1] if isinstance(item.get("pos"), list) and len(item.get("pos")) >= 2 else item.get("y", 0),
            (item.get("ypr") or [0, 0, 0])[0] if isinstance(item.get("ypr"), list) else item.get("yaw", 0),
            (item.get("ypr") or [0, 0, 0])[1] if isinstance(item.get("ypr"), list) and len(item.get("ypr")) >= 2 else item.get("pitch", 0),
            (item.get("ypr") or [0, 0, 0])[2] if isinstance(item.get("ypr"), list) and len(item.get("ypr")) >= 3 else item.get("roll", 0),
            item.get("scale", 1.0),
            item.get("enableCEPersistency", item.get("persistent", False)),
            item.get("id"),
        )
        if not record:
            continue
        record.pop("id", None)
        output["Objects"].append(record)
    return json.dumps(output, indent=4)


def load_reference_cfggameplay_text(map_key):
    map_key = "livonia" if map_key == "livonia" else "chernarus"
    path = dayz_reference_path(map_key, "cfggameplay.json")
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as source:
            return source.read()
    return '{\n    "version": 123,\n    "WorldsData": {\n        "objectSpawnersArr": []\n    }\n}\n'


def update_cfggameplay_object_spawner(cfggameplay_text, spawner_ref):
    data = json.loads(cfggameplay_text or "{}")
    worlds = data.setdefault("WorldsData", {})
    spawners = worlds.setdefault("objectSpawnersArr", [])
    if not isinstance(spawners, list):
        spawners = []
        worlds["objectSpawnersArr"] = spawners

    wanted = str(spawner_ref or CONSOLE_OBJECT_SPAWNER_REF).strip()
    normalized_existing = {str(item).replace("\\", "/").lower() for item in spawners}
    changed = False
    if wanted.replace("\\", "/").lower() not in normalized_existing:
        spawners.append(wanted)
        changed = True

    return json.dumps(data, indent=4), changed


def download_cfggameplay_with_fallback(config, guild_id, requested_path=""):
    paths = []
    if requested_path:
        paths.append(requested_path)
    settings = console_object_spawner_config(config)
    if settings.get("cfggameplay_path"):
        paths.append(settings["cfggameplay_path"])
    paths.extend(CONSOLE_CFGGAMEPLAY_CANDIDATES)

    tried = []
    for path in paths:
        if not path or path in tried:
            continue
        tried.append(path)
        ok, message, content = download_text_file_from_nitrado(config, path)
        if ok and content:
            return True, message, content, path

    map_key = server_map_key(guild_id)
    return False, "Could not download cfggameplay.json; using bundled vanilla template.", load_reference_cfggameplay_text(map_key), (requested_path or settings.get("cfggameplay_path") or CONSOLE_CFGGAMEPLAY_CANDIDATES[0])


def console_mission_folder_for_map(map_key):
    return DAYZ_REFERENCE_MAP_FOLDERS.get(map_key) or DAYZ_REFERENCE_MAP_FOLDERS["chernarus"]


def console_ce_default_paths(guild_id):
    mission_folder = console_mission_folder_for_map(server_map_key(guild_id))
    return {
        "events_path": f"/dayzxb/mpmissions/{mission_folder}/db/events.xml",
        "spawns_path": f"/dayzxb/mpmissions/{mission_folder}/cfgeventspawns.xml",
        "spawnabletypes_path": f"/dayzxb/mpmissions/{mission_folder}/cfgspawnabletypes.xml",
    }


def console_ce_event_config(config):
    settings = config.setdefault("console_ce_events", {})
    settings.setdefault("enabled", False)
    settings.setdefault("events_path", "")
    settings.setdefault("spawns_path", "")
    settings.setdefault("spawnabletypes_path", "")
    return settings


def ce_event_name(event, suffix=""):
    event_id = int(event.get("id", 0) or 0)
    kind = normalize_discord_name(event.get("event_type", "event")) or "event"
    tail = f"_{normalize_discord_name(suffix)}" if suffix else ""
    return f"{CONSOLE_CE_EVENT_PREFIX}{event_id}_{kind}{tail}"[:64]


def ce_event_nominal_count(event, override_count=None):
    try:
        count = int(override_count if override_count is not None else event.get("count", 1))
    except Exception:
        count = 1
    return max(1, min(250, count))


def xml_text_from_root(root):
    try:
        ET.indent(root, space="    ")
    except Exception:
        pass
    return "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n" + ET.tostring(root, encoding="unicode")


def parse_xml_root_or_new(text, fallback_root):
    text = str(text or "").strip()
    if not text:
        return ET.Element(fallback_root), "Created new template because the source XML was empty."

    try:
        return ET.fromstring(text.encode("utf-8")), None
    except Exception as error:
        return ET.Element(fallback_root), f"Created new `{fallback_root}` template because XML parsing failed: {error}"


def remove_wandering_ce_nodes(root):
    removed = 0
    for child in list(root):
        name = str(child.get("name") or "")
        if name.startswith(CONSOLE_CE_EVENT_PREFIX):
            root.remove(child)
            removed += 1
    return removed


def console_ce_needs_spawnabletypes(config):
    for event in active_scenario_events(config):
        if event.get("event_type") == "airdrop" and event.get("loot"):
            return True
    return False


def cfgspawnabletypes_loot_signature(cargo_node):
    return tuple(sorted(
        str(item.get("name") or "").strip()
        for item in cargo_node.findall("item")
        if str(item.get("name") or "").strip()
    ))


def find_or_create_spawnable_type(root, class_name):
    wanted = str(class_name or "").strip()
    for type_node in root.findall("type"):
        if str(type_node.get("name") or "").strip().lower() == wanted.lower():
            return type_node, False

    return ET.SubElement(root, "type", {"name": wanted}), True


def merge_airdrop_loot_into_spawnabletypes(root, events):
    changed_classes = set()
    cargo_blocks = 0

    for event in events:
        if event.get("event_type") != "airdrop":
            continue

        class_name = str(event.get("class_name") or "").strip()
        loot = [
            str(item).strip()
            for item in (event.get("loot") or [])
            if str(item).strip()
        ]
        if not class_name or not loot:
            continue

        type_node, _ = find_or_create_spawnable_type(root, class_name)
        signature = tuple(sorted(loot))

        for cargo_node in list(type_node.findall("cargo")):
            if cfgspawnabletypes_loot_signature(cargo_node) == signature:
                type_node.remove(cargo_node)

        cargo_node = ET.SubElement(type_node, "cargo", {"chance": "1.00"})
        for item_name in loot:
            ET.SubElement(cargo_node, "item", {
                "name": item_name,
                "chance": "1.00",
            })

        changed_classes.add(class_name)
        cargo_blocks += 1

    return sorted(changed_classes), cargo_blocks


def ce_decimal(value, default=0):
    parsed = parse_dayz_map_number(value)
    if parsed is None:
        parsed = default
    return f"{float(parsed):.2f}".rstrip("0").rstrip(".")


def add_console_ce_event_definition(root, event_name, child_type, count, lifetime, restock=0):
    event_node = ET.SubElement(root, "event", {"name": event_name})
    fields = [
        ("nominal", count),
        ("min", count),
        ("max", count),
        ("lifetime", lifetime),
        ("restock", restock),
        ("saferadius", 0),
        ("distanceradius", 0),
        ("cleanupradius", 100),
    ]
    for tag, value in fields:
        child = ET.SubElement(event_node, tag)
        child.text = str(int(value))

    flags = ET.SubElement(event_node, "flags")
    flags.set("deletable", "1")
    flags.set("init_random", "0")
    flags.set("remove_damaged", "0")

    position = ET.SubElement(event_node, "position")
    position.text = "fixed"
    limit = ET.SubElement(event_node, "limit")
    limit.text = "custom"
    active = ET.SubElement(event_node, "active")
    active.text = "1"

    children = ET.SubElement(event_node, "children")
    ET.SubElement(children, "child", {
        "lootmax": "-1",
        "lootmin": "-1",
        "max": str(int(count)),
        "min": str(int(count)),
        "type": str(child_type),
    })
    return event_node


def add_console_ce_event_spawn(root, event_name, x, z, angle=0):
    event_node = ET.SubElement(root, "event", {"name": event_name})
    ET.SubElement(event_node, "pos", {
        "x": ce_decimal(x),
        "z": ce_decimal(z),
        "a": ce_decimal(angle),
    })
    return event_node


def console_ce_records_for_event(event):
    event_type = str(event.get("event_type") or "").strip()
    class_name = str(event.get("class_name") or "").strip()
    records = []
    warnings = []

    if event_type in {"vehicle_reset_all", "vehicle_reset_point"}:
        warnings.append(
            f"`{event.get('id')}` is a vehicle reset. Native console XML can add vehicle spawn events, but it cannot delete/reset existing vehicles on command."
        )
        return records, warnings

    if not class_name:
        warnings.append(f"`{event.get('id')}` has no classname, so it was skipped.")
        return records, warnings

    count = ce_event_nominal_count(event)
    lifetime = 3600
    if event_type == "vehicle_spawn":
        count = 1
        lifetime = 3888000
    elif event_type == "airdrop":
        count = 1
        lifetime = 7200
    elif event_type == "zombie_horde":
        lifetime = 1800

    records.append({
        "name": ce_event_name(event),
        "class_name": class_name,
        "count": count,
        "lifetime": lifetime,
        "x": event.get("x"),
        "z": event.get("z"),
    })

    if event_type == "airdrop":
        guard_class = str(event.get("guard_class") or "").strip()
        guard_count = ce_event_nominal_count(event, event.get("guard_count", 0)) if guard_class else 0
        if guard_class and guard_count:
            records.append({
                "name": ce_event_name(event, "guards"),
                "class_name": guard_class,
                "count": guard_count,
                "lifetime": 1800,
                "x": event.get("x"),
                "z": event.get("z"),
            })

        marker_class = str(event.get("marker_class") or "").strip()
        if event.get("visual_marker") and marker_class:
            records.append({
                "name": ce_event_name(event, "marker"),
                "class_name": marker_class,
                "count": 1,
                "lifetime": 7200,
                "x": event.get("x"),
                "z": event.get("z"),
            })

        if event.get("loot_preset") and event.get("loot_preset") != "none":
            warnings.append(
                f"`{event.get('id')}` keeps its airdrop crate spawn, but exact crate contents need cfgspawnabletypes/types tuning; CE XML alone cannot fill one single crate instance."
            )

    if event_type == "vehicle_spawn" and event.get("vehicle_condition") and event.get("vehicle_condition") != "no_parts":
        warnings.append(
            f"`{event.get('id')}` spawns the vehicle event, but exact fuel/parts condition is not guaranteed by events.xml/cfgeventspawns.xml alone."
        )

    return records, warnings


def download_console_ce_source(config, guild_id, key, requested_path=""):
    defaults = console_ce_default_paths(guild_id)
    settings = console_ce_event_config(config)
    target_path = requested_path or settings.get(key) or defaults[key]
    ok, message, text = download_text_file_from_nitrado(config, target_path)
    if ok and text:
        return text, target_path, message

    map_key = server_map_key(guild_id)
    if key == "events_path":
        reference_parts = ("db", "events.xml")
        fallback_root = "events"
    elif key == "spawnabletypes_path":
        reference_parts = ("cfgspawnabletypes.xml",)
        fallback_root = "spawnabletypes"
    else:
        reference_parts = ("cfgeventspawns.xml",)
        fallback_root = "eventposdef"

    reference_text = load_dayz_reference_text(map_key, *reference_parts)
    if reference_text:
        return reference_text, target_path, f"{message} Using bundled vanilla reference as fallback."

    return f"<{fallback_root}></{fallback_root}>\n", target_path, f"{message} No bundled reference was found, so a minimal template was used."


def build_console_ce_event_files(guild_id, config, events_path="", spawns_path="", spawnabletypes_path=""):
    events_text, resolved_events_path, events_source = download_console_ce_source(config, guild_id, "events_path", events_path)
    spawns_text, resolved_spawns_path, spawns_source = download_console_ce_source(config, guild_id, "spawns_path", spawns_path)

    events_root, events_parse_warning = parse_xml_root_or_new(events_text, "events")
    spawns_root, spawns_parse_warning = parse_xml_root_or_new(spawns_text, "eventposdef")

    removed_events = remove_wandering_ce_nodes(events_root)
    removed_spawns = remove_wandering_ce_nodes(spawns_root)

    records = []
    warnings = []
    for event in active_scenario_events(config):
        event_records, event_warnings = console_ce_records_for_event(event)
        records.extend(event_records)
        warnings.extend(event_warnings)

    for record in records:
        add_console_ce_event_definition(
            events_root,
            record["name"],
            record["class_name"],
            record["count"],
            record["lifetime"],
        )
        add_console_ce_event_spawn(
            spawns_root,
            record["name"],
            record["x"],
            record["z"],
        )

    messages = [
        events_source,
        spawns_source,
        f"Removed `{removed_events}` old WanderingBot event definition(s) and `{removed_spawns}` old spawn point block(s).",
        f"Generated `{len(records)}` native CE event record(s).",
    ]
    if events_parse_warning:
        messages.append(events_parse_warning)
    if spawns_parse_warning:
        messages.append(spawns_parse_warning)
    messages.extend(warnings)

    output = {
        "events_path": resolved_events_path,
        "events_text": xml_text_from_root(events_root),
        "spawns_path": resolved_spawns_path,
        "spawns_text": xml_text_from_root(spawns_root),
        "spawnabletypes_path": "",
        "spawnabletypes_text": "",
        "record_count": len(records),
        "messages": messages,
    }

    if console_ce_needs_spawnabletypes(config):
        spawnable_text, resolved_spawnable_path, spawnable_source = download_console_ce_source(
            config,
            guild_id,
            "spawnabletypes_path",
            spawnabletypes_path
        )
        spawnable_root, spawnable_parse_warning = parse_xml_root_or_new(spawnable_text, "spawnabletypes")
        changed_classes, cargo_blocks = merge_airdrop_loot_into_spawnabletypes(spawnable_root, active_scenario_events(config))
        output["spawnabletypes_path"] = resolved_spawnable_path
        output["spawnabletypes_text"] = xml_text_from_root(spawnable_root)
        output["messages"].append(spawnable_source)
        output["messages"].append(
            f"Updated `cfgspawnabletypes.xml` with `{cargo_blocks}` airdrop cargo block(s) for: "
            + (", ".join(f"`{item}`" for item in changed_classes) if changed_classes else "none")
        )
        output["messages"].append(
            "Note: crate cargo tuning is class-based, so using `WoodenCrate` means other CE-spawned WoodenCrate instances can share that cargo setup."
        )
        if spawnable_parse_warning:
            output["messages"].append(spawnable_parse_warning)

    return output


def upload_console_ce_event_files(guild_id, config, events_path="", spawns_path="", spawnabletypes_path="", consume_restart=False):
    built = build_console_ce_event_files(guild_id, config, events_path, spawns_path, spawnabletypes_path)
    messages = list(built["messages"])

    events_ok, events_message = upload_text_file_to_nitrado(config, built["events_path"], built["events_text"])
    spawns_ok, spawns_message = upload_text_file_to_nitrado(config, built["spawns_path"], built["spawns_text"])
    messages.append(f"`events.xml`: {events_message}")
    messages.append(f"`cfgeventspawns.xml`: {spawns_message}")

    spawnable_ok = True
    if built.get("spawnabletypes_text"):
        spawnable_ok, spawnable_message = upload_text_file_to_nitrado(
            config,
            built["spawnabletypes_path"],
            built["spawnabletypes_text"]
        )
        messages.append(f"`cfgspawnabletypes.xml`: {spawnable_message}")

    success = events_ok and spawns_ok and spawnable_ok
    if success:
        settings = console_ce_event_config(config)
        settings["enabled"] = True
        settings["events_path"] = built["events_path"]
        settings["spawns_path"] = built["spawns_path"]
        if built.get("spawnabletypes_path"):
            settings["spawnabletypes_path"] = built["spawnabletypes_path"]
        if consume_restart:
            mark_one_time_scenario_events_uploaded(config)
        save_guild_configs()

    return success, built, messages


def scenario_location_from_choice(location_key, x=None, z=None, y=0, map_key="chernarus"):
    presets = scenario_location_presets_for_map(map_key)
    location = presets.get(str(location_key or "").lower())
    if not location:
        location = presets.get("custom", SCENARIO_LOCATION_PRESETS["custom"])

    if location_key == "custom":
        x_value = parse_dayz_map_number(x)
        z_value = parse_dayz_map_number(z)
        y_value = parse_dayz_map_number(y) if y is not None else 0
        if x_value is None or z_value is None:
            return None, "Custom location needs numeric `x` and `z` coordinates."
        return {
            "name": "Custom Coordinates",
            "x": x_value,
            "y": y_value or 0,
            "z": z_value,
        }, None

    return dict(location), None


def build_scenario_event_xml(event):
    x = parse_dayz_map_number(event.get("x"))
    y = parse_dayz_map_number(event.get("y", 0))
    z = parse_dayz_map_number(event.get("z"))
    class_name = str(event.get("class_name") or "").strip()
    event_type = str(event.get("event_type") or "").strip()
    if x is None or z is None:
        return None

    if event_type == "vehicle_reset_all":
        excluded = event.get("exclude") or []
        if isinstance(excluded, str):
            excluded = [item.strip() for item in excluded.split(",") if item.strip()]
        exclude_attr = "|".join(str(item).strip() for item in excluded if str(item).strip())
        radius = max(1000, min(30000, int(event.get("radius", 22000) or 22000)))
        return (
            f'<object action="reset_all_vehicles" name="ALL_VEHICLES" '
            f'pos="{x} {y or 0} {z}" radius="{radius}" '
            f'exclude="{safe_xml_attr(exclude_attr)}" event_id="{safe_xml_attr(event.get("id", ""))}" />'
        )

    if event_type == "vehicle_reset_point":
        if not class_name:
            return None
        radius = max(5, min(250, int(event.get("radius", 35) or 35)))
        return (
            f'<object action="reset_vehicle" name="{safe_xml_attr(class_name)}" '
            f'pos="{x} {y or 0} {z}" radius="{radius}" '
            f'event_id="{safe_xml_attr(event.get("id", ""))}" />'
        )

    if not class_name:
        return None

    count = max(1, min(250, int(event.get("count", 1) or 1)))
    radius = max(0, min(2000, int(event.get("radius", 0) or 0)))
    loot = event.get("loot") or []
    if isinstance(loot, str):
        loot = [item.strip() for item in loot.split(",") if item.strip()]
    loot_attr = "|".join(str(item).strip() for item in loot if str(item).strip())

    extra_attrs = {
        "event_type": event.get("event_type", ""),
        "loot_preset": event.get("loot_preset", ""),
        "vehicle_condition": event.get("vehicle_condition", ""),
        "guard_class": event.get("guard_class", ""),
        "guard_count": event.get("guard_count", ""),
        "guard_radius": event.get("guard_radius", ""),
        "marker_class": event.get("marker_class", ""),
        "visual_marker": "1" if event.get("visual_marker") else "",
    }
    extra_text = " ".join(
        f'{key}="{safe_xml_attr(value)}"'
        for key, value in extra_attrs.items()
        if str(value or "").strip()
    )
    if extra_text:
        extra_text = " " + extra_text

    return (
        f'<object action="spawn_event" name="{safe_xml_attr(class_name)}" '
        f'pos="{x} {y or 0} {z}" count="{count}" radius="{radius}" '
        f'loot="{safe_xml_attr(loot_attr)}" event_id="{safe_xml_attr(event.get("id", ""))}"{extra_text} />'
    )


def scenario_event_mode_text(event):
    if event.get("permanent"):
        return "forever"

    remaining = event.get("remaining_restarts")
    if remaining is None:
        return "one-time"

    try:
        remaining = int(remaining)
    except Exception:
        return "one-time"

    if remaining <= 0:
        return "forever"

    return f"{remaining} restart(s)"


async def auto_push_scenario_events_xml(guild_id, config):
    """Push merged events.xml / cfgeventspawns.xml / cfgspawnabletypes.xml to
    Nitrado right after an admin creates a new scenario event.

    Returns a tuple (success, status_text) where `status_text` is a human-
    readable string suitable for embed descriptions. Does NOT consume the
    event's restart counter — the normal restart processor handles that on
    the actual server restart.
    """
    try:
        upload_success, _, upload_messages = await asyncio.to_thread(
            upload_console_ce_event_files,
            guild_id,
            config,
            "",
            "",
            "",
            False,
        )
    except Exception as upload_error:
        return False, (
            "⚠️ Event created but auto-upload to Nitrado FAILED — it will NOT appear "
            f"on the server until you run `/events uploadce`. Reason: {upload_error}"
        )

    if upload_success:
        return True, (
            "✅ XML uploaded to Nitrado. Event will appear after the next server restart."
        )

    last_msg = upload_messages[-1] if upload_messages else "no message"
    return False, (
        "⚠️ Event created but auto-upload to Nitrado FAILED — it will NOT appear "
        f"on the server until you run `/events uploadce`. Reason: {last_msg}"
    )


def restart_count_fields(restarts=1):
    try:
        restarts = int(restarts or 1)
    except Exception:
        restarts = 1

    if restarts <= 0:
        return {"permanent": True, "remaining_restarts": 0}

    return {"permanent": False, "remaining_restarts": max(1, min(365, restarts))}


def mark_one_time_scenario_events_uploaded(config):
    events = scenario_events_for_config(config)
    kept = []

    for event in events:
        if not event.get("enabled", True):
            kept.append(event)
            continue

        if event.get("permanent"):
            kept.append(event)
            continue

        if "remaining_restarts" not in event:
            continue

        try:
            remaining = int(event.get("remaining_restarts", 1) or 1)
        except Exception:
            remaining = 1

        remaining -= 1
        if remaining > 0:
            event["remaining_restarts"] = remaining
            kept.append(event)

    config["scenario_events"] = kept


def vehicle_reset_exclusions(config):
    excluded = config.setdefault("vehicle_reset_exclusions", [])
    if not isinstance(excluded, list):
        excluded = []
        config["vehicle_reset_exclusions"] = excluded
    return [str(item) for item in excluded if str(item).strip()]


def known_vehicle_classes(limit=25):
    classes = []

    for item_name, data in shop_items.items():
        if str(data.get("category", "")).lower() == "vehicles":
            classes.append(str(item_name))

    if not classes:
        classes = DEFAULT_VEHICLE_RESET_CLASSES.copy()

    deduped = []
    seen = set()
    for item_name in sorted(classes):
        key = normalize_discord_name(item_name)
        if not key or key in seen:
            continue
        deduped.append(item_name)
        seen.add(key)

    return deduped[:limit]


def queue_all_vehicle_reset(guild_id, config, requested_by):
    map_width, map_height = server_map_size(guild_id)
    center_x = map_width / 2
    center_y = map_height / 2
    radius = int(max(map_width, map_height) * 1.5)
    excluded = vehicle_reset_exclusions(config)

    reset_entry = {
        "action": "reset_all_vehicles",
        "player": str(requested_by),
        "discord_id": str(getattr(requested_by, "id", "")),
        "vehicle": "ALL_VEHICLES",
        "x": str(center_x),
        "y": str(center_y),
        "radius": radius,
        "exclude": excluded,
        "status": "queued",
        "created": str(datetime.now(UTC))
    }

    vehicle_rentals_queue.append(reset_entry)
    save_delivery_queue()
    return reset_entry


# =========================================================
# BASIC SHOP COMMANDS
# =========================================================

@bot.command()
async def wallet(ctx):

    user_id = str(ctx.author.id)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

        save_wallets()

    balance = wallets[user_id]["balance"]

    embed = discord.Embed(
        title="💰 SURVIVOR WALLET",
        description=f"{balance} pennies 🪙",
        color=0x2ECC71
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def shop(ctx):

    if not shop_items:

        await ctx.send("Shop is currently empty.")
        return

    lines = []

    for item_name, data in shop_items.items():

        lines.append(
            f"• {item_name} — {data.get('price', 0)} pennies 🪙"
        )

    embed = discord.Embed(
        title="🛒 BLACK MARKET SHOP",
        description="\n".join(lines[:25]),
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Black Market"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
async def buy(ctx, item_name: str, x: str, y: str):

    user_id = str(ctx.author.id)

    if item_name not in shop_items:

        await ctx.send("That item does not exist in the shop.")
        return

    if not shop_items[item_name].get("enabled", True):

        await ctx.send("❌ That item is currently disabled.")
        return

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

    wallet = wallets[user_id]

    limit = DEFAULT_DAILY_TRANSACTION_LIMIT

    if wallet["daily_transactions"] >= limit:

        await ctx.send("❌ Daily delivery limit reached.")
        return

    price = shop_items[item_name].get("price", 0)

    if wallet["balance"] < price:

        await ctx.send("❌ Not enough pennies.")
        return

    wallet["balance"] -= price
    wallet["daily_transactions"] += 1

    delivery_queue.append({
        "delivery_type": "item",
        "spawn_ready": False,
        "player": str(ctx.author),
        "discord_id": user_id,
        "item": item_name,
        "x": x,
        "y": y,
        "status": "queued",
        "created": str(datetime.now(UTC))
    })

    save_wallets()
    save_delivery_queue()

    map_link = f"https://dayz.ginfo.gg/#location={x};{y}"

    embed = discord.Embed(
        title="📦 DELIVERY QUEUED",
        description=(
            f"Your order has been added to the next restart delivery queue."
        ),
        color=0x3498DB
    )

    embed.add_field(
        name="📦 Item",
        value=item_name,
        inline=True
    )

    embed.add_field(
        name="💰 Cost",
        value=f"{price} pennies 🪙",
        inline=True
    )

    embed.add_field(
        name="📍 Delivery Location",
        value=f"[🔵 Open Map](<{map_link}>)",
        inline=False
    )

    embed.add_field(
        name="⏰ Delivery ETA",
        value="Next server restart",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Black Market Delivery"
    )

    await ctx.send(embed=style_embed(embed))

    # ================= PURCHASE LOG =================

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    purchase_log_channel = bot.get_channel(
        config.get("channels", {}).get("purchase_logs")
    )

    if purchase_log_channel:

        log_embed = discord.Embed(
            title="💳 NEW BLACK MARKET PURCHASE",
            color=0x9B59B6
        )

        log_embed.add_field(
            name="👤 Survivor",
            value=ctx.author.mention,
            inline=True
        )

        log_embed.add_field(
            name="📦 Item",
            value=item_name,
            inline=True
        )

        log_embed.add_field(
            name="💰 Price",
            value=f"{price} pennies 🪙",
            inline=True
        )

        log_embed.add_field(
            name="📍 Delivery Location",
            value=f"[🔵 Open Map](<{map_link}>)",
            inline=False
        )

        log_embed.set_thumbnail(url=BOT_IMAGE)

        log_embed.set_footer(
            text="Wandering Bot Alpha • Purchase Logs"
        )

        await purchase_log_channel.send(
            embed=style_embed(log_embed)
        )


# =========================================================
# VEHICLE RENTAL SYSTEM
# =========================================================


def safe_xml_attr(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def parse_dayz_map_number(value):
    try:
        return float(str(value).strip().replace(",", ""))
    except Exception:
        return None


def build_delivery_xml(items, vehicles, scenario_events=None):
    xml_lines = ["<objects>"]

    for delivery in items:
        item_name = delivery.get("item")
        x = parse_dayz_map_number(delivery.get("x"))
        y = parse_dayz_map_number(delivery.get("y"))
        if not item_name or x is None or y is None:
            continue

        xml_lines.append(
            f'<object action="spawn_item" name="{safe_xml_attr(item_name)}" pos="{x} 0 {y}" />'
        )

    for vehicle in vehicles:
        vehicle_name = vehicle.get("vehicle")
        x = parse_dayz_map_number(vehicle.get("x"))
        y = parse_dayz_map_number(vehicle.get("y"))
        if not vehicle_name or x is None or y is None:
            continue

        action = vehicle.get("action") or "spawn_vehicle"
        radius = max(5, min(250, int(vehicle.get("radius", 35) or 35)))
        if action == "reset_all_vehicles":
            radius = max(1000, min(30000, int(vehicle.get("radius", 22000) or 22000)))
            excluded = vehicle.get("exclude") or []
            if isinstance(excluded, str):
                excluded = [item.strip() for item in excluded.split(",") if item.strip()]
            exclude_attr = "|".join(str(item).strip() for item in excluded if str(item).strip())
            xml_lines.append(
                f'<object action="reset_all_vehicles" name="ALL_VEHICLES" pos="{x} 0 {y}" radius="{radius}" exclude="{safe_xml_attr(exclude_attr)}" />'
            )
            continue

        radius_attr = f' radius="{radius}"' if action == "reset_vehicle" else ""
        xml_lines.append(
            f'<object action="{safe_xml_attr(action)}" name="{safe_xml_attr(vehicle_name)}" pos="{x} 0 {y}"{radius_attr} />'
        )

    for event in scenario_events or []:
        event_line = build_scenario_event_xml(event)
        if event_line:
            xml_lines.append(event_line)

    xml_lines.append("</objects>")
    return "\n".join(xml_lines)


def write_and_upload_delivery_xml(guild_id, config, generated_at=None):
    generated_at = generated_at or datetime.now(UTC)
    delivery_file = os.path.join(
        GUILD_DATA_FOLDER,
        f"{guild_id}_deliveries.json"
    )
    output = {
        "items": delivery_queue,
        "vehicles": vehicle_rentals_queue,
        "scenario_events": [] if console_ce_event_config(config).get("enabled") else active_scenario_events(config),
        "generated": str(generated_at)
    }

    save_json(delivery_file, output)
    print(f"DELIVERY FILE GENERATED FOR {guild_id}")

    xml_output_path = os.path.join(
        GUILD_DATA_FOLDER,
        f"{guild_id}_deliveries.xml"
    )

    with open(xml_output_path, "w", encoding="utf-8") as xml_file:
        bridge_scenario_events = [] if console_ce_event_config(config).get("enabled") else active_scenario_events(config)
        xml_file.write(build_delivery_xml(delivery_queue, vehicle_rentals_queue, bridge_scenario_events))

    print(f"XML DELIVERY FILE GENERATED FOR {guild_id}")
    upload_success = upload_delivery_xml_to_nitrado(config, xml_output_path)

    if upload_success:
        print(f"DELIVERY XML BRIDGED TO SERVER {guild_id}")
        delivery_queue.clear()
        vehicle_rentals_queue.clear()
        if not console_ce_event_config(config).get("enabled"):
            mark_one_time_scenario_events_uploaded(config)
        save_guild_configs()
        save_delivery_queue()

    return upload_success, xml_output_path


@bot.command()
async def rentvehicle(ctx, vehicle_name: str, rental_hours: int, x: str, y: str):

    user_id = str(ctx.author.id)

    if vehicle_name not in shop_items:

        await ctx.send("❌ Vehicle not available.")
        return

    vehicle_data = shop_items[vehicle_name]

    if vehicle_data.get("category", "").lower() != "vehicles":

        await ctx.send("❌ That item is not configured as a rentable vehicle.")
        return

    rental_price = vehicle_data.get("price", 0) * max(rental_hours, 1)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(ctx.author),
            "balance": 0,
            "daily_transactions": 0
        }

    if wallets[user_id]["balance"] < rental_price:

        await ctx.send("❌ Not enough pennies.")
        return

    wallets[user_id]["balance"] -= rental_price

    rental_entry = {
        "action": "spawn_vehicle",
        "player": str(ctx.author),
        "discord_id": user_id,
        "vehicle": vehicle_name,
        "x": x,
        "y": y,
        "rental_hours": rental_hours,
        "status": "queued",
        "created": str(datetime.now(UTC))
    }

    vehicle_rentals_queue.append(rental_entry)

    save_wallets()
    save_delivery_queue()

    map_link = f"https://dayz.ginfo.gg/#location={x};{y}"

    embed = discord.Embed(
        title="🚗 VEHICLE RENTAL CONFIRMED",
        description="Vehicle queued for next restart delivery.",
        color=0x3498DB
    )

    embed.add_field(
        name="🚗 Vehicle",
        value=vehicle_name,
        inline=True
    )

    embed.add_field(
        name="⏰ Rental Period",
        value=f"{rental_hours} hours",
        inline=True
    )

    embed.add_field(
        name="💰 Cost",
        value=f"{rental_price} pennies 🪙",
        inline=True
    )

    embed.add_field(
        name="📍 Spawn Location",
        value=f"[🔵 Open Map](<{map_link}>)",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Vehicle Rental System"
    )

    await ctx.send(embed=style_embed(embed))

    # ================= RENTAL LOG =================

    guild_id = str(ctx.guild.id)

    config = guild_configs.get(guild_id, {})

    rental_log_channel = bot.get_channel(
        config.get("channels", {}).get("rental_logs")
    )

    if rental_log_channel:

        rental_embed = discord.Embed(
            title="🚗 NEW VEHICLE RENTAL",
            color=0x3498DB
        )

        rental_embed.add_field(
            name="👤 Survivor",
            value=ctx.author.mention,
            inline=True
        )

        rental_embed.add_field(
            name="🚗 Vehicle",
            value=vehicle_name,
            inline=True
        )

        rental_embed.add_field(
            name="⏰ Rental Time",
            value=f"{rental_hours} hours",
            inline=True
        )

        rental_embed.add_field(
            name="💰 Cost",
            value=f"{rental_price} pennies 🪙",
            inline=True
        )

        rental_embed.add_field(
            name="📍 Spawn Location",
            value=f"[🔵 Open Map](<{map_link}>)",
            inline=False
        )

        rental_embed.set_thumbnail(url=BOT_IMAGE)

        rental_embed.set_footer(
            text="Wandering Bot Alpha • Vehicle Rental Logs"
        )

        await rental_log_channel.send(
            embed=style_embed(rental_embed)
        )


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def resetvehicle(ctx, vehicle_name: str, x: str, y: str, radius: int = 35):
    x_value = parse_dayz_map_number(x)
    y_value = parse_dayz_map_number(y)

    if x_value is None or y_value is None:
        await ctx.send("❌ Use numeric map coordinates, for example `/resetvehicle OffroadHatchback 7500 8400 35`.")
        return

    radius = max(5, min(250, int(radius or 35)))
    reset_entry = {
        "action": "reset_vehicle",
        "player": str(ctx.author),
        "discord_id": str(ctx.author.id),
        "vehicle": vehicle_name,
        "x": str(x_value),
        "y": str(y_value),
        "radius": radius,
        "status": "queued",
        "created": str(datetime.now(UTC))
    }

    vehicle_rentals_queue.append(reset_entry)
    save_delivery_queue()

    map_link = f"https://dayz.ginfo.gg/#location={x_value};{y_value}"
    embed = discord.Embed(
        title="🔄 VEHICLE RESET QUEUED",
        description=(
            "At the next configured restart delivery run, the DayZ bridge will delete matching old vehicles "
            "near this spawn point and create a fresh one there."
        ),
        color=0xF1C40F
    )
    embed.add_field(name="Vehicle", value=vehicle_name, inline=True)
    embed.add_field(name="Reset Radius", value=f"{radius}m", inline=True)
    embed.add_field(name="Spawn Position", value=f"[Open Map](<{map_link}>)", inline=False)
    embed.add_field(
        name="Important",
        value="This requires `/installdayzbridge install:true` and a server restart before the in-game action happens.",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await ctx.send(embed=style_embed(embed))


class VehicleResetExcludeSelect(discord.ui.Select):
    def __init__(self, guild_id, config):
        self.guild_id = str(guild_id)
        self.config = config
        vehicle_classes = known_vehicle_classes()
        excluded = set(vehicle_reset_exclusions(config))
        options = [
            discord.SelectOption(
                label=item_name[:100],
                value=item_name[:100],
                default=item_name in excluded
            )
            for item_name in vehicle_classes[:25]
        ]

        super().__init__(
            placeholder="Choose vehicle classes to exclude from the all-vehicle reset",
            min_values=0,
            max_values=max(1, len(options)),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if not has_interaction_admin_power(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        self.config["vehicle_reset_exclusions"] = list(self.values)
        save_guild_configs()
        excluded = vehicle_reset_exclusions(self.config)
        text = ", ".join(f"`{item}`" for item in excluded) or "None"
        await interaction.response.send_message(
            f"Vehicle reset exclusions updated: {text}",
            ephemeral=True
        )


class QueueAllVehicleResetButton(discord.ui.Button):
    def __init__(self, guild_id, config):
        super().__init__(
            label="Queue All-Vehicle Reset",
            style=discord.ButtonStyle.danger
        )
        self.guild_id = str(guild_id)
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        if not has_interaction_admin_power(interaction):
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        entry = queue_all_vehicle_reset(self.guild_id, self.config, interaction.user)
        excluded = entry.get("exclude", [])
        excluded_text = ", ".join(f"`{item}`" for item in excluded) or "None"
        await interaction.response.send_message(
            "All-vehicle reset queued for the next restart delivery run.\n"
            f"Excluded classes: {excluded_text}\n\n"
            "This requires `/installdayzbridge install:true` with the v5 bridge and a server restart before the in-game cleanup happens.",
            ephemeral=True
        )


class VehicleResetExcludeView(discord.ui.View):
    def __init__(self, guild_id, config):
        super().__init__(timeout=900)
        if known_vehicle_classes():
            self.add_item(VehicleResetExcludeSelect(guild_id, config))
        self.add_item(QueueAllVehicleResetButton(guild_id, config))


# =========================================================
# RESTART DELIVERY PROCESSOR
# =========================================================

@tasks.loop(minutes=1)
async def restart_delivery_processor():

    now = datetime.now(UTC)

    for guild_id, config in active_guild_config_items():

        try:

            restart_interval = config.get(
                "restart_interval_hours",
                DEFAULT_RESTART_INTERVAL_HOURS
            )

            restart_offset = config.get(
                "restart_start_hour",
                0
            )

            if now.minute != 0:
                continue

            if (
                now.hour >= restart_offset
                and ((now.hour - restart_offset) % restart_interval == 0)
            ):
                if delivery_queue or vehicle_rentals_queue or (has_active_scenario_events(config) and not console_ce_event_config(config).get("enabled")):
                    await asyncio.to_thread(
                        write_and_upload_delivery_xml,
                        guild_id,
                        config,
                        now
                    )

                if has_active_scenario_events(config) and console_ce_event_config(config).get("enabled"):
                    success, _, messages = await asyncio.to_thread(
                        upload_console_ce_event_files,
                        guild_id,
                        config,
                        "",
                        "",
                        "",
                        True
                    )
                    if not success:
                        print(f"CONSOLE CE EVENT UPLOAD FAILED {guild_id}: {' | '.join(messages[-4:])}")

        except Exception as error:
            print(f"DELIVERY XML SCHEDULE ERROR {guild_id}: {error}")


# =========================================================
# TYPES.XML SHOP MANAGEMENT SYSTEM
# =========================================================

@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def addshopitem(
    ctx,
    item_name: str,
    price: int,
    category: str = "General"
):

    shop_items[item_name] = {
        "price": price,
        "category": category,
        "enabled": True
    }

    save_shop()

    embed = discord.Embed(
        title="🛒 ITEM ADDED TO BLACK MARKET",
        color=0x2ECC71
    )

    embed.add_field(
        name="📦 Item",
        value=item_name,
        inline=True
    )

    embed.add_field(
        name="💰 Price",
        value=f"{price} pennies 🪙",
        inline=True
    )

    embed.add_field(
        name="📂 Category",
        value=category,
        inline=True
    )

    embed.add_field(
        name="📡 Delivery",
        value="Delivered next restart",
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    embed.set_footer(
        text="Wandering Bot Alpha • Economy Management"
    )

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def editshopitem(
    ctx,
    item_name: str,
    price: int = None,
    category: str = None
):

    if item_name not in shop_items:

        await ctx.send("❌ Item not found in shop.")
        return

    if price is not None:
        shop_items[item_name]["price"] = price

    if category is not None:
        shop_items[item_name]["category"] = category

    save_shop()

    embed = discord.Embed(
        title="✏️ SHOP ITEM UPDATED",
        description=f"Updated `{item_name}` successfully.",
        color=0x3498DB
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def toggleshopitem(ctx, item_name: str):

    if item_name not in shop_items:

        await ctx.send("❌ Item not found.")
        return

    current = shop_items[item_name].get("enabled", True)

    shop_items[item_name]["enabled"] = not current

    save_shop()

    state = "ENABLED" if not current else "DISABLED"

    embed = discord.Embed(
        title="📦 SHOP ITEM STATUS UPDATED",
        description=f"`{item_name}` is now {state}.",
        color=0x9B59B6
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def shopcategories(ctx):

    categories = {}

    for item, data in shop_items.items():

        category = data.get("category", "General")

        if category not in categories:
            categories[category] = []

        categories[category].append(item)

    embed = discord.Embed(
        title="📂 BLACK MARKET CATEGORIES",
        color=0xF1C40F
    )

    for category, items in categories.items():

        embed.add_field(
            name=f"📦 {category}",
            value=f"{len(items)} items",
            inline=False
        )

    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def importtypesxml(ctx, source_path: str = None, default_price: int = 100):

    added, updated, types_path = load_shop_items_from_types_xml(
        source_path,
        default_price,
        overwrite=False
    )

    if not types_path:
        await ctx.send("No `types.xml` file found. Put it beside the bot, in `guild_data`, or pass the folder/file path as `source_path`.")
        return

    embed = discord.Embed(
        title="🛒 TYPES.XML IMPORTED TO SHOP",
        description=f"Source: `{types_path}`",
        color=0x2ECC71
    )

    embed.add_field(name="Added", value=str(added), inline=True)
    embed.add_field(name="Updated", value=str(updated), inline=True)
    embed.add_field(name="Total Shop Items", value=str(len(shop_items)), inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)

    await ctx.send(embed=style_embed(embed))


# =========================================================
# ADMIN SHOP MANAGEMENT
# =========================================================


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def removeshopitem(ctx, *, item_name: str):

    if item_name not in shop_items:

        await ctx.send("Item not found.")
        return

    del shop_items[item_name]

    save_shop()

    await ctx.send(f"🗑️ Removed {item_name} from the shop.")


@bot.command()
@commands.check(lambda ctx: has_staff_permissions(ctx))
async def givepennies(ctx, member: discord.Member, amount: int):

    user_id = str(member.id)

    if user_id not in wallets:

        wallets[user_id] = {
            "name": str(member),
            "balance": 0,
            "daily_transactions": 0
        }

    wallets[user_id]["balance"] += amount

    save_wallets()

    await ctx.send(
        f"💰 Added {amount} pennies 🪙 to {member.mention}"
    )


@bot.tree.command(
    name="playerlottery",
    description="Admin only: pick a random currently-online player"
)
@app_commands.default_permissions(administrator=True)
async def player_lottery(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    ensure_guild_runtime(guild_id)
    pool = sorted(list(online_players.get(guild_id, set())))
    if not pool:
        await interaction.response.send_message("No online players to pick from.", ephemeral=True)
        return
    import random
    winner = random.choice(pool)
    embed = discord.Embed(
        title="🎰 PLAYER LOTTERY",
        description=f"Winner: **{winner}**",
        color=0xF1C40F
    )
    await interaction.response.send_message(embed=style_embed(embed))



@bot.tree.command(name="wanderingemoji", description="Show off one of Wandering Bot's own emojis")
async def wanderingemoji(interaction: discord.Interaction):
    icon = random_wandering_emoji()
    line = random.choice(WANDERING_EMOJI_SHOWCASE_LINES)
    await interaction.response.send_message(
        f"{icon} {line}",
        ephemeral=False
    )

@bot.tree.command(name="online", description="Show currently online survivors")
async def slash_online(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    ensure_guild_runtime(guild_id)
    guild_online = online_players[guild_id]
    player_list = "\n".join(f"🟢 {p}" for p in sorted(guild_online)) if guild_online else "No players online."
    embed = discord.Embed(
        title=f"✅🎮 ONLINE SURVIVORS 🎮✅ ({len(guild_online)})",
        description=player_list,
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="serverstatus", description="Show Wandering Bot status")
async def slash_serverstatus(interaction: discord.Interaction):
    total_guilds = len(guild_configs)
    total_players = sum(len(players) for players in online_players.values())
    embed = discord.Embed(title="📡 WANDERING BOT STATUS", color=0x3498DB)
    embed.add_field(name="Connected Servers", value=str(total_guilds), inline=True)
    embed.add_field(name="Tracked Players", value=str(total_players), inline=True)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="supportbot", description="Open an admin ticket with the bot owner")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(issue="Briefly describe your bot issue")
async def supportbot(interaction: discord.Interaction, issue: str):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    ticket_id = f"{guild_id}-{int(datetime.now(UTC).timestamp())}"
    local_channel = await get_or_create_support_channel(interaction.guild)

    support_tickets[ticket_id] = {
        "guild_id": guild_id,
        "guild_name": interaction.guild.name,
        "channel_id": local_channel.id,
        "requester_id": interaction.user.id,
        "requester_name": str(interaction.user),
        "issue": issue[:1500],
        "status": "open",
        "created": str(datetime.now(UTC))
    }
    save_support_tickets()

    local_embed = discord.Embed(
        title="Bot Support Ticket Opened",
        description=issue[:1500],
        color=0x3498DB
    )
    local_embed.add_field(name="Ticket ID", value=ticket_id, inline=False)
    local_embed.add_field(name="Opened By", value=interaction.user.mention, inline=False)
    local_embed.set_footer(text="Replies from the bot owner will appear here.")
    await local_channel.send(embed=style_embed(local_embed))

    owner_channel = bot.get_channel(int(BOT_OWNER_CHANNEL_ID)) if BOT_OWNER_CHANNEL_ID else None
    if owner_channel:
        owner_embed = discord.Embed(
            title="New Bot Support Ticket",
            description=issue[:1500],
            color=0xE67E22
        )
        owner_embed.add_field(name="Ticket ID", value=ticket_id, inline=False)
        owner_embed.add_field(name="Server", value=f"{interaction.guild.name} (`{guild_id}`)", inline=False)
        owner_embed.add_field(name="Requester", value=str(interaction.user), inline=False)
        owner_embed.add_field(name="Reply Command", value=f"/ownerreply ticket_id:{ticket_id}", inline=False)
        await owner_channel.send(embed=style_embed(owner_embed))

    await interaction.response.send_message(
        f"Support ticket `{ticket_id}` opened.",
        ephemeral=True
    )


@bot.tree.command(name="ownerreply", description="Owner only: reply to a support ticket")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(secret_code="Owner secret code", ticket_id="Ticket ID", message="Reply message")
async def ownerreply(interaction: discord.Interaction, secret_code: str, ticket_id: str, message: str):

    if not owner_secret_valid(interaction, secret_code):
        await reject_owner_command(interaction)
        return

    ticket = support_tickets.get(ticket_id)
    if not ticket:
        await interaction.response.send_message("Ticket not found.", ephemeral=True)
        return

    target_guild = bot.get_guild(int(ticket["guild_id"]))
    target_channel = bot.get_channel(int(ticket["channel_id"]))

    if not target_guild or not target_channel:
        await interaction.response.send_message("Ticket server/channel is unavailable.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Bot Owner Reply",
        description=message[:1500],
        color=0x2ECC71
    )
    embed.add_field(name="Ticket ID", value=ticket_id, inline=False)
    embed.set_footer(text="Wandering Bot Alpha - Support")
    await target_channel.send(embed=style_embed(embed))

    ticket["status"] = "replied"
    ticket["last_reply"] = str(datetime.now(UTC))
    save_support_tickets()

    await interaction.response.send_message(
        f"Reply sent to `{target_guild.name}` ticket channel.",
        ephemeral=True
    )


@bot.tree.command(name="ownerservers", description="Owner only: list bot servers")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(secret_code="Owner secret code")
async def ownerservers(interaction: discord.Interaction, secret_code: str):

    if not owner_secret_valid(interaction, secret_code):
        await reject_owner_command(interaction)
        return

    total_players = sum(len(players) for players in online_players.values())
    embed = discord.Embed(
        title="Owner Server Intelligence",
        description=f"Connected servers: {len(bot.guilds)}\nTracked online players: {total_players}",
        color=0x9B59B6
    )

    for guild in bot.guilds[:20]:
        guild_id = str(guild.id)
        config = guild_configs.get(guild_id, {})
        online_count = len(online_players.get(guild_id, set()))
        owner = guild.owner or "Unknown"
        embed.add_field(
            name=f"{guild.name} ({guild.id})",
            value=(
                f"Owner: {owner}\n"
                f"Members: {guild.member_count}\n"
                f"Online tracked: {online_count}\n"
                f"Service ID: {config.get('service_id', 'Not set')}"
            ),
            inline=False
        )

    if len(bot.guilds) > 20:
        embed.set_footer(text=f"Showing 20 of {len(bot.guilds)} servers.")

    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="ownerremovebot", description="Owner only: remove bot from a server")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(secret_code="Owner secret code", guild_id="Server ID to leave", reason="Optional reason")
async def ownerremovebot(interaction: discord.Interaction, secret_code: str, guild_id: str, reason: str = "Owner removal"):

    if not owner_secret_valid(interaction, secret_code):
        await reject_owner_command(interaction)
        return

    target_guild = bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
    if not target_guild:
        await interaction.response.send_message("Server not found.", ephemeral=True)
        return

    target_name = target_guild.name

    try:
        await target_guild.leave()
        guild_configs.pop(guild_id, None)
        save_guild_configs()
        await interaction.response.send_message(
            f"Removed bot from `{target_name}`. Reason: {reason}",
            ephemeral=True
        )
    except Exception as error:
        await interaction.response.send_message(
            f"Failed to remove bot: {error}",
            ephemeral=True
        )


async def remove_non_showcase_channels(guild, showcase_category, showcase_channel_ids):
    keep_ids = {int(channel_id) for channel_id in showcase_channel_ids}
    deleted_channels = 0
    deleted_categories = 0

    for channel in list(guild.text_channels):
        if channel.id in keep_ids:
            continue

        try:
            await channel.delete(reason="Wandering Bot showcase mode cleanup")
            deleted_channels += 1
        except Exception as error:
            print(f"SHOWCASE CLEANUP CHANNEL ERROR {guild.id}:{channel.id}: {error}")

    for category in list(guild.categories):
        if showcase_category and category.id == showcase_category.id:
            continue
        if category.channels:
            continue

        try:
            await category.delete(reason="Wandering Bot showcase mode cleanup")
            deleted_categories += 1
        except Exception as error:
            print(f"SHOWCASE CLEANUP CATEGORY ERROR {guild.id}:{category.id}: {error}")

    return deleted_channels, deleted_categories


@bot.tree.command(name="ownerbotshowcase", description="Owner only: build Wandering Bot advertising/info channels")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(secret_code="Owner secret code", invite_url="Bot invite URL to display")
async def ownerbotshowcase(interaction: discord.Interaction, secret_code: str, invite_url: str = ""):
    if not owner_secret_valid(interaction, secret_code):
        await reject_owner_command(interaction)
        return

    await interaction.response.defer(ephemeral=True)
    invite_link = bot_invite_url(invite_url)

    guild_id = str(interaction.guild.id)
    if guild_id not in guild_configs:
        guild_configs[guild_id] = {
            "guild_name": interaction.guild.name,
            "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
            "channels": {}
        }

    # Mark this guild as a showcase/advertising guild so bot behaviour adapts
    guild_configs[guild_id]["is_showcase_guild"] = True
    guild_configs[guild_id]["showcase_mode"] = True
    save_guild_configs()

    category_name = "🤖🌲┃WANDERING BOT SHOWCASE┃🌲🤖"
    category = discord.utils.get(interaction.guild.categories, name=category_name)
    if not category:
        category = await interaction.guild.create_category(category_name)

    # Showcase-specific channels: emoji-heavy advertising/info channels — no DayZ game channels
    showcase_channels = [
        "💬🤖・TALK TO THE BOT・🤖💬",
        "🎨🖼️・AI IMAGE LAB・🖼️🎨",
        "🎮✨・COMMANDS・✨🎮",
        "🤖🧠・AI MAGIC・🧠🤖",
        "⭐💫・REVIEWS & LOVE・💫⭐",
        "❓🔥・ASK ANYTHING・🔥❓",
        "🎯🚀・FEATURES GALORE・🚀🎯",
        "🌟🎉・GET STARTED NOW・🎉🌟",
        "🔗💥・INVITE ME!・💥🔗",
        "📢🎊・UPDATES & NEWS・🎊📢",
    ]

    made_channels = {}
    for channel_name in showcase_channels:
        existing = discord.utils.get(interaction.guild.text_channels, name=channel_name)
        if not existing:
            existing = await interaction.guild.create_text_channel(channel_name, category=category)
        elif existing.category != category:
            try:
                await existing.edit(category=category)
            except Exception:
                pass
        made_channels[channel_name] = existing

    showcase_config_keys = {"general_chat", "ai_chat", "help_channel", "company_announcements"}
    guild_configs[guild_id]["disabled_channels"] = [
        key for key in DEFAULT_CHANNEL_NAMES
        if key not in showcase_config_keys
    ]
    channels_cfg = guild_configs[guild_id].setdefault("channels", {})
    channels_cfg.clear()
    if "💬・talk-to-the-bot" in made_channels:
        channels_cfg["general_chat"] = made_channels["💬🤖・TALK TO THE BOT・🤖💬"].id
    if "🎨・ai-image-lab" in made_channels:
        channels_cfg["ai_chat"] = made_channels["🎨🖼️・AI IMAGE LAB・🖼️🎨"].id
    if "❓・questions-answers" in made_channels:
        channels_cfg["help_channel"] = made_channels["❓🔥・ASK ANYTHING・🔥❓"].id
    if "📢・announcements" in made_channels:
        channels_cfg["company_announcements"] = made_channels["📢🎊・UPDATES & NEWS・🎊📢"].id

    ai_settings = ai_image_config(guild_configs[guild_id])
    ai_settings["enabled"] = True
    ai_settings["style"] = "gritty"
    ai_settings["cooldown_seconds"] = 3600
    if "🎨・ai-image-lab" in made_channels:
        ai_settings["channel_id"] = made_channels["🎨🖼️・AI IMAGE LAB・🖼️🎨"].id
    save_guild_configs()

    # ── 💬・talk-to-the-bot ─────────────────────────────────────────────────
    ch = made_channels["💬🤖・TALK TO THE BOT・🤖💬"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="💬 TALK TO WANDERING BOT",
        description=(
            "This is the live demo room. Say hello, ask what I can do, ask how setup works, "
            "or ask which command does what. I answer here without needing a DayZ server connected."
        ),
        color=0xFF4FD8
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="Try Me",
        value=(
            "`hi`\n"
            "`what can you do?`\n"
            "`how do I set up the killfeed?`\n"
            "`explain the economy system`\n"
            "`can you generate an image?`"
        ),
        inline=False
    )
    embed.add_field(
        name="Showcase Mode",
        value=(
            "In this Discord I act like an autonomous host: I greet people, answer questions, "
            "drop feature suggestions, react to chat, and adapt lightly to how people talk."
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot - Live AI Demo")
    await ch.send(embed=style_embed(embed))

    # ── 🎨・ai-image-lab ────────────────────────────────────────────────────
    ch = made_channels["🎨🖼️・AI IMAGE LAB・🖼️🎨"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="🎨 AI IMAGE LAB",
        description=(
            "Ask for generated DayZ-style showcase images here. I can do cinematic, gritty, "
            "funny, survival, horror, and atmospheric prompts when image generation is configured."
        ),
        color=0x9B59B6
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="Try Asking",
        value=(
            "`make a cinematic survivor image`\n"
            "`generate a funny DayZ picture`\n"
            "`show me a gritty survival scene`"
        ),
        inline=False
    )
    embed.add_field(
        name="Note",
        value="If image generation is offline, I will still explain what needs configuring instead of sitting there silently.",
        inline=False
    )
    embed.set_footer(text="Wandering Bot - AI Art Showcase")
    await ch.send(embed=style_embed(embed))

    # ── 📖・commands-guide ──────────────────────────────────────────────────
    ch = made_channels["🎮✨・COMMANDS・✨🎮"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="📖 COMMANDS GUIDE",
        description=(
            "Every slash command Wandering Bot supports, with a plain-English explanation "
            "of what it does and when to use it."
        ),
        color=0x3498DB
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="🛠️ Server Setup",
        value=(
            "`/setup` — Connect your Nitrado server, FTP credentials, and Discord channels in one go.\n"
            "`/admstatus` — Check whether the ADM log reader is running and when it last processed events.\n"
            "`/restartadm` — Restart the ADM reader. Use `force` after initial setup.\n"
            "`/mapimagestatus` — See which map images are loaded and upload custom art.\n"
            "`/setdayzmessages` — Push custom in-game server messages to your DayZ server."
        ),
        inline=False
    )
    embed.add_field(
        name="📡 Live Feeds & Radar",
        value=(
            "`/radarstatus` — View active radar zones and their trigger settings.\n"
            "`/setradarchannel` — Choose which channel receives radar alerts.\n"
            "`/addradarzone` — Create a named coordinate zone that alerts when players enter.\n"
            "`/removeradarzone` — Delete a radar zone by ID."
        ),
        inline=False
    )
    embed.add_field(
        name="👥 Player & Community",
        value=(
            "`/linkgamer` — Link your Discord account to your in-game gamertag.\n"
            "`/mylink` — Check which gamertag your Discord is linked to.\n"
            "`/forcelinkgamer` — Admin: manually link any member to a gamertag.\n"
            "`/topkills` — Leaderboard of top PvP killers on the server.\n"
            "`/toplongshots` — Leaderboard of the longest confirmed kills."
        ),
        inline=False
    )
    embed.add_field(
        name="💰 Economy",
        value=(
            "`/wallet` — Check your penny balance.\n"
            "`/shop` — Browse and purchase items from the server shop.\n"
            "`/addreward` — Admin: reward pennies when a keyword appears in chat.\n"
            "`/addpunishment` — Admin: deduct pennies for a keyword."
        ),
        inline=False
    )
    embed.add_field(
        name="🧭 PVE & Quests",
        value=(
            "`/pveinfo` — See active PVE quests and how to complete them.\n"
            "`/pvecomplete` — Admin: mark a quest as completed for a player.\n"
            "`/pveconfig` — Admin: enable/disable PVE and set quest intervals."
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • Commands Guide")
    await ch.send(embed=style_embed(embed))
    await send_command_guide_pages(
        ch,
        title="FULL SLASH COMMAND LIST",
        intro=(
            "This live list includes every slash command currently registered by the bot, "
            "plus the options needed to use each one."
        )
    )

    # ── 🤖・ai-showcase ─────────────────────────────────────────────────────
    ch = made_channels["🤖🧠・AI MAGIC・🧠🤖"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="🤖 AI CAPABILITIES SHOWCASE",
        description=(
            "Wandering Bot is powered by an always-on AI layer that reads your server's "
            "activity and responds intelligently — no commands required."
        ),
        color=0x9B59B6
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="🧠 Contextual Chat Responses",
        value=(
            "Mention the bot or ask a question in the AI chat channel and it replies with "
            "context-aware advice — loot routes, base building tips, medical guidance, vehicle "
            "troubleshooting, and more. It reads what you actually asked, not just keywords."
        ),
        inline=False
    )
    embed.add_field(
        name="🎨 AI-Generated DayZ Art",
        value=(
            "Enable the AI image feature with `/aiimageconfig` and the bot will periodically "
            "generate original DayZ-inspired artwork and post it to your chosen channel. "
            "Styles include cinematic, funny, survival horror, and more."
        ),
        inline=False
    )
    embed.add_field(
        name="📻 Personality & Atmosphere",
        value=(
            "The bot has a distinct voice — dry, sardonic, and deeply invested in your "
            "server's survival drama. It drops in-character remarks, reacts to swearing, "
            "and keeps the atmosphere alive between events."
        ),
        inline=False
    )
    embed.add_field(
        name="🌍 Automatic Translation",
        value=(
            "Configure `/translationconfig` to automatically translate messages in any channel. "
            "Supports dozens of languages via LibreTranslate. Ideal for international communities."
        ),
        inline=False
    )
    embed.add_field(
        name="📊 Intelligent Feed Summaries",
        value=(
            "Kill feeds, raid alerts, and connection events are formatted with player names, "
            "coordinates, iZurvive map links, and distance calculations — all extracted "
            "automatically from raw ADM log data."
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • AI Showcase")
    await ch.send(embed=style_embed(embed))

    # ── ⭐・reviews ──────────────────────────────────────────────────────────
    ch = made_channels["⭐💫・REVIEWS & LOVE・💫⭐"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="⭐ REVIEWS & TESTIMONIALS",
        description=(
            "Server owners and community managers share their experience with Wandering Bot. "
            "Have feedback? Drop it here — good, bad, or brutally honest."
        ),
        color=0xF1C40F
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="How to Leave a Review",
        value=(
            "Simply post a message in this channel describing your experience. "
            "Include what you use the bot for, what works well, and anything you'd like improved. "
            "All feedback is read by the developer."
        ),
        inline=False
    )
    embed.add_field(
        name="What We're Looking For",
        value=(
            "• Which features do you use most?\n"
            "• How long have you been running the bot?\n"
            "• What has it replaced or improved in your server?\n"
            "• Anything that surprised you — positively or negatively?"
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • Reviews")
    await ch.send(embed=style_embed(embed))

    # ── ❓・questions-answers ────────────────────────────────────────────────
    ch = made_channels["❓🔥・ASK ANYTHING・🔥❓"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="❓ QUESTIONS & ANSWERS",
        description=(
            "Ask anything about Wandering Bot here. Setup questions, feature questions, "
            "troubleshooting — all welcome. The bot itself will try to help where it can."
        ),
        color=0x1ABC9C
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="Frequently Asked Questions",
        value=(
            "**Q: Does it work without Nitrado?**\n"
            "A: Core features require Nitrado API + FTP access to read ADM logs. "
            "Economy, factions, and community features work without it.\n\n"
            "**Q: How do I set up the killfeed?**\n"
            "A: Run `/setup` with your Nitrado token, service ID, and FTP credentials. "
            "The bot will create channels and start reading logs automatically.\n\n"
            "**Q: Can I use it on multiple servers?**\n"
            "A: Yes. Each Discord server gets its own isolated config, channels, and data."
        ),
        inline=False
    )
    embed.add_field(
        name="Still Stuck?",
        value=(
            "Post your question below and either the bot or a community member will respond. "
            "For urgent issues, use the support ticket system in your own server."
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • Q&A")
    await ch.send(embed=style_embed(embed))

    # ── 🎯・features ─────────────────────────────────────────────────────────
    ch = made_channels["🎯🚀・FEATURES GALORE・🚀🎯"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="🎯 FEATURE HIGHLIGHTS",
        description=(
            "What makes Wandering Bot different from every other DayZ Discord bot."
        ),
        color=0xE74C3C
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="🔥 Live ADM Intelligence",
        value=(
            "Real-time killfeed, raid detection, base building alerts, connection tracking, "
            "zombie kills, unconscious events, and more — all parsed directly from your "
            "server's ADM logs with zero manual input."
        ),
        inline=False
    )
    embed.add_field(
        name="🗺️ Interactive Heatmaps",
        value=(
            "Visual heatmaps of PvP hotspots, raid locations, building activity, and animal "
            "kills rendered on your actual server map. Supports Chernarus, Livonia, and Sakhal."
        ),
        inline=False
    )
    embed.add_field(
        name="🏴 Faction System",
        value=(
            "Full in-Discord faction management: create factions, assign leaders, manage "
            "members, set flags, and track faction activity — all without leaving Discord."
        ),
        inline=False
    )
    embed.add_field(
        name="💰 Server Economy",
        value=(
            "A complete penny-based economy with wallets, a shop, keyword rewards, "
            "punishment rules, recurring wages, and a swear jar. Fully configurable per server."
        ),
        inline=False
    )
    embed.add_field(
        name="🧭 PVE Quest System",
        value=(
            "Automated PVE challenges: hunting, fishing, crafting, collection, and expedition "
            "quests that rotate on a schedule and reward players tracked via ADM logs."
        ),
        inline=False
    )
    embed.add_field(
        name="📡 Radar Zones",
        value=(
            "Define named coordinate zones on your map. When a player enters, the bot fires "
            "an alert to your radar channel — perfect for high-value areas like NWAF or Tisy."
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • Features")
    await ch.send(embed=style_embed(embed))

    # ── 🚀・getting-started ──────────────────────────────────────────────────
    ch = made_channels["🌟🎉・GET STARTED NOW・🎉🌟"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="🚀 GETTING STARTED",
        description=(
            "From invite to live killfeed in under ten minutes. Here is exactly what to do."
        ),
        color=0x2ECC71
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="Step 1 — Invite the Bot",
        value=(
            f"Use the invite link in **#🔗💥・INVITE ME!・💥🔗** to add Wandering Bot to your server. "
            "Grant it Administrator permissions so it can create channels and manage roles."
        ),
        inline=False
    )
    embed.add_field(
        name="Step 2 — Run /setup",
        value=(
            "In your server, run `/setup` and provide:\n"
            "• Your **Nitrado API token** (from the Nitrado dashboard)\n"
            "• Your **Service ID** (the number in your Nitrado server URL)\n"
            "• Your **FTP credentials** (host, username, password)\n"
            "The bot will create all channels automatically."
        ),
        inline=False
    )
    embed.add_field(
        name="Step 3 — Upload Your Map Image",
        value=(
            "Run `/mapimagestatus` to check the current map. "
            "Upload a high-quality map image for accurate heatmap rendering."
        ),
        inline=False
    )
    embed.add_field(
        name="Step 4 — Force a First Sync",
        value=(
            "Run `/restartadm force` to kick off the first ADM log read. "
            "Within minutes your killfeed, connections, and other feeds will be live."
        ),
        inline=False
    )
    embed.add_field(
        name="Optional — Link Your Gamertag",
        value=(
            "Players can run `/linkgamer` to connect their Discord to their in-game name. "
            "This enables leaderboards, economy rewards, and personalised quest tracking."
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • Getting Started")
    await ch.send(embed=style_embed(embed))

    # ── 🔗・invite-bot ───────────────────────────────────────────────────────
    ch = made_channels["🔗💥・INVITE ME!・💥🔗"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="🔗 INVITE WANDERING BOT",
        description=(
            "Add Wandering Bot to your DayZ community server and go from zero to live "
            "killfeed, economy, factions, and AI chat in minutes."
        ),
        color=0x2ECC71
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="🚀 Bot Invite Link",
        value=f"[Click here to add Wandering Bot to your Discord](<{invite_link}>)\n{invite_link}",
        inline=False
    )
    embed.add_field(
        name="What You Get",
        value=(
            "✅ Live killfeed, raids, building, and connection alerts\n"
            "✅ Interactive heatmaps on your actual server map\n"
            "✅ Full economy system with shop and rewards\n"
            "✅ Faction management and PVE quest system\n"
            "✅ Radar zones, leaderboards, and longshot tracking\n"
            "✅ AI chat, automatic translation, and AI-generated art\n"
            "✅ Support ticket system and owner monitoring tools"
        ),
        inline=False
    )
    embed.add_field(
        name="Requirements",
        value=(
            "• A DayZ server hosted on **Nitrado** (for live feeds)\n"
            "• FTP access to your server files\n"
            "• A Discord server where you have Administrator permissions"
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • Invite")
    await ch.send(embed=style_embed(embed))

    # ── 📢・announcements ────────────────────────────────────────────────────
    ch = made_channels["📢🎊・UPDATES & NEWS・🎊📢"]
    try:
        await ch.purge(limit=20)
    except Exception:
        pass
    embed = discord.Embed(
        title="📢 BOT ANNOUNCEMENTS",
        description=(
            "Updates, new features, and important notices about Wandering Bot will be posted here. "
            "Follow this channel to stay up to date."
        ),
        color=0xE67E22
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.add_field(
        name="Currently Active",
        value=(
            f"Wandering Bot is live across **{len(bot.guilds)}** Discord servers. "
            "New features ship regularly — watch this channel for release notes."
        ),
        inline=False
    )
    embed.add_field(
        name="Recent Highlights",
        value=(
            "• AI-generated DayZ art via `/aiimageconfig`\n"
            "• Radar zone system with coordinate-based alerts\n"
            "• PVE quest system with hunting, fishing, crafting, and expedition chains\n"
            "• Custom scheduled feeds via `/addfeed`\n"
            "• Multi-language automatic translation"
        ),
        inline=False
    )
    embed.set_footer(text="Wandering Bot • Announcements")
    await ch.send(embed=style_embed(embed))

    deleted_channels, deleted_categories = await remove_non_showcase_channels(
        interaction.guild,
        category,
        [channel.id for channel in made_channels.values()]
    )
    save_guild_configs()

    await interaction.followup.send(
        "✅ Wandering Bot showcase server configured. Guild marked as `is_showcase_guild`. "
        f"Removed `{deleted_channels}` non-showcase channel(s) and `{deleted_categories}` empty category/categories. "
        "Only showcase channels are kept.",
        ephemeral=True
    )

@bot.tree.command(name="botupdates", description="Admin: create/repair the public bot updates feed")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(force_repost="Repost the full changelog backlog instead of only missing updates")
async def botupdates(interaction: discord.Interaction, force_repost: bool = False):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})

    if force_repost:
        config["posted_bot_update_ids"] = []

    set_channel_key_disabled(config, "bot_updates", False)
    sent, channel = await publish_bot_update_notes(interaction.guild, config, force=force_repost)
    if not channel:
        channel = await ensure_bot_updates_channel(interaction.guild, config, force=True)
    await interaction.followup.send(
        f"Bot updates feed is ready in {channel.mention}. Posted `{sent}` update note(s).",
        ephemeral=True
    )


@bot.tree.command(name="cheatchecksetup", description="Admin: create private PC cheat-check category and guide")
@app_commands.default_permissions(administrator=True)
async def cheatchecksetup(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    settings = cheat_check_config(config)
    settings["enabled"] = True
    channel = await ensure_cheat_check_channel(interaction.guild, config, force=True)
    await post_cheat_check_intro(channel, config)
    save_guild_configs()

    await interaction.followup.send(
        f"Private PC cheat-check feed is ready in {channel.mention}. Detection is enabled in alert-only mode.",
        ephemeral=True
    )


@bot.tree.command(name="cheatcheckconfig", description="Admin: configure PC cheat-check detection")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    enabled="Turn cheat-check detection on or off",
    auto_ban="Reserved safety switch. Alerts remain evidence-first unless a trusted DayZ ban backend is wired."
)
async def cheatcheckconfig(interaction: discord.Interaction, enabled: bool = True, auto_ban: bool = False):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    settings = cheat_check_config(config)
    settings["enabled"] = enabled
    settings["auto_ban"] = auto_ban
    save_guild_configs()

    channel = bot.get_channel(config.get("channels", {}).get("cheat_checks"))
    if channel:
        embed = discord.Embed(
            title="PC CHEAT CHECK CONFIG UPDATED",
            color=0x2ECC71 if enabled else 0x95A5A6
        )
        embed.add_field(name="Detection", value="on" if enabled else "off", inline=True)
        embed.add_field(name="Auto-ban", value="on" if auto_ban else "off", inline=True)
        embed.add_field(name="Changed By", value=f"{interaction.user.mention}\n`{interaction.user}`", inline=False)
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - Private PC Cheat Check")
        embed.timestamp = datetime.now(UTC)
        await channel.send(embed=style_embed(embed))

    await interaction.response.send_message(
        f"PC cheat-check detection is `{'on' if enabled else 'off'}`. Auto-ban setting is `{'on' if auto_ban else 'off'}`.",
        ephemeral=True
    )


@bot.tree.command(name="cheatcheckstatus", description="Admin: show PC cheat-check thresholds and mode")
@app_commands.default_permissions(administrator=True)
async def cheatcheckstatus(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    settings = cheat_check_config(config)

    embed = discord.Embed(
        title="PC CHEAT CHECK STATUS",
        color=0xE74C3C if settings.get("enabled", True) else 0x95A5A6
    )
    embed.add_field(name="Detection", value="on" if settings.get("enabled", True) else "off", inline=True)
    embed.add_field(name="Auto-ban", value="on" if settings.get("auto_ban") else "off", inline=True)
    embed.add_field(
        name="Shot Limits",
        value="\n".join(f"{weapon}: `{limit}m`" for weapon, limit in CHEAT_WEAPON_LIMITS.items()),
        inline=False
    )
    embed.add_field(
        name="Snap Chain Rules",
        value=(
            "2 kills: `<=1.5s`, `85 deg+`, `350m+`\n"
            "3 kills: `<=4s`, `60 deg+`, `250m+`\n"
            "4+ kills: `<=7s`, `40 deg+`, `175m+`"
        ),
        inline=False
    )
    channel = bot.get_channel(config.get("channels", {}).get("cheat_checks"))
    embed.add_field(name="Private Feed", value=channel.mention if channel else "Not created. Run `/cheatchecksetup`.", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="shamesetup", description="Admin: create the public Wandering in Shame moderation feed")
@app_commands.default_permissions(administrator=True)
async def shamesetup(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    channel = await ensure_public_shame_channel(interaction.guild, config, force=True)
    await interaction.response.send_message(f"Public moderation feed is ready in {channel.mention}.", ephemeral=True)


@bot.tree.command(name="adminban", description="Admin: ban a Discord member and post a public reason")
@app_commands.default_permissions(ban_members=True)
@app_commands.describe(member="Member to ban", reason="Reason shown in Wandering in Shame", delete_message_days="Delete recent message history, 0-7 days")
async def adminban(interaction: discord.Interaction, member: discord.Member, reason: str, delete_message_days: int = 0):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("You need Ban Members permission.", ephemeral=True)
        return

    if member.id == interaction.user.id or member.id == bot.user.id:
        await interaction.response.send_message("That member cannot be banned by this command.", ephemeral=True)
        return

    delete_message_days = max(0, min(7, int(delete_message_days or 0)))
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})

    await member.ban(reason=f"{reason} - banned by {interaction.user}", delete_message_days=delete_message_days)
    await send_public_shame_notice(
        interaction.guild,
        config,
        "MEMBER BANNED",
        f"{member.mention}\n`{member}`",
        interaction.user,
        reason,
        "permanent"
    )

    await interaction.response.send_message(f"Banned `{member}` and posted the reason in Wandering in Shame.", ephemeral=True)


@bot.tree.command(name="admintempban", description="Admin: temporarily ban a Discord member and post a public reason")
@app_commands.default_permissions(ban_members=True)
@app_commands.describe(member="Member to temp-ban", duration="Example: 30m, 2h, 3d, or 1d 6h", reason="Reason shown in Wandering in Shame")
async def admintempban(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("You need Ban Members permission.", ephemeral=True)
        return

    if member.id == interaction.user.id or member.id == bot.user.id:
        await interaction.response.send_message("That member cannot be banned by this command.", ephemeral=True)
        return

    seconds = parse_duration_to_seconds(duration)
    if not seconds or seconds < 60:
        await interaction.response.send_message("Duration must be at least 1 minute. Use examples like `30m`, `2h`, `3d`, or `1d 6h`.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    until_ts = datetime.now(UTC).timestamp() + seconds
    duration_text = format_duration_seconds(seconds)

    config.setdefault("temp_bans", []).append({
        "user_id": str(member.id),
        "user_name": str(member),
        "moderator_id": str(interaction.user.id),
        "reason": reason,
        "until_ts": until_ts,
        "created": str(datetime.now(UTC)),
    })
    save_guild_configs()

    await member.ban(reason=f"Temp ban {duration_text}: {reason} - banned by {interaction.user}", delete_message_days=0)
    await send_public_shame_notice(
        interaction.guild,
        config,
        "TEMP BAN ISSUED",
        f"{member.mention}\n`{member}`",
        interaction.user,
        reason,
        duration_text
    )

    await interaction.response.send_message(f"Temp-banned `{member}` for {duration_text} and posted the reason.", ephemeral=True)


@bot.tree.command(name="adminunban", description="Admin: unban a Discord user ID and post a public reason")
@app_commands.default_permissions(ban_members=True)
@app_commands.describe(user_id="Discord user ID to unban", reason="Reason shown in Wandering in Shame")
async def adminunban(interaction: discord.Interaction, user_id: str, reason: str = "Appeal accepted"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("You need Ban Members permission.", ephemeral=True)
        return

    if not str(user_id).isdigit():
        await interaction.response.send_message("User ID must be numeric.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user, reason=f"{reason} - unbanned by {interaction.user}")
    config["temp_bans"] = [
        ban for ban in config.get("temp_bans", [])
        if str(ban.get("user_id")) != str(user_id)
    ]
    save_guild_configs()

    await send_public_shame_notice(
        interaction.guild,
        config,
        "MEMBER UNBANNED",
        f"`{user}` (`{user_id}`)",
        interaction.user,
        reason,
        None
    )

    await interaction.response.send_message(f"Unbanned `{user}` and posted the reason.", ephemeral=True)


@bot.tree.command(name="translationconfig", description="Admin: configure automatic translation")
@app_commands.describe(
    mode="same posts translations in the same chat, channel forwards them, off disables translation",
    target_language="Target language code, example: en, es, fr, de",
    source_language="Source language code or auto",
    source_channel="Optional source channel. Blank means all channels.",
    target_channel="Required for channel mode"
)
@app_commands.choices(mode=[
    app_commands.Choice(name="same - translate beside the original message", value="same"),
    app_commands.Choice(name="channel - forward translations to a target channel", value="channel"),
    app_commands.Choice(name="off - disable automatic translation", value="off"),
])
async def translationconfig(
    interaction: discord.Interaction,
    mode: str = "same",
    target_language: str = "en",
    source_language: str = "auto",
    source_channel: discord.TextChannel = None,
    target_channel: discord.TextChannel = None
):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    mode = mode.lower().strip()

    if mode not in ["off", "same", "channel"]:
        await interaction.response.send_message("Mode must be `off`, `same`, or `channel`.", ephemeral=True)
        return

    if mode == "channel" and not target_channel:
        await interaction.response.send_message(
            "`channel` mode means translations are posted into another channel, so choose `target_channel`. Use `same` if you want translations posted beside the original message.",
            ephemeral=True
        )
        return

    guild_id = str(interaction.guild.id)
    if guild_id not in guild_configs:
        guild_configs[guild_id] = {
            "guild_name": interaction.guild.name,
            "admin_roles": DEFAULT_ADMIN_ROLES.copy(),
            "channels": {}
        }

    guild_configs[guild_id]["translation"] = {
        "enabled": mode != "off",
        "mode": mode,
        "target_language": target_language.lower().strip(),
        "source_language": source_language.lower().strip(),
        "source_channel_id": source_channel.id if source_channel else None,
        "target_channel_id": target_channel.id if target_channel else None
    }

    save_guild_configs()

    embed = discord.Embed(
        title="Translation Config Updated",
        description=(
            "`same` posts translations in the same chat.\n"
            "`channel` forwards translations into the target channel.\n"
            "`off` disables automatic translation."
        ),
        color=0x1ABC9C
    )
    embed.add_field(name="Mode", value=mode, inline=True)
    embed.add_field(name="Source", value=source_channel.mention if source_channel else "All channels", inline=True)
    embed.add_field(name="Target", value=target_channel.mention if target_channel else "Same channel", inline=True)
    embed.add_field(name="Language", value=f"{source_language} -> {target_language}", inline=False)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="addreward", description="Admin: reward pennies when a keyword appears in chat")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(keyword="Word or phrase to detect", amount="Pennies to add")
async def addreward(interaction: discord.Interaction, keyword: str, amount: int):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Amount must be above 0.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    rules = config.setdefault("chat_rules", [])
    rules.append({"kind": "reward", "keyword": keyword.lower().strip(), "amount": amount})
    save_guild_configs()

    await interaction.response.send_message(f"Reward rule added: `{keyword}` gives {amount} pennies.", ephemeral=True)


@bot.tree.command(name="addpunishment", description="Admin: remove pennies when a keyword appears in chat")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(keyword="Word or phrase to detect", amount="Pennies to remove")
async def addpunishment(interaction: discord.Interaction, keyword: str, amount: int):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Amount must be above 0.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    rules = config.setdefault("chat_rules", [])
    rules.append({"kind": "punishment", "keyword": keyword.lower().strip(), "amount": amount})
    save_guild_configs()

    await interaction.response.send_message(f"Punishment rule added: `{keyword}` removes {amount} pennies.", ephemeral=True)


@bot.tree.command(name="addwage", description="Admin: pay a member recurring pennies")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(member="Member to pay", amount="Pennies per payment", interval_hours="Every how many hours", reason="Reason shown in payroll")
async def addwage(interaction: discord.Interaction, member: discord.Member, amount: int, interval_hours: int, reason: str = "Server wage"):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("Amount must be above 0.", ephemeral=True)
        return

    interval_hours = max(1, min(720, int(interval_hours)))
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    wages = config.setdefault("recurring_wages", [])
    next_id = max([int(wage.get("id", 0)) for wage in wages] or [0]) + 1
    wages.append({
        "id": next_id,
        "user_id": str(member.id),
        "name": str(member),
        "amount": int(amount),
        "interval_hours": interval_hours,
        "reason": reason[:200],
        "enabled": True,
        "last_paid_ts": 0
    })
    save_guild_configs()
    await interaction.response.send_message(
        f"Wage `{next_id}` created for {member.mention}: `{amount}` pennies every `{interval_hours}` hours.",
        ephemeral=True
    )


@bot.tree.command(name="listwages", description="Admin: list recurring wages")
@app_commands.default_permissions(administrator=True)
async def listwages(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    wages = guild_configs.get(str(interaction.guild.id), {}).get("recurring_wages", [])
    if not wages:
        await interaction.response.send_message("No recurring wages configured.", ephemeral=True)
        return

    lines = [
        f"`{wage.get('id')}` {'on' if wage.get('enabled', True) else 'off'} <@{wage.get('user_id')}> - {wage.get('amount')} pennies every {wage.get('interval_hours')}h - {wage.get('reason', 'Server wage')}"
        for wage in wages[:25]
    ]
    embed = discord.Embed(title="RECURRING WAGES", description="\n".join(lines), color=0x2ECC71)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="removewage", description="Admin: remove a recurring wage")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(wage_id="Wage ID from /listwages")
async def removewage(interaction: discord.Interaction, wage_id: int):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.get(str(interaction.guild.id), {})
    wages = config.get("recurring_wages", [])
    kept = [wage for wage in wages if int(wage.get("id", 0)) != int(wage_id)]
    if len(kept) == len(wages):
        await interaction.response.send_message("Wage ID not found.", ephemeral=True)
        return

    config["recurring_wages"] = kept
    save_guild_configs()
    await interaction.response.send_message(f"Wage `{wage_id}` removed.", ephemeral=True)


@bot.tree.command(name="listrules", description="Admin: list reward and punishment rules")
@app_commands.default_permissions(administrator=True)
async def listrules(interaction: discord.Interaction):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    rules = guild_configs.get(str(interaction.guild.id), {}).get("chat_rules", [])

    if not rules:
        await interaction.response.send_message("No reward or punishment rules configured.", ephemeral=True)
        return

    lines = [
        f"{idx}. {rule.get('kind')} `{rule.get('keyword')}` - {rule.get('amount')} pennies"
        for idx, rule in enumerate(rules, start=1)
    ]

    embed = discord.Embed(
        title="Reward & Punishment Rules",
        description="\n".join(lines[:25]),
        color=0xF1C40F
    )
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="removerule", description="Admin: remove a reward/punishment rule by number")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(rule_number="Rule number from /listrules")
async def removerule(interaction: discord.Interaction, rule_number: int):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    rules = guild_configs.get(guild_id, {}).get("chat_rules", [])

    if rule_number < 1 or rule_number > len(rules):
        await interaction.response.send_message("Rule number not found.", ephemeral=True)
        return

    removed = rules.pop(rule_number - 1)
    save_guild_configs()

    await interaction.response.send_message(
        f"Removed {removed.get('kind')} rule for `{removed.get('keyword')}`.",
        ephemeral=True
    )


@bot.tree.command(name="addradarzone", description="Admin: alert when ADM activity enters a coordinate radius")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    name="Zone name",
    x="iZurvive X coordinate",
    y="iZurvive Y coordinate",
    radius="Radius in meters",
    ignored_gamertags="Optional comma-separated Xbox gamertags that should not trigger this zone"
)
async def addradarzone(
    interaction: discord.Interaction,
    name: str,
    x: float,
    y: float,
    radius: int,
    ignored_gamertags: str = ""
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    if radius < 25 or radius > 5000:
        await interaction.response.send_message("Radius must be between 25 and 5000 meters.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    zones = config.setdefault("radar_zones", [])
    next_id = (max([int(zone.get("id", 0)) for zone in zones] or [0]) + 1)
    ignored = parse_gamertag_list(ignored_gamertags)
    zones.append({
        "id": next_id,
        "name": name[:80],
        "x": float(x),
        "y": float(y),
        "radius": int(radius),
        "enabled": True,
        "cooldown_seconds": 600,
        "ignored_gamertags": ignored,
        "created_by": str(interaction.user.id)
    })
    save_guild_configs()
    radar_note = ""
    if not config.get("channels", {}).get("radar"):
        radar_note = " Set a radar channel with `/setradarchannel` or alerts have nowhere to post."
    ignore_note = f" Ignoring: `{', '.join(ignored)}`." if ignored else ""
    await interaction.response.send_message(
        f"Radar zone `{next_id}` created at `{x}, {y}` with `{radius}m` radius.{ignore_note}{radar_note}",
        ephemeral=True
    )


@bot.tree.command(name="listradarzones", description="Admin: list configured radar zones")
@app_commands.default_permissions(administrator=True)
async def listradarzones(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    zones = guild_configs.get(str(interaction.guild.id), {}).get("radar_zones", [])
    if not zones:
        await interaction.response.send_message("No radar zones configured.", ephemeral=True)
        return

    lines = []
    for zone in zones[:25]:
        ignored = radar_zone_ignored_gamertags(zone)
        ignored_text = f" - ignores: {', '.join(ignored[:8])}" if ignored else ""
        if len(ignored) > 8:
            ignored_text += f" +{len(ignored) - 8} more"
        lines.append(
            f"`{zone.get('id')}` {'on' if zone.get('enabled', True) else 'off'} **{zone.get('name')}** - {zone.get('x')}, {zone.get('y')} - {zone.get('radius')}m{ignored_text}"
        )
    embed = discord.Embed(title="RADAR ZONES", description="\n".join(lines), color=0xE74C3C)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="radarstatus", description="Admin: show radar setup and troubleshooting status")
@app_commands.default_permissions(administrator=True)
async def radarstatus(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id, {})
    channels = config.get("channels", {})
    radar_channel = interaction.guild.get_channel(channels.get("radar")) if channels.get("radar") else None
    zones = config.get("radar_zones", [])
    enabled_zones = [zone for zone in zones if zone.get("enabled", True)]

    embed = discord.Embed(
        title="RADAR STATUS",
        description=(
            "Radar checks newly processed ADM lines with coordinates. "
            "If a player was already in the latest processed lines before this fix, run `/restartadm force` once."
        ),
        color=0x3498DB
    )
    embed.add_field(
        name="Radar Channel",
        value=radar_channel.mention if radar_channel else "Not set. Use `/setradarchannel`.",
        inline=False
    )
    embed.add_field(name="Zones", value=f"{len(enabled_zones)} enabled / {len(zones)} total", inline=True)
    embed.add_field(name="ADM Loop", value="Running" if adm_loop.is_running() else "Stopped", inline=True)
    embed.add_field(
        name="Processed ADM Lines",
        value=str(len(processed_lines.get(guild_id, set()))),
        inline=True
    )

    if zones:
        zone_lines = []
        for zone in zones[:10]:
            ignored = radar_zone_ignored_gamertags(zone)
            ignore_text = f", ignores {len(ignored)}" if ignored else ""
            zone_lines.append(
                f"`{zone.get('id')}` {'on' if zone.get('enabled', True) else 'off'} {zone.get('name')} - {zone.get('x')}, {zone.get('y')} - {zone.get('radius')}m{ignore_text}"
            )
        embed.add_field(name="Zone Preview", value="\n".join(zone_lines), inline=False)

    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="addradarignore", description="Admin: add an Xbox gamertag that will not trigger a radar zone")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(zone_id="Zone ID from /listradarzones", gamertag="Exact Xbox gamertag to ignore")
async def addradarignore(interaction: discord.Interaction, zone_id: int, gamertag: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.get(str(interaction.guild.id), {})
    zones = config.get("radar_zones", [])
    zone = next((item for item in zones if int(item.get("id", 0)) == int(zone_id)), None)
    if not zone:
        await interaction.response.send_message("Radar zone not found.", ephemeral=True)
        return

    ignored = radar_zone_ignored_gamertags(zone)
    ignored_keys = {normalize_discord_name(item) for item in ignored}
    if normalize_discord_name(gamertag) not in ignored_keys:
        ignored.append(gamertag.strip())

    zone["ignored_gamertags"] = ignored
    save_guild_configs()
    await interaction.response.send_message(
        f"`{gamertag}` will no longer trigger radar zone `{zone_id}`.",
        ephemeral=True
    )


@bot.tree.command(name="removeradarignore", description="Admin: remove an ignored Xbox gamertag from a radar zone")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(zone_id="Zone ID from /listradarzones", gamertag="Xbox gamertag to remove from the ignore list")
async def removeradarignore(interaction: discord.Interaction, zone_id: int, gamertag: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.get(str(interaction.guild.id), {})
    zones = config.get("radar_zones", [])
    zone = next((item for item in zones if int(item.get("id", 0)) == int(zone_id)), None)
    if not zone:
        await interaction.response.send_message("Radar zone not found.", ephemeral=True)
        return

    wanted = normalize_discord_name(gamertag)
    ignored = [
        item for item in radar_zone_ignored_gamertags(zone)
        if normalize_discord_name(item) != wanted
    ]
    zone["ignored_gamertags"] = ignored
    save_guild_configs()
    await interaction.response.send_message(
        f"`{gamertag}` removed from radar zone `{zone_id}` ignore list.",
        ephemeral=True
    )


@bot.tree.command(name="removeradarzone", description="Admin: remove a radar zone")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(zone_id="Zone ID from /listradarzones")
async def removeradarzone(interaction: discord.Interaction, zone_id: int):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.get(str(interaction.guild.id), {})
    zones = config.get("radar_zones", [])
    kept = [zone for zone in zones if int(zone.get("id", 0)) != int(zone_id)]
    if len(kept) == len(zones):
        await interaction.response.send_message("Radar zone not found.", ephemeral=True)
        return

    config["radar_zones"] = kept
    save_guild_configs()
    await interaction.response.send_message(f"Radar zone `{zone_id}` removed.", ephemeral=True)


@bot.tree.command(name="setheatmapmode", description="Admin: choose what the heatmap tracks")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(mode="pvp, zombie, cuts, building, raids, flags, suicide, placed, pve, or all")
async def setheatmapmode(interaction: discord.Interaction, mode: str):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    mode = mode.lower().strip()

    if mode not in HEATMAP_MODES:
        await interaction.response.send_message(
            f"Mode must be one of: {', '.join(HEATMAP_MODES)}",
            ephemeral=True
        )
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    config["heatmap_mode"] = mode
    save_guild_configs()

    await interaction.response.send_message(
        f"Heatmap mode set to `{mode}`.",
        ephemeral=True
    )


@bot.tree.command(name="setservermap", description="Admin: set heatmap scaling to Chernarus, Livonia, or Sakhal")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(map_name="chernarus, livonia, or sakhal")
async def setservermap(interaction: discord.Interaction, map_name: str):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    wanted = normalize_discord_name(map_name)
    if wanted not in ["chernarus", "livonia", "enoch", "sakhal", "sakhalplus"]:
        await interaction.response.send_message(
            "Map must be `chernarus`, `livonia`, or `sakhal`.",
            ephemeral=True
        )
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    if wanted in ["livonia", "enoch"]:
        config["server_map"] = "livonia"
    elif wanted in ["sakhal", "sakhalplus"]:
        config["server_map"] = "sakhal"
    else:
        config["server_map"] = "chernarus"
    save_guild_configs()

    await interaction.response.send_message(
        f"Server map set to `{config['server_map']}`. New heatmap points will use that map scale.",
        ephemeral=True
    )


@bot.tree.command(name="setheatmapimage", description="Admin: set the real map image used behind heatmap dots")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(map_name="chernarus, livonia, sakhal, or default", image_source="Direct image URL or server file path")
async def setheatmapimage(interaction: discord.Interaction, map_name: str, image_source: str):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    wanted = normalize_map_image_key(map_name)
    if not wanted:
        await interaction.response.send_message(
            "Map must be `chernarus`, `livonia`, `sakhal`, or `default`.",
            ephemeral=True
        )
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    images = config.setdefault("heatmap_images", {})
    images[wanted] = image_source.strip()
    save_guild_configs()

    warning = ""
    if not image_source.startswith(("http://", "https://")) and not os.path.exists(image_source):
        warning = "\nWarning: that file path is not visible from this bot process, so upload the image with `/uploadmapimage` instead."

    await interaction.response.send_message(
        f"Heatmap image for `{wanted}` set. The next heatmap refresh will draw heat over that image.{warning}",
        ephemeral=True
    )


@bot.tree.command(name="uploadmapimage", description="Admin: upload the real map image for heatmaps and /map")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(map_name="chernarus, livonia, sakhal, or default", image="Map image file")
async def uploadmapimage(interaction: discord.Interaction, map_name: str, image: discord.Attachment):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    wanted = normalize_map_image_key(map_name)
    if not wanted:
        await interaction.response.send_message(
            "Map must be `chernarus`, `livonia`, `sakhal`, or `default`.",
            ephemeral=True
        )
        return

    filename = image.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    if extension not in [".png", ".jpg", ".jpeg", ".webp"]:
        await interaction.response.send_message("Please upload a PNG, JPG, JPEG, or WEBP image.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    folder = os.path.join(MAP_IMAGE_FOLDER, guild_id)
    ensure_folder(folder)
    target_path = os.path.join(folder, f"{wanted}{extension}")

    try:
        await image.save(target_path)
    except Exception as error:
        await interaction.followup.send(f"Failed to save map image: {error}", ephemeral=True)
        return

    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    images = config.setdefault("heatmap_images", {})
    images[wanted] = target_path
    save_guild_configs()

    await interaction.followup.send(
        f"Uploaded map image for `{wanted}`. Heatmaps and `/map` will use it on the next render.",
        ephemeral=True
    )


@bot.tree.command(name="mapimagestatus", description="Admin: check real map image setup for heatmaps and /map")
@app_commands.default_permissions(administrator=True)
async def mapimagestatus(interaction: discord.Interaction):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    map_key = server_map_key(guild_id)
    source, source_status = map_image_source_status(guild_id, map_key)
    heatmap_mode = guild_heatmap_mode(guild_id)
    pillow_ok, pillow_message = pillow_install_status()

    embed = discord.Embed(
        title="MAP IMAGE STATUS",
        description=source_status,
        color=0x3498DB if source and pillow_ok and (str(source).startswith(("http://", "https://")) or os.path.exists(source)) else 0xE67E22
    )
    embed.add_field(name="Server Map", value=map_key, inline=True)
    embed.add_field(name="Heatmap Mode", value=heatmap_mode, inline=True)
    embed.add_field(name="Image Renderer", value=pillow_message[:1000], inline=False)
    embed.add_field(name="Last Heatmap Render", value=heatmap_render_status(guild_id, heatmap_mode)[:1000], inline=False)
    embed.add_field(
        name="Upload Shortcut",
        value=(
            "Railway cannot use `C:\\Users\\...` paths. For public URL setup, run:\n"
            "`/setheatmapimage map_name: chernarus image_source: https://i.redd.it/a2mn8bzx93gd1.jpeg`\n"
            "`/setheatmapimage map_name: livonia image_source: https://i.imgur.com/nzEp9wF.jpeg`\n"
            "Or attach an image and type `set heatmap chernarus`, `set heatmap livonia`, or `set heatmap sakhal`."
        ),
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)

    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


async def maybe_save_map_image_from_message(message, lower):
    if not message.guild or not message.attachments:
        return False

    if not has_member_admin_power(message.author):
        return False

    if "map" not in lower and "heatmap" not in lower:
        return False

    if not any(word in lower for word in ["set", "upload", "save", "use"]):
        return False

    wanted = None
    for candidate in ["chernarus", "cherno", "livonia", "enoch", "sakhal", "sakhalplus", "default"]:
        if candidate in lower:
            wanted = normalize_map_image_key(candidate)
            break

    if not wanted:
        await message.channel.send(
            "I can save that as a map image, but tell me which one: `set heatmap chernarus`, `set heatmap livonia`, or `set heatmap sakhal`."
        )
        return True

    attachment = message.attachments[0]
    filename = attachment.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    if extension not in [".png", ".jpg", ".jpeg", ".webp"]:
        await message.channel.send("Please attach a PNG, JPG, JPEG, or WEBP map image.")
        return True

    guild_id = str(message.guild.id)
    folder = os.path.join(MAP_IMAGE_FOLDER, guild_id)
    ensure_folder(folder)
    target_path = os.path.join(folder, f"{wanted}{extension}")

    try:
        await attachment.save(target_path)
    except Exception as error:
        await message.channel.send(f"Failed to save the map image: {error}")
        return True

    config = guild_configs.setdefault(guild_id, {"guild_name": message.guild.name, "channels": {}})
    images = config.setdefault("heatmap_images", {})
    images[wanted] = target_path
    save_guild_configs()

    await message.channel.send(
        f"Saved `{wanted}` map image. Heatmaps and `/map` will use it on the next render. Run `/mapimagestatus` if you want to check it."
    )
    return True


async def send_live_map_response(interaction: discord.Interaction):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)
    ensure_guild_runtime(guild_id)

    if not online_players.get(guild_id):
        await interaction.followup.send("No online survivors are currently tracked.", ephemeral=True)
        return

    map_path, error = await asyncio.to_thread(generate_live_player_map_image, guild_id)

    if not map_path:
        await interaction.followup.send(f"Could not render live map: {error}", ephemeral=True)
        return

    online_count = len(online_players.get(guild_id, set()))
    plotted_count = sum(
        1
        for player in online_players.get(guild_id, set())
        if player_last_coords.get(guild_id, {}).get(player, {}).get("coords")
    )
    map_key = server_map_key(guild_id)
    map_name = {"livonia": "Livonia", "sakhal": "Sakhal"}.get(map_key, "Chernarus")

    embed = discord.Embed(
        title=f"LIVE SURVIVOR MAP - {map_name.upper()}",
        description=(
            f"Showing latest known ADM positions for online survivors.\n"
            f"Plotted `{plotted_count}` of `{online_count}` tracked online players."
        ),
        color=0xE74C3C
    )
    embed.set_image(url="attachment://live_player_map.png")
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Admin Live Map")

    file = discord.File(map_path, filename="live_player_map.png")
    await interaction.followup.send(embed=style_embed(embed), file=file, ephemeral=True)

    try:
        os.remove(map_path)
    except Exception:
        pass


@bot.tree.command(name="map", description="Admin: show online survivors on the server map")
@app_commands.default_permissions(administrator=True)
async def live_map(interaction: discord.Interaction):
    await send_live_map_response(interaction)


@bot.tree.command(name="livemap", description="Admin: show online survivors on the server map")
@app_commands.default_permissions(administrator=True)
async def slash_livemap_alias(interaction: discord.Interaction):
    await send_live_map_response(interaction)


@bot.tree.command(name="setdayzmessages", description="Owner: upload simple in-game rotating server messages")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    messages="Separate messages with |",
    interval_minutes="Minutes between messages",
    ftp_path="Advanced: messages.xml path on FTP"
)
async def setdayzmessages(
    interaction: discord.Interaction,
    messages: str,
    interval_minutes: int = 30,
    ftp_path: str = "/dayzxb/config/messages.xml"
):
    if interaction.user.id != interaction.guild.owner_id and not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Server owner or bot owner only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id)
    if not config:
        await interaction.followup.send("This server is not setup yet.", ephemeral=True)
        return

    message_list = [item.strip() for item in str(messages).split("|") if item.strip()]
    if not message_list:
        await interaction.followup.send("Add at least one message. Separate multiple messages with `|`.", ephemeral=True)
        return

    if len(message_list) > 20:
        await interaction.followup.send("Please keep it to 20 messages or fewer.", ephemeral=True)
        return

    interval_minutes = max(1, min(240, int(interval_minutes or 30)))
    xml_text = build_dayz_messages_xml(message_list, interval_minutes)
    config["dayz_messages"] = {
        "messages": message_list,
        "interval_minutes": interval_minutes,
        "ftp_path": ftp_path,
        "updated_at": str(datetime.now(UTC)),
        "updated_by": str(interaction.user.id)
    }
    save_guild_configs()

    success, result = await asyncio.to_thread(
        upload_text_file_to_nitrado,
        config,
        ftp_path,
        xml_text
    )

    if not success:
        await interaction.followup.send(
            f"Saved the message config, but upload failed: `{result}`\nCheck the FTP path before trying again.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="DAYZ SERVER MESSAGES UPDATED",
        description="Messages were uploaded safely as XML. They normally appear after a server restart.",
        color=0x2ECC71
    )
    embed.add_field(name="Interval", value=f"{interval_minutes} minutes", inline=True)
    embed.add_field(name="FTP Path", value=f"`{ftp_path}`", inline=False)
    embed.add_field(name="Messages", value="\n".join(f"• {item}" for item in message_list[:10])[:1000], inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


def default_init_path_for_guild(guild_id):
    map_key = server_map_key(guild_id)
    mission = {
        "livonia": "dayzOffline.enoch",
        "sakhal": "dayzOffline.sakhal",
    }.get(map_key, "dayzOffline.chernarusplus")
    return f"/dayzxb_missions/{mission}/init.c"


def map_mission_folder_names(map_key):
    if map_key == "livonia":
        return [
            "dayzOffline.enoch",
            "dayzOffline.chernarusplus",
            "dayzOffline.sakhal",
            "dayzOffline.sakhalplus",
            "dayzOffline.namalsk",
        ]
    if map_key == "sakhal":
        return [
            "dayzOffline.sakhal",
            "dayzOffline.sakhalplus",
            "dayzOffline.enoch",
            "dayzOffline.chernarusplus",
            "dayzOffline.namalsk",
        ]
    return [
        "dayzOffline.chernarusplus",
        "dayzOffline.enoch",
        "dayzOffline.sakhal",
        "dayzOffline.sakhalplus",
        "dayzOffline.namalsk",
    ]


def sort_init_paths_for_guild(guild_id, paths):
    map_key = server_map_key(guild_id)
    missions = map_mission_folder_names(map_key)
    mission_rank = {normalize_discord_name(mission): index for index, mission in enumerate(missions)}
    preferred_roots = [
        "/dayzxb_missions/",
        "/dayzxb/mpmissions/",
        "/dayzps_missions/",
        "/dayzps/mpmissions/",
        "/dayz_missions/",
        "/dayz/mpmissions/",
        "/mpmissions/",
    ]

    def path_rank(path):
        clean = canonical_remote_path(path)
        normalized = normalize_discord_name(clean)
        rank = min(
            (rank for mission, rank in mission_rank.items() if mission in normalized),
            default=len(mission_rank)
        )
        root_rank = min(
            (index for index, root in enumerate(preferred_roots) if clean.startswith(root)),
            default=len(preferred_roots)
        )
        return rank, root_rank, clean

    deduped = []
    for path in paths:
        clean = canonical_remote_path(path)
        if clean and clean not in deduped:
            deduped.append(clean)

    return sorted(deduped, key=path_rank)


def init_path_candidates_for_guild(guild_id):
    preferred = default_init_path_for_guild(guild_id)
    saved = guild_configs.get(str(guild_id), {}).get("dayz_delivery_bridge", {}).get("init_path")
    candidates = [saved, preferred]
    mission_bases = [
        "/dayzxb_missions",
        "/dayzxb/mpmissions",
        "/dayzxb_missions/mpmissions",
        "/dayzps_missions",
        "/dayzps/mpmissions",
        "/dayzps_missions/mpmissions",
        "/dayz_missions",
        "/dayz/mpmissions",
        "/dayz_missions/mpmissions",
        "/dayzserver/mpmissions",
        "/dayzxbserver/mpmissions",
        "/mpmissions",
    ]
    for mission in map_mission_folder_names(server_map_key(guild_id)):
        candidates.extend(f"{base}/{mission}/init.c" for base in mission_bases)

    deduped = []
    for candidate in candidates:
        candidate = canonical_remote_path(candidate)
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return sort_init_paths_for_guild(guild_id, deduped)


def download_init_c_with_fallback(config, guild_id, init_path=""):
    attempted = []
    candidates = []

    if init_path:
        candidate = canonical_remote_path(init_path)
        ok, message, init_text = download_text_file_from_nitrado_ftp(config, candidate, exact_only=True)
        attempted.append(f"{candidate}: {message}")
        if ok:
            return True, message, init_text, candidate, attempted

        api_ok, api_message, api_text = download_text_file_from_nitrado_api(config, candidate)
        attempted.append(f"{candidate}: {api_message}")
        if api_ok:
            return True, api_message, api_text, candidate, attempted

        return False, api_message or message, None, candidate, attempted
    else:
        for candidate in init_path_candidates_for_guild(guild_id):
            candidate = canonical_remote_path(candidate)
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        for candidate in discover_init_c_paths(config):
            candidate = canonical_remote_path(candidate)
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        candidates = sort_init_paths_for_guild(guild_id, candidates)

    last_message = ""
    for candidate in candidates:
        if not candidate:
            continue

        ok, message, init_text = download_text_file_from_nitrado(config, candidate)
        attempted.append(f"{candidate}: {message}")
        if ok:
            return True, message, init_text, candidate, attempted
        last_message = message

    return False, last_message or "No init.c path could be downloaded.", None, candidates[0] if candidates else "", attempted


async def run_bridge_blocking_io(label, func, *args, timeout_seconds=90):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        raise TimeoutError(f"{label} timed out after {timeout_seconds} seconds.")


def is_console_mission_path(path):
    normalized = str(path or "").replace("\\", "/").lower()
    return any(
        marker in normalized
        for marker in [
            "/dayzxb",
            "dayzxb_",
            "/dayzps",
            "dayzps_",
        ]
    )


def console_bridge_unavailable_embed():
    embed = discord.Embed(
        title="CONSOLE SERVER: INIT.C BRIDGE NOT AVAILABLE",
        description=(
            "Console DayZ servers do not expose an official mission `init.c` script file. "
            "That means the restart delivery bridge cannot be auto-installed or manually pasted on this server."
        ),
        color=0xE67E22
    )
    embed.add_field(
        name="What Still Works",
        value=(
            "ADM log feeds, killfeed, stats, leaderboards, heatmaps, economy balances, factions, tickets, "
            "and Discord-side rewards still work normally."
        ),
        inline=False
    )
    embed.add_field(
        name="What Uses Console XML Now",
        value=(
            "Vehicle spawns, infected events, animal events, airdrop/crate events, event positions, and crate cargo can use "
            "`/events uploadce`. The bot merges and uploads the needed XML files directly."
        ),
        inline=False
    )
    embed.add_field(
        name="What Still Needs Persistence Reset",
        value=(
            "Deleting vehicles already saved on the map or inside bases is not an XML spawn action. "
            "That needs a provider persistence reset/wipe, or a script bridge on hosts that expose `init.c`."
        ),
        inline=False
    )
    embed.add_field(
        name="Console XML/JSON Alternatives",
        value=(
            "`cfgspawnabletypes.xml` - attachments/items that spawn on guns and clothing.\n"
            "`types.xml` - core loot table: nominal/min/max, lifetime, restock, usage, value.\n"
            "`globals.xml` - core economy/game rules such as timers, weather, day/night, infected limits.\n"
            "`cfgeventspawns.xml` + `events.xml` - infected, vehicles, crashes, animal herds, and event positions.\n"
            "`cfgplayerspawn.json` - fresh spawn clothing, inventory, and starting gear."
        ),
        inline=False
    )
    embed.add_field(
        name="Next Step",
        value=(
            "Do not keep searching for `init.c` on this console package. Use `/events uploadce` to let the bot merge and upload "
            "`events.xml`, `cfgeventspawns.xml`, and `cfgspawnabletypes.xml` where needed. "
            "Only targeted delete/reset actions remain bridge-only."
        ),
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - Console Bridge Check")
    return style_embed(embed)


@bridge_group.command(name="findinitc", description="Admin: search Nitrado FTP/API for your DayZ init.c path")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(ftp_host="Optional: Nitrado FTP host/IP shown in your Nitrado file browser")
async def findinitc(interaction: discord.Interaction, ftp_host: str = ""):
    if interaction.user.id != interaction.guild.owner_id and not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Server owner or bot owner only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id)
    if not config:
        await interaction.followup.send("This server is not setup yet.", ephemeral=True)
        return

    supplied_ftp_host = normalize_ftp_host(ftp_host)
    if supplied_ftp_host:
        if not looks_like_ftp_host(supplied_ftp_host):
            await interaction.followup.send(
                "That FTP host does not look valid. Use only the host/IP shown by Nitrado, not a full URL or file path.",
                ephemeral=True
            )
            return
        config["ftp_host"] = supplied_ftp_host
        config.pop("_discovered_ftp_hosts", None)
        save_guild_configs()

    try:
        found_paths, visible_roots, diagnostic_notes = await run_bridge_blocking_io(
            "Searching for init.c",
            bridge_init_c_diagnostic,
            config,
            40,
            10,
            6,
            timeout_seconds=25
        )
    except TimeoutError:
        await interaction.followup.send(
            (
                "The init.c search timed out before Nitrado returned enough data. "
                "That usually means the FTP/API listing is hanging or very slow. "
                "Try `/installdayzbridge install:false init_path:/dayzxb_missions/dayzOffline.enoch/init.c ftp_host:"
                f"{config.get('ftp_host') or '<your Nitrado FTP host>'}` if you know the exact mission path, "
                "or use `/events bridgecode` for the manual install snippet."
            ),
            ephemeral=True
        )
        return
    found_paths = sort_init_paths_for_guild(guild_id, found_paths)

    embed = discord.Embed(
        title="INIT.C SEARCH DIAGNOSTIC",
        color=0x2ECC71 if found_paths else 0xE67E22
    )

    if found_paths:
        embed.description = "I found one or more visible `init.c` paths."
        embed.add_field(
            name="Found Path(s)",
            value="\n".join(f"`{path}`" for path in found_paths[:10])[:1000],
            inline=False
        )
        embed.add_field(
            name="Next Step",
            value=f"Run `/installdayzbridge install:true init_path:{found_paths[0]}`.",
            inline=False
        )
    else:
        embed.description = (
            "I could not find `init.c` anywhere visible through the Nitrado API or FTPS listing. "
            "That usually means this server package does not expose mission script files to the bot, "
            "or the mission folder is outside the FTP/API areas Nitrado allows this account to list."
        )
        embed.add_field(
            name="What This Means",
            value=(
                "Auto-install cannot patch the bridge unless `init.c` is visible and downloadable. "
                "Manual install also requires access to the mission `init.c` through Nitrado's file browser or another admin tool."
            ),
            inline=False
        )

    if visible_roots:
        root_lines = []
        for item in visible_roots[:8]:
            sample = ", ".join(item.get("sample", [])[:5]) or "no names returned"
            root_lines.append(f"`{item['root']}` - {item['count']} item(s): {sample}")
        embed.add_field(
            name="Visible Roots",
            value="\n".join(root_lines)[:1000],
            inline=False
        )
    else:
        embed.add_field(
            name="Visible Roots",
            value="No searched root returned a directory listing. Check FTP/API permissions, host, service ID, and server platform.",
            inline=False
        )

    if diagnostic_notes:
        embed.add_field(
            name="Connection Notes",
            value="\n".join(str(note) for note in diagnostic_notes[:4])[:1000],
            inline=False
        )

    embed.add_field(
        name="FTP Host",
        value=f"`{config.get('ftp_host')}`" if config.get("ftp_host") else "No saved host. You can pass `ftp_host:` here or run `/bridge setftphost`.",
        inline=False
    )
    embed.add_field(
        name="Roots Checked",
        value=", ".join(f"`{root}`" for root in init_search_roots(config)[:10])[:1000],
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha - DayZ Bridge Diagnostic")
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


bot.tree.add_command(bridge_group)


@bot.tree.command(name="installdayzbridge", description="Owner: install the restart delivery bridge into init.c")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    install="False checks/explains only. True backs up and patches init.c.",
    init_path="Advanced: FTP path to init.c. Leave blank for map-based default.",
    delivery_path="Advanced: FTP path for deliveries.xml",
    ftp_host="Optional: Nitrado FTP host/IP shown in your Nitrado file browser"
)
async def installdayzbridge(
    interaction: discord.Interaction,
    install: bool = False,
    init_path: str = "",
    delivery_path: str = "/dayzxb/custom/deliveries.xml",
    ftp_host: str = ""
):
    if interaction.user.id != interaction.guild.owner_id and not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Server owner or bot owner only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id)
    if not config:
        await interaction.followup.send("This server is not setup yet.", ephemeral=True)
        return

    supplied_ftp_host = normalize_ftp_host(ftp_host)
    if supplied_ftp_host:
        if not looks_like_ftp_host(supplied_ftp_host):
            await interaction.followup.send(
                "That FTP host does not look valid. Use only the host/IP shown by Nitrado, not a full URL or file path.",
                ephemeral=True
            )
            return
        config["ftp_host"] = supplied_ftp_host
        config.pop("_discovered_ftp_hosts", None)
        save_guild_configs()

    requested_init_path = (init_path or "").strip()
    if requested_init_path and is_console_mission_path(requested_init_path):
        await interaction.followup.send(embed=console_bridge_unavailable_embed(), ephemeral=True)
        return

    await interaction.followup.send(
        (
            f"Bridge install started. Downloading `init.c` from `{requested_init_path}`..."
            if requested_init_path else
            "Bridge install started. Searching for and downloading `init.c`..."
        ),
        ephemeral=True
    )
    try:
        ok, message, init_text, init_path, attempted_paths = await run_bridge_blocking_io(
            "Downloading init.c",
            download_init_c_with_fallback,
            config,
            guild_id,
            requested_init_path,
            timeout_seconds=45 if requested_init_path else 90
        )
    except TimeoutError as error:
        await interaction.followup.send(
            discord_safe_content(
                f"{error}\n\n"
                "The bot stopped waiting instead of leaving Discord stuck on thinking. "
                "Nitrado is hanging during the `init.c` download, so this bridge path is not reliable for this server right now.\n\n"
                "For console-safe events, use `/events uploadce` instead. That path edits the real XML files directly and does not need `init.c`. "
                "Only targeted hard vehicle deletion/reset still needs a script bridge or a provider persistence reset."
            ),
            ephemeral=True
        )
        return
    if not ok:
        permission_denied = (
            "Permission denied" in str(message)
            or any("Permission denied" in str(item) for item in attempted_paths)
        )
        if permission_denied:
            tried_paths = []
            for item in attempted_paths[:8]:
                path_text, _, error_text = str(item).partition(": ")
                tried_paths.append(f"`{path_text or str(item)[:220]}`")

            embed = discord.Embed(
                title="DAYZ BRIDGE NEEDS MANUAL INSTALL",
                description=(
                    "Nitrado refused the API download of `init.c` with `Permission denied`. Railway also "
                    "cannot resolve Nitrado's FTP hosts from this bot environment, so I cannot patch "
                    "`init.c` automatically from here."
                ),
                color=0xE67E22
            )
            embed.add_field(
                name="Manual Install",
                value=(
                    "1. Paste the attached bridge functions above `void main()` in your mission `init.c`.\n"
                    "2. Add `SpawnWanderingDeliveries();` inside `main()`, after weather setup or near the end.\n"
                    "3. Restart the DayZ server. Run `/events bridgecode` any time to export this again."
                ),
                inline=False
            )
            embed.add_field(
                name="Paths Checked",
                value=("\n".join(tried_paths) or "No paths were attempted.")[:1000],
                inline=False
            )
            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Alpha - Manual Bridge Fallback")
            instructions = (
                "MANUAL INSTALL\n"
                "1. Paste the bridge functions below above void main() in your mission init.c.\n"
                "2. Add this single line inside main(), after weather setup or near the end:\n"
                "   SpawnWanderingDeliveries();\n"
                "3. Upload deliveries.xml to /dayzxb/custom/deliveries.xml and restart the server.\n\n"
            )
            file = discord.File(
                io.BytesIO((instructions + WANDERING_DELIVERY_BRIDGE_CODE).encode("utf-8")),
                filename="wandering_bridge_v5_init_snippet.c"
            )
            await interaction.followup.send(embed=style_embed(embed), file=file, ephemeral=True)
            return

        if requested_init_path:
            tried_lines = []
            seen_tried = set()
            for item in attempted_paths[:8]:
                path_text, _, error_text = str(item).partition(": ")
                line_key = (path_text, error_text[:220])
                if line_key in seen_tried:
                    continue
                seen_tried.add(line_key)
                if error_text:
                    tried_lines.append(f"`{path_text}`: {error_text[:260]}")
                else:
                    tried_lines.append(f"`{str(item)[:280]}`")

            embed = discord.Embed(
                title="EXACT INIT.C DOWNLOAD FAILED",
                description=(
                    "I tried the exact `init.c` path you supplied and could not download it through Nitrado API or FTPS. "
                    "I am skipping the deeper search because Nitrado listing is timing out for this account."
                ),
                color=0xE67E22
            )
            embed.add_field(name="Requested Path", value=f"`{canonical_remote_path(requested_init_path)}`", inline=False)
            embed.add_field(name="FTP Host", value=f"`{config.get('ftp_host')}`" if config.get("ftp_host") else "No saved host.", inline=False)
            embed.add_field(
                name="Download Attempts",
                value=("\n".join(tried_lines) or f"`{canonical_remote_path(requested_init_path)}` failed.")[:1000],
                inline=False
            )
            embed.add_field(
                name="What This Means",
                value=(
                    "The bot cannot auto-patch the bridge unless the mission `init.c` is downloadable by this Nitrado account. "
                    "Use `/events uploadce` for console-safe XML events. Use `/events bridgecode` only if you can edit `init.c` manually "
                    "and specifically need bridge-only hard reset/delete behavior."
                ),
                inline=False
            )
            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Alpha - Manual Bridge Fallback")
            await interaction.followup.send(embed=style_embed(embed), ephemeral=True)
            return

        network_error = (
            "Could not resolve any Nitrado FTP host" in str(message)
            or "Could not connect to Nitrado FTP" in str(message)
        )
        try:
            found_paths, visible_roots, diagnostic_notes = await run_bridge_blocking_io(
                "Running init.c diagnostic",
                bridge_init_c_diagnostic,
                config,
                timeout_seconds=45
            )
            found_paths = sort_init_paths_for_guild(guild_id, found_paths)
        except TimeoutError:
            found_paths, visible_roots, diagnostic_notes = [], [], ["The deeper init.c diagnostic timed out."]

        embed = discord.Embed(title="INIT.C NOT FOUND", color=0xE67E22)
        if network_error:
            embed.description = (
                "The bot could not connect to Nitrado FTPS from this host. "
                "Pass the exact FTP host/IP shown in Nitrado with `ftp_host:` or save it with `/bridge setftphost`."
            )
        elif found_paths:
            embed.description = "The first download failed, but the deeper search found possible `init.c` path(s)."
            embed.add_field(
                name="Found Path(s)",
                value="\n".join(f"`{path}`" for path in found_paths[:8])[:1000],
                inline=False
            )
            embed.add_field(
                name="Next Step",
                value=f"Run `/installdayzbridge install:true init_path:{found_paths[0]}`.",
                inline=False
            )
        else:
            embed.description = (
                "I checked the normal mission paths and then ran the deeper FTP/API search. "
                "`init.c` is not visible to this bot account."
            )
            embed.add_field(
                name="What This Means",
                value=(
                    "Auto-install cannot patch the bridge unless Nitrado exposes your mission `init.c`. "
                    "Some server packages do not expose mission script files through FTP/API."
                ),
                inline=False
            )

        ftp_host_text = (
            f"`{config.get('ftp_host')}`"
            if config.get("ftp_host")
            else "No saved host. Use `/bridge setftphost ftp_host:<host>` or pass `ftp_host:` to `/installdayzbridge`."
        )
        embed.add_field(name="FTP Host", value=ftp_host_text, inline=False)

        if visible_roots:
            root_lines = []
            for item in visible_roots[:6]:
                sample = ", ".join(item.get("sample", [])[:4]) or "no names returned"
                root_lines.append(f"`{item['root']}` - {item['count']} item(s): {sample}")
            embed.add_field(name="Visible Roots", value="\n".join(root_lines)[:1000], inline=False)
        else:
            embed.add_field(
                name="Visible Roots",
                value="No searched root returned a useful directory listing.",
                inline=False
            )

        if diagnostic_notes:
            embed.add_field(
                name="Connection Notes",
                value="\n".join(str(note) for note in diagnostic_notes[:4])[:1000],
                inline=False
            )

        path_lines = []
        for item in attempted_paths[:8]:
            path_text, _, _ = str(item).partition(": ")
            if path_text:
                path_lines.append(f"`{path_text}`")
        embed.add_field(
            name="Fallback Paths Tried",
            value=("\n".join(path_lines) or "No fallback paths were attempted.")[:1000],
            inline=False
        )
        embed.add_field(
            name="Manual Option",
            value=(
                "Run `/events uploadce` for the bridge-free XML route. Run `/events bridgecode` only if you can edit `init.c` manually "
                "and need bridge-only hard reset/delete behavior."
            ),
            inline=False
        )
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.set_footer(text="Wandering Bot Alpha - DayZ Bridge Diagnostic")
        await interaction.followup.send(embed=style_embed(embed), ephemeral=True)
        return
        hint = (
            "\n\nThis is a DNS/network problem in the bot host. Pass the exact Nitrado FTP host/IP with "
            "`ftp_host:` or save it with `/bridge setftphost`, then try again. If that still fails, check that "
            "the host running the bot can make outbound FTPS/DNS connections."
            if network_error else
            "\n\nRun `/bridge findinitc ftp_host:<your Nitrado FTP host>` to search every visible Nitrado FTP/API root for the real mission path. "
            "If it finds a path, rerun `/installdayzbridge install:true init_path:<that path>`."
        )
        tried_lines = []
        for item in attempted_paths[:8]:
            path_text, _, error_text = str(item).partition(": ")
            if error_text:
                tried_lines.append(f"- `{path_text}`: {error_text[:220]}")
            else:
                tried_lines.append(f"- `{str(item)[:260]}`")
        attempted_paths = tried_lines

        await interaction.followup.send(
            discord_safe_content(f"Could not download `init.c`. Last error: `{str(message)[:600]}`\n\n"
            "Tried:\n"
            + "\n".join(f"• `{item}`" for item in attempted_paths[:8])
            + hint),
            ephemeral=True
        )
        return

    await interaction.followup.send(
        f"Downloaded `init.c` from `{init_path}`. Checking whether the bridge hook is already installed...",
        ephemeral=True
    )

    updated_text, changed, install_error = install_wandering_delivery_bridge(init_text)
    if install_error:
        await interaction.followup.send(discord_safe_content(install_error), ephemeral=True)
        return

    if not install:
        embed = discord.Embed(
            title="DAYZ DELIVERY BRIDGE CHECK",
            description=(
                "Shop deliveries and vehicle reset/rental spawns need a small restart hook in `init.c`.\n\n"
                "I found your `init.c` and checked what would be needed. Nothing was changed."
            ),
            color=0x3498DB
        )
        embed.add_field(name="Detected init.c Path", value=f"`{init_path}`", inline=False)
        if not requested_init_path:
            embed.add_field(
                name="Path Search",
                value=f"Auto-detected after trying `{len(attempted_paths)}` path(s).",
                inline=True
            )
        embed.add_field(name="Delivery XML Path", value=f"`{delivery_path}`", inline=False)
        embed.add_field(
            name="Status",
            value=(
                "Bridge already appears installed." if not changed else
                "Bridge is not installed yet. Run this command again with `install:true` if you want the bot to back up and patch `init.c`."
            ),
            inline=False
        )
        embed.add_field(
            name="What install:true does",
            value=(
                "1. Downloads `init.c` from FTP.\n"
                "2. Uploads a timestamped backup next to it.\n"
                "3. Adds `SpawnWanderingDeliveries()` only if missing.\n"
                "4. Adds `SpawnWanderingDeliveries();` only if missing.\n"
                "5. Uploads a starter `deliveries.xml`."
            ),
            inline=False
        )
        embed.set_thumbnail(url=BOT_IMAGE)
        await interaction.followup.send(embed=style_embed(embed), ephemeral=True)
        return

    backup_path = f"{init_path}.wandering-backup-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    await interaction.followup.send(f"Creating backup at `{backup_path}`...", ephemeral=True)
    try:
        backup_ok, backup_message = await run_bridge_blocking_io(
            "Creating init.c backup",
            upload_text_file_to_nitrado,
            config,
            backup_path,
            init_text,
            timeout_seconds=90
        )
    except TimeoutError as error:
        await interaction.followup.send(
            discord_safe_content(f"{error}\n\nBackup did not finish, so I did not touch `init.c`."),
            ephemeral=True
        )
        return

    if not backup_ok:
        await interaction.followup.send(
            discord_safe_content(f"Backup failed, so I did not touch init.c: `{backup_message}`"),
            ephemeral=True
        )
        return

    if changed:
        await interaction.followup.send("Backup created. Uploading patched `init.c`...", ephemeral=True)
        try:
            upload_ok, upload_message = await run_bridge_blocking_io(
                "Uploading patched init.c",
                upload_text_file_to_nitrado,
                config,
                init_path,
                updated_text,
                timeout_seconds=90
            )
        except TimeoutError as error:
            await interaction.followup.send(
                discord_safe_content(f"{error}\n\nBackup was created at `{backup_path}`, but patched `init.c` did not finish uploading."),
                ephemeral=True
            )
            return

        if not upload_ok:
            await interaction.followup.send(
                discord_safe_content(f"Backup was created at `{backup_path}`, but init.c upload failed: `{upload_message}`"),
                ephemeral=True
            )
            return
        await interaction.followup.send("Patched `init.c` uploaded. Uploading starter `deliveries.xml`...", ephemeral=True)
    else:
        await interaction.followup.send("Bridge hook is already installed. Uploading starter `deliveries.xml`...", ephemeral=True)

    starter_xml = "<objects>\n</objects>\n"
    try:
        delivery_ok, delivery_message = await run_bridge_blocking_io(
            "Uploading starter deliveries.xml",
            upload_text_file_to_nitrado,
            config,
            delivery_path,
            starter_xml,
            timeout_seconds=90
        )
    except TimeoutError as error:
        delivery_ok = False
        delivery_message = str(error)

    config["dayz_delivery_bridge"] = {
        "init_path": init_path,
        "delivery_path": delivery_path,
        "backup_path": backup_path,
        "installed_at": str(datetime.now(UTC)),
        "installed_by": str(interaction.user.id),
        "changed_init": changed,
        "starter_delivery_uploaded": delivery_ok,
    }
    save_guild_configs()

    embed = discord.Embed(
        title="DAYZ DELIVERY BRIDGE INSTALLED",
        description=(
            "The bot backed up `init.c`, installed the restart delivery hook if needed, "
            "and uploaded a starter `deliveries.xml`. Restart the server before expecting deliveries to spawn."
        ),
        color=0x2ECC71
    )
    embed.add_field(name="init.c", value=f"`{init_path}`", inline=False)
    embed.add_field(name="Backup", value=f"`{backup_path}`", inline=False)
    embed.add_field(name="Delivery XML", value=f"`{delivery_path}`", inline=False)
    embed.add_field(name="Changed init.c", value="Yes" if changed else "Already installed", inline=True)
    embed.add_field(name="Starter XML", value="Uploaded" if delivery_ok else f"Failed: {delivery_message}", inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


events_group = app_commands.Group(
    name="events",
    description="Owner tools for restart-based DayZ scenario events"
)

SCENARIO_LOOT_PRESET_OPTIONS = [
    ("None - empty crate", "none"),
    ("Military - balanced weapons/ammo/meds", "military"),
    ("Military high tier - rare weapons/armor/NVG", "military_high"),
    ("Medical - meds and healing supplies", "medical"),
    ("Survival - food, knife, water, basics", "survival"),
    ("Building - nails and base tools", "building"),
    ("Food - canned food and drinks", "food"),
]

SCENARIO_CRATE_CLASS_OPTIONS = [
    ("Wooden crate - default stash crate", "WoodenCrate"),
    ("Sea chest - large storage chest", "SeaChest"),
    ("Barrel green - persistent barrel", "Barrel_Green"),
    ("Barrel blue - persistent barrel", "Barrel_Blue"),
    ("Barrel red - persistent barrel", "Barrel_Red"),
    ("Protector case - small waterproof case", "SmallProtectorCase"),
    ("First aid kit - medical themed box", "FirstAidKit"),
    ("Ammo box - military themed container", "AmmoBox"),
]


def autocomplete_matches(options, current):
    try:
        current_key = normalize_discord_name(current)
        matches = []
        for label, value in options:
            label = str(label or "").strip()
            value = str(value or "").strip()
            if not label or not value:
                continue
            if current_key and current_key not in normalize_discord_name(label) and current_key not in normalize_discord_name(value):
                continue
            matches.append(app_commands.Choice(name=label[:100], value=value[:100]))
            if len(matches) >= 25:
                break
        return matches
    except Exception as error:
        print(f"EVENT AUTOCOMPLETE ERROR: {error}")
        return []


async def scenario_location_autocomplete(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    map_key = server_map_key(guild_id) if guild_id else "chernarus"
    options = [
        (location.get("name", key), key)
        for key, location in scenario_location_presets_for_map(map_key).items()
    ]
    return autocomplete_matches(options, current)


async def scenario_spawn_autocomplete(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    map_key = server_map_key(guild_id) if guild_id else "chernarus"
    event_type = getattr(interaction.namespace, "event_type", None)
    return autocomplete_matches(scenario_spawn_preset_options(map_key, event_type), current)


async def scenario_loot_autocomplete(interaction: discord.Interaction, current: str):
    return autocomplete_matches(SCENARIO_LOOT_PRESET_OPTIONS, current)


async def scenario_crate_autocomplete(interaction: discord.Interaction, current: str):
    options = list(SCENARIO_CRATE_CLASS_OPTIONS)
    try:
        guild_id = str(interaction.guild.id) if interaction.guild else ""
        map_key = server_map_key(guild_id) if guild_id else "chernarus"
        reference = load_dayz_reference(map_key)
        for class_name in reference.get("containers", [])[:40]:
            options.append((class_name.replace("_", " "), class_name))
    except Exception as error:
        print(f"CRATE AUTOCOMPLETE REFERENCE ERROR: {error}")
    return autocomplete_matches(options, current)


async def scenario_vehicle_autocomplete(interaction: discord.Interaction, current: str):
    return autocomplete_matches(scenario_vehicle_preset_options(), current)


async def scenario_guard_autocomplete(interaction: discord.Interaction, current: str):
    return autocomplete_matches(scenario_guard_preset_options(), current)


async def scenario_zombie_autocomplete(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    map_key = server_map_key(guild_id) if guild_id else "chernarus"
    return autocomplete_matches(scenario_spawn_preset_options(map_key, "zombie_horde"), current)


async def scenario_animal_autocomplete(interaction: discord.Interaction, current: str):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    map_key = server_map_key(guild_id) if guild_id else "chernarus"
    return autocomplete_matches(scenario_spawn_preset_options(map_key, "animal_pack"), current)


@events_group.command(name="create", description="Admin: create a restart scenario event")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    event_type="What kind of scenario to create",
    location="Preset location or custom coordinates",
    spawn_preset="Specific zombie, animal, crate, or custom classname",
    count="How many to spawn. Crates usually use 1.",
    radius="Spread spawns around the location in metres",
    permanent="True keeps spawning every restart. False is one restart only.",
    loot_preset="Loot to put inside crates/airdrops where possible",
    custom_class="Required only if spawn_preset is custom",
    x="Custom X coordinate if location is custom",
    z="Custom Z coordinate if location is custom",
    y="Optional height coordinate"
)
@app_commands.choices(
    event_type=[
        app_commands.Choice(name="Zombie horde", value="zombie_horde"),
        app_commands.Choice(name="Animal pack", value="animal_pack"),
        app_commands.Choice(name="Loot crate", value="loot_crate"),
        app_commands.Choice(name="Airdrop crate", value="airdrop"),
        app_commands.Choice(name="Custom class spawn", value="custom_spawn"),
    ],
    loot_preset=[
        app_commands.Choice(name=label, value=value)
        for label, value in SCENARIO_LOOT_PRESET_OPTIONS
    ]
)
@app_commands.autocomplete(
    location=scenario_location_autocomplete,
    spawn_preset=scenario_spawn_autocomplete,
)
async def event_create(
    interaction: discord.Interaction,
    event_type: str,
    location: str,
    spawn_preset: str,
    count: int,
    radius: int = 25,
    permanent: bool = False,
    loot_preset: str = "none",
    custom_class: str = "",
    x: str = "",
    z: str = "",
    y: str = "0",
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    map_key = server_map_key(guild_id)
    location_data, location_error = scenario_location_from_choice(location, x, z, y, map_key)
    if location_error:
        await interaction.followup.send(location_error, ephemeral=True)
        return

    preset = resolve_scenario_spawn_preset(map_key, spawn_preset, custom_class)
    class_name = (custom_class or "").strip() if spawn_preset == "custom" else preset.get("class", "")
    if not class_name:
        await interaction.followup.send("Choose a preset or provide `custom_class`.", ephemeral=True)
        return

    chosen_event_type = event_type
    preset_type = preset.get("event_type")
    if spawn_preset != "custom":
        compatible = (
            preset_type == chosen_event_type
            or (chosen_event_type == "airdrop" and preset_type == "loot_crate")
        )
        if not compatible:
            await interaction.followup.send(
                f"`{preset.get('label', spawn_preset)}` does not match `{event_type}`. "
                "Pick a matching preset or use `spawn_preset:Custom classname`.",
                ephemeral=True
            )
            return

    count = max(1, min(250, int(count or 1)))
    radius = max(0, min(2000, int(radius or 0)))
    if chosen_event_type in {"loot_crate", "airdrop"} and count > 20:
        count = 20

    loot_key = loot_preset or "none"
    if spawn_preset in {"military_crate"} and loot_key == "none":
        loot_key = "military"
    elif spawn_preset in {"medical_crate"} and loot_key == "none":
        loot_key = "medical"
    elif spawn_preset in {"survival_crate"} and loot_key == "none":
        loot_key = "survival"
    elif spawn_preset in {"building_crate"} and loot_key == "none":
        loot_key = "building"

    events = scenario_events_for_config(config)
    event_id = next_scenario_event_id(config)
    event_record = {
        "id": event_id,
        "name": f"{preset.get('label', class_name)} at {location_data['name']}",
        "event_type": chosen_event_type,
        "location": location_data["name"],
        "x": location_data["x"],
        "y": location_data["y"],
        "z": location_data["z"],
        "class_name": class_name,
        "preset": spawn_preset,
        "map": map_key,
        "count": count,
        "radius": radius,
        "loot_preset": loot_key,
        "loot": SCENARIO_LOOT_PRESETS.get(loot_key, []),
        **restart_count_fields(0 if permanent else 1),
        "enabled": True,
        "created_by": str(interaction.user.id),
        "created_at": str(datetime.now(UTC)),
    }
    events.append(event_record)
    save_guild_configs()

    upload_success, upload_status = await auto_push_scenario_events_xml(guild_id, config)

    embed = discord.Embed(
        title="SCENARIO EVENT CREATED",
        description=upload_status,
        color=0x2ECC71 if upload_success else 0xE74C3C
    )
    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
    embed.add_field(name="Mode", value=scenario_event_mode_text(event_record), inline=True)
    embed.add_field(name="Class", value=f"`{class_name}`", inline=False)
    embed.add_field(name="Count / Spread", value=f"`{count}` within `{radius}m`", inline=True)
    embed.add_field(name="Location", value=f"{location_data['name']}\n`{location_data['x']} {location_data['y']} {location_data['z']}`", inline=False)
    embed.add_field(name="Loot", value=f"`{loot_key}`" if event_record["loot"] else "None", inline=True)
    embed.add_field(
        name="Controls",
        value="Use `/events list`, `/events disable`, `/events enable`, or `/events delete`.",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@events_group.command(name="horde", description="Admin: create a zombie horde event for one or more restarts")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    location="Preset location or custom coordinates",
    zombie_preset="Zombie/infected class to spawn",
    count="How many infected to spawn",
    radius="Spread around the location in metres",
    restarts="How many restarts to run. Use 0 for forever.",
    custom_class="Required only if zombie_preset is custom",
    x="Custom X coordinate if location is custom",
    z="Custom Z coordinate if location is custom",
    y="Optional height coordinate"
)
@app_commands.autocomplete(
    location=scenario_location_autocomplete,
    zombie_preset=scenario_zombie_autocomplete,
)
async def event_horde(
    interaction: discord.Interaction,
    location: str,
    zombie_preset: str,
    count: int,
    radius: int = 45,
    restarts: int = 1,
    custom_class: str = "",
    x: str = "",
    z: str = "",
    y: str = "0",
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    map_key = server_map_key(guild_id)
    location_data, location_error = scenario_location_from_choice(location, x, z, y, map_key)
    if location_error:
        await interaction.followup.send(location_error, ephemeral=True)
        return

    preset = resolve_scenario_spawn_preset(map_key, zombie_preset, custom_class)
    class_name = (custom_class or "").strip() if zombie_preset == "custom" else preset.get("class", "")
    if not class_name:
        await interaction.followup.send("Choose a zombie preset or provide `custom_class`.", ephemeral=True)
        return

    if preset.get("event_type") != "zombie_horde" and zombie_preset != "custom":
        await interaction.followup.send("That preset is not a zombie/infected class.", ephemeral=True)
        return

    count = max(1, min(250, int(count or 1)))
    radius = max(0, min(2000, int(radius or 0)))
    event_id = next_scenario_event_id(config)
    event_record = {
        "id": event_id,
        "name": f"{preset.get('label', class_name)} horde at {location_data['name']}",
        "event_type": "zombie_horde",
        "location": location_data["name"],
        "x": location_data["x"],
        "y": location_data["y"],
        "z": location_data["z"],
        "class_name": class_name,
        "preset": zombie_preset,
        "map": map_key,
        "count": count,
        "radius": radius,
        "loot_preset": "none",
        "loot": [],
        **restart_count_fields(restarts),
        "enabled": True,
        "created_by": str(interaction.user.id),
        "created_at": str(datetime.now(UTC)),
    }
    scenario_events_for_config(config).append(event_record)
    save_guild_configs()

    upload_success, upload_status = await auto_push_scenario_events_xml(guild_id, config)

    embed = discord.Embed(
        title="HORDE EVENT CREATED",
        description=upload_status,
        color=0x2ECC71 if upload_success else 0xE74C3C
    )
    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
    embed.add_field(name="Runs", value=scenario_event_mode_text(event_record), inline=True)
    embed.add_field(name="Zombie Class", value=f"`{class_name}`", inline=False)
    embed.add_field(name="Count / Spread", value=f"`{count}` within `{radius}m`", inline=True)
    embed.add_field(name="Location", value=f"{location_data['name']}\n`{location_data['x']} {location_data['y']} {location_data['z']}`", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@events_group.command(name="animals", description="Admin: create an animal pack event for one or more restarts")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    location="Preset location or custom coordinates",
    animal_preset="Animal class to spawn",
    count="How many animals to spawn",
    radius="Spread around the location in metres",
    restarts="How many restarts to run. Use 0 for forever.",
    custom_class="Required only if animal_preset is custom",
    x="Custom X coordinate if location is custom",
    z="Custom Z coordinate if location is custom",
    y="Optional height coordinate"
)
@app_commands.autocomplete(
    location=scenario_location_autocomplete,
    animal_preset=scenario_animal_autocomplete,
)
async def event_animals(
    interaction: discord.Interaction,
    location: str,
    animal_preset: str,
    count: int,
    radius: int = 75,
    restarts: int = 1,
    custom_class: str = "",
    x: str = "",
    z: str = "",
    y: str = "0",
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    map_key = server_map_key(guild_id)
    location_data, location_error = scenario_location_from_choice(location, x, z, y, map_key)
    if location_error:
        await interaction.followup.send(location_error, ephemeral=True)
        return

    preset = resolve_scenario_spawn_preset(map_key, animal_preset, custom_class)
    class_name = (custom_class or "").strip() if animal_preset == "custom" else preset.get("class", "")
    if not class_name:
        await interaction.followup.send("Choose an animal preset or provide `custom_class`.", ephemeral=True)
        return

    if preset.get("event_type") != "animal_pack" and animal_preset != "custom":
        await interaction.followup.send("That preset is not an animal class.", ephemeral=True)
        return

    count = max(1, min(120, int(count or 1)))
    radius = max(0, min(2000, int(radius or 0)))
    event_id = next_scenario_event_id(config)
    event_record = {
        "id": event_id,
        "name": f"{preset.get('label', class_name)} pack at {location_data['name']}",
        "event_type": "animal_pack",
        "location": location_data["name"],
        "x": location_data["x"],
        "y": location_data["y"],
        "z": location_data["z"],
        "class_name": class_name,
        "preset": animal_preset,
        "map": map_key,
        "count": count,
        "radius": radius,
        "loot_preset": "none",
        "loot": [],
        **restart_count_fields(restarts),
        "enabled": True,
        "created_by": str(interaction.user.id),
        "created_at": str(datetime.now(UTC)),
    }
    scenario_events_for_config(config).append(event_record)
    save_guild_configs()

    upload_success, upload_status = await auto_push_scenario_events_xml(guild_id, config)

    embed = discord.Embed(
        title="ANIMAL PACK EVENT CREATED",
        description=upload_status,
        color=0x2ECC71 if upload_success else 0xE74C3C
    )
    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
    embed.add_field(name="Runs", value=scenario_event_mode_text(event_record), inline=True)
    embed.add_field(name="Animal Class", value=f"`{class_name}`", inline=False)
    embed.add_field(name="Count / Spread", value=f"`{count}` within `{radius}m`", inline=True)
    embed.add_field(name="Location", value=f"{location_data['name']}\n`{location_data['x']} {location_data['y']} {location_data['z']}`", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@events_group.command(name="vehicle", description="Admin: create a one-time or recurring vehicle spawn event")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    location="Preset location or custom coordinates",
    vehicle_preset="Vehicle to spawn",
    condition="Whether the vehicle spawns full or without parts",
    restarts="How many restarts to run. Use 0 for forever.",
    permanent="Legacy override: true means forever",
    custom_class="Required only if vehicle_preset is custom",
    x="Custom X coordinate if location is custom",
    z="Custom Z coordinate if location is custom",
    y="Optional height coordinate"
)
@app_commands.choices(condition=[
    app_commands.Choice(name="Full vehicle", value="full"),
    app_commands.Choice(name="Without parts", value="no_parts"),
    app_commands.Choice(name="Random common parts", value="random_parts"),
])
@app_commands.autocomplete(
    location=scenario_location_autocomplete,
    vehicle_preset=scenario_vehicle_autocomplete,
)
async def event_vehicle(
    interaction: discord.Interaction,
    location: str,
    vehicle_preset: str,
    condition: str = "full",
    restarts: int = 1,
    permanent: bool = False,
    custom_class: str = "",
    x: str = "",
    z: str = "",
    y: str = "0",
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    map_key = server_map_key(guild_id)
    location_data, location_error = scenario_location_from_choice(location, x, z, y, map_key)
    if location_error:
        await interaction.followup.send(location_error, ephemeral=True)
        return

    preset = resolve_scenario_vehicle_preset(vehicle_preset, custom_class)
    class_name = str(preset.get("class") or "").strip()
    if not class_name:
        await interaction.followup.send("Choose a vehicle preset or provide `custom_class`.", ephemeral=True)
        return

    condition = condition if condition in SCENARIO_VEHICLE_CONDITIONS else "full"
    events = scenario_events_for_config(config)
    event_id = next_scenario_event_id(config)
    event_record = {
        "id": event_id,
        "name": f"{preset.get('label', class_name)} vehicle at {location_data['name']}",
        "event_type": "vehicle_spawn",
        "location": location_data["name"],
        "x": location_data["x"],
        "y": location_data["y"],
        "z": location_data["z"],
        "class_name": class_name,
        "preset": vehicle_preset,
        "map": map_key,
        "count": 1,
        "radius": 0,
        "loot_preset": "none",
        "loot": [],
        "vehicle_condition": condition,
        **restart_count_fields(0 if permanent else restarts),
        "enabled": True,
        "created_by": str(interaction.user.id),
        "created_at": str(datetime.now(UTC)),
    }
    events.append(event_record)
    save_guild_configs()

    upload_success, upload_status = await auto_push_scenario_events_xml(guild_id, config)

    embed = discord.Embed(
        title="VEHICLE EVENT CREATED",
        description=upload_status,
        color=0x2ECC71 if upload_success else 0xE74C3C
    )
    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
    embed.add_field(name="Runs", value=scenario_event_mode_text(event_record), inline=True)
    embed.add_field(name="Vehicle", value=f"`{class_name}`", inline=False)
    embed.add_field(name="Condition", value=SCENARIO_VEHICLE_CONDITIONS[condition], inline=False)
    embed.add_field(name="Location", value=f"{location_data['name']}\n`{location_data['x']} {location_data['y']} {location_data['z']}`", inline=False)
    embed.add_field(name="Controls", value="Use `/events list`, `/events disable`, `/events enable`, or `/events delete`.", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@events_group.command(name="airdrop", description="Admin: create a one-time or recurring airdrop crate event")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    location="Preset location or custom coordinates",
    loot_preset="Pick what the crate should contain. This patches cfgspawnabletypes.xml on uploadce.",
    restarts="How many restarts to run. Use 0 for forever.",
    permanent="Legacy override: true means forever",
    visual_marker="Spawn a crash/debris marker object beside the crate",
    zombie_guards="Spawn infected guards around the airdrop",
    guard_preset="Guard infected type",
    guard_count="How many guards to spawn",
    guard_radius="Guard spread around the airdrop in metres",
    crate_class="Container to spawn. WoodenCrate is safest unless you know another classname.",
    custom_guard_class="Required only if guard_preset is custom",
    x="Custom X coordinate if location is custom",
    z="Custom Z coordinate if location is custom",
    y="Optional height coordinate"
)
@app_commands.choices(loot_preset=[
    app_commands.Choice(name=label, value=value)
    for label, value in SCENARIO_LOOT_PRESET_OPTIONS
])
@app_commands.autocomplete(
    location=scenario_location_autocomplete,
    guard_preset=scenario_guard_autocomplete,
    crate_class=scenario_crate_autocomplete,
)
async def event_airdrop(
    interaction: discord.Interaction,
    location: str,
    loot_preset: str = "military_high",
    restarts: int = 1,
    permanent: bool = False,
    visual_marker: bool = True,
    zombie_guards: bool = True,
    guard_preset: str = "military_zombie",
    guard_count: int = 8,
    guard_radius: int = 35,
    crate_class: str = "WoodenCrate",
    custom_guard_class: str = "",
    x: str = "",
    z: str = "",
    y: str = "0",
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    map_key = server_map_key(guild_id)
    location_data, location_error = scenario_location_from_choice(location, x, z, y, map_key)
    if location_error:
        await interaction.followup.send(location_error, ephemeral=True)
        return

    crate_class = str(crate_class or "WoodenCrate").strip()[:80]
    if not crate_class:
        await interaction.followup.send("Provide a crate/container classname.", ephemeral=True)
        return

    loot_key = loot_preset if loot_preset in SCENARIO_LOOT_PRESETS else "military_high"
    guard_class = ""
    guard_label = "No guards"
    if zombie_guards:
        guard_class, guard_label = resolve_scenario_guard_class(guard_preset, custom_guard_class)
        if not guard_class:
            await interaction.followup.send("Choose a guard preset or provide `custom_guard_class`.", ephemeral=True)
            return

    guard_count = max(0, min(80, int(guard_count or 0)))
    guard_radius = max(5, min(500, int(guard_radius or 35)))
    events = scenario_events_for_config(config)
    event_id = next_scenario_event_id(config)
    event_record = {
        "id": event_id,
        "name": f"Airdrop at {location_data['name']}",
        "event_type": "airdrop",
        "location": location_data["name"],
        "x": location_data["x"],
        "y": location_data["y"],
        "z": location_data["z"],
        "class_name": crate_class,
        "preset": "airdrop",
        "map": map_key,
        "count": 1,
        "radius": 0,
        "loot_preset": loot_key,
        "loot": SCENARIO_LOOT_PRESETS.get(loot_key, []),
        "visual_marker": bool(visual_marker),
        "marker_class": SCENARIO_AIRDROP_MARKER_CLASS if visual_marker else "",
        "guard_class": guard_class if zombie_guards else "",
        "guard_count": guard_count if zombie_guards else 0,
        "guard_radius": guard_radius if zombie_guards else 0,
        **restart_count_fields(0 if permanent else restarts),
        "enabled": True,
        "created_by": str(interaction.user.id),
        "created_at": str(datetime.now(UTC)),
    }
    events.append(event_record)
    save_guild_configs()

    upload_success, upload_status = await auto_push_scenario_events_xml(guild_id, config)

    embed = discord.Embed(
        title="AIRDROP EVENT CREATED",
        description=upload_status,
        color=0x2ECC71 if upload_success else 0xE74C3C
    )
    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
    embed.add_field(name="Runs", value=scenario_event_mode_text(event_record), inline=True)
    embed.add_field(name="Crate", value=f"`{crate_class}`", inline=True)
    embed.add_field(name="Loot", value=f"`{loot_key}` ({len(event_record['loot'])} item types)", inline=True)
    embed.add_field(name="Marker", value="On" if visual_marker else "Off", inline=True)
    embed.add_field(name="Guards", value=f"`{guard_count}`x {guard_label}" if zombie_guards else "Off", inline=True)
    embed.add_field(name="Location", value=f"{location_data['name']}\n`{location_data['x']} {location_data['y']} {location_data['z']}`", inline=False)
    embed.add_field(name="Controls", value="Use `/events list`, `/events disable`, `/events enable`, or `/events delete`.", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@events_group.command(name="vehiclereset", description="Admin: create a one-time or recurring vehicle reset event")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    scope="Reset all vehicles, or only one class near one spawn point",
    restarts="How many restarts to run. Use 0 for forever.",
    excluded_classes="Comma-separated vehicle classes to skip during all-vehicle reset",
    vehicle_class="Vehicle class for a point reset",
    location="Preset location or custom coordinates for point reset",
    radius="Reset radius. All reset uses a map-wide radius.",
    x="Custom X coordinate if location is custom",
    z="Custom Z coordinate if location is custom",
    y="Optional height coordinate"
)
@app_commands.choices(scope=[
    app_commands.Choice(name="All vehicles, with exceptions", value="all"),
    app_commands.Choice(name="One vehicle class near a point", value="point"),
])
@app_commands.autocomplete(location=scenario_location_autocomplete)
async def event_vehiclereset(
    interaction: discord.Interaction,
    scope: str = "all",
    restarts: int = 1,
    excluded_classes: str = "",
    vehicle_class: str = "",
    location: str = "custom",
    radius: int = 35,
    x: str = "",
    z: str = "",
    y: str = "0",
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    map_key = server_map_key(guild_id)
    event_id = next_scenario_event_id(config)

    if scope == "all":
        map_width, map_height = server_map_size(guild_id)
        center_x = map_width / 2
        center_z = map_height / 2
        reset_radius = int(max(map_width, map_height) * 1.5)
        excluded = [
            item.strip()
            for item in str(excluded_classes or "").split(",")
            if item.strip()
        ] or vehicle_reset_exclusions(config)
        event_record = {
            "id": event_id,
            "name": "All-vehicle reset",
            "event_type": "vehicle_reset_all",
            "location": "Map center",
            "x": center_x,
            "y": 0,
            "z": center_z,
            "class_name": "ALL_VEHICLES",
            "map": map_key,
            "count": 1,
            "radius": reset_radius,
            "exclude": excluded,
            **restart_count_fields(restarts),
            "enabled": True,
            "created_by": str(interaction.user.id),
            "created_at": str(datetime.now(UTC)),
        }
    else:
        vehicle_class = str(vehicle_class or "").strip()
        if not vehicle_class:
            await interaction.followup.send("For a point reset, provide `vehicle_class`.", ephemeral=True)
            return

        location_data, location_error = scenario_location_from_choice(location, x, z, y, map_key)
        if location_error:
            await interaction.followup.send(location_error, ephemeral=True)
            return

        reset_radius = max(5, min(250, int(radius or 35)))
        event_record = {
            "id": event_id,
            "name": f"{vehicle_class} reset at {location_data['name']}",
            "event_type": "vehicle_reset_point",
            "location": location_data["name"],
            "x": location_data["x"],
            "y": location_data["y"],
            "z": location_data["z"],
            "class_name": vehicle_class,
            "map": map_key,
            "count": 1,
            "radius": reset_radius,
            **restart_count_fields(restarts),
            "enabled": True,
            "created_by": str(interaction.user.id),
            "created_at": str(datetime.now(UTC)),
        }

    scenario_events_for_config(config).append(event_record)
    save_guild_configs()

    embed = discord.Embed(
        title="VEHICLE RESET EVENT CREATED",
        description="This reset remains a bridge-only action. Native console XML can spawn vehicles, but cannot delete existing ones on command.",
        color=0xF1C40F
    )
    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
    embed.add_field(name="Runs", value=scenario_event_mode_text(event_record), inline=True)
    embed.add_field(name="Scope", value="All vehicles" if scope == "all" else f"`{event_record['class_name']}` near point", inline=False)
    embed.add_field(name="Radius", value=f"`{event_record.get('radius')}`m", inline=True)
    if event_record.get("exclude"):
        embed.add_field(name="Exceptions", value=", ".join(f"`{item}`" for item in event_record["exclude"])[:1000], inline=False)
    embed.add_field(name="Location", value=f"{event_record['location']}\n`{event_record['x']} {event_record['y']} {event_record['z']}`", inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@events_group.command(name="list", description="Admin: list restart scenario events")
@app_commands.default_permissions(administrator=True)
async def event_list(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    events = scenario_events_for_config(config)
    if not events:
        await interaction.response.send_message("No scenario events configured.", ephemeral=True)
        return

    lines = []
    for event in events[:25]:
        state = "on" if event.get("enabled", True) else "off"
        mode = scenario_event_mode_text(event)
        extras = []
        if event.get("vehicle_condition"):
            extras.append(f"condition `{event.get('vehicle_condition')}`")
        if event.get("guard_class"):
            extras.append(f"guards `{event.get('guard_count', 0)}x`")
        if event.get("visual_marker"):
            extras.append("marker on")
        if event.get("exclude"):
            extras.append(f"exceptions `{len(event.get('exclude', []))}`")
        extra_text = f" ({', '.join(extras)})" if extras else ""
        lines.append(
            f"`{event.get('id')}` {state} {mode} `{event.get('event_type', 'event')}` - {event.get('name')} - "
            f"`{event.get('count', 1)}x {event.get('class_name')}` at `{event.get('location')}`"
            f"{extra_text}"
        )
    await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)


@events_group.command(name="reference", description="Admin: show loaded vanilla DayZ reference data")
@app_commands.default_permissions(administrator=True)
async def event_reference(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    map_key = server_map_key(guild_id)
    reference = load_dayz_reference(map_key)
    folder = DAYZ_REFERENCE_MAP_FOLDERS.get(map_key, "missing")
    location_count = len(scenario_location_presets_for_map(map_key))
    embed = discord.Embed(
        title="DAYZ VANILLA REFERENCE",
        description=f"Server map: `{map_key}`\nReference folder: `{folder}`",
        color=0x3498DB if reference.get("available") else 0xE74C3C
    )
    embed.add_field(name="Loaded", value="Yes" if reference.get("available") else "No", inline=True)
    embed.add_field(name="Locations", value=str(location_count), inline=True)
    embed.add_field(name="Zombies", value=str(len(reference.get("zombies", []))), inline=True)
    embed.add_field(name="Animals", value=str(len(reference.get("animals", []))), inline=True)
    embed.add_field(name="Containers", value=str(len(reference.get("containers", []))), inline=True)
    embed.add_field(
        name="Source",
        value="Uses bundled vanilla mission files. Modded classnames still need `spawn_preset: custom` plus `custom_class`.",
        inline=False
    )
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@events_group.command(name="disable", description="Admin: disable a scenario event without deleting it")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(event_id="Event ID from /events list")
async def event_disable(interaction: discord.Interaction, event_id: int):
    await set_scenario_event_enabled(interaction, event_id, False)


@events_group.command(name="enable", description="Admin: enable a disabled scenario event")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(event_id="Event ID from /events list")
async def event_enable(interaction: discord.Interaction, event_id: int):
    await set_scenario_event_enabled(interaction, event_id, True)


async def set_scenario_event_enabled(interaction, event_id, enabled):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    for event in scenario_events_for_config(config):
        if int(event.get("id", 0)) == int(event_id):
            event["enabled"] = bool(enabled)
            save_guild_configs()
            await interaction.response.send_message(
                f"Scenario event `{event_id}` {'enabled' if enabled else 'disabled'}.",
                ephemeral=True
            )
            return
    await interaction.response.send_message(f"Scenario event `{event_id}` not found.", ephemeral=True)


@events_group.command(name="delete", description="Admin: delete/cancel a scenario event")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(event_id="Event ID from /events list")
async def event_delete(interaction: discord.Interaction, event_id: int):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    events = scenario_events_for_config(config)
    kept = [event for event in events if int(event.get("id", 0)) != int(event_id)]
    if len(kept) == len(events):
        await interaction.response.send_message(f"Scenario event `{event_id}` not found.", ephemeral=True)
        return
    config["scenario_events"] = kept
    save_guild_configs()
    await interaction.response.send_message(f"Scenario event `{event_id}` deleted.", ephemeral=True)


@events_group.command(name="exportce", description="Admin: export console-safe events.xml and cfgeventspawns.xml")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    events_path="Remote events.xml path to merge from",
    spawns_path="Remote cfgeventspawns.xml path to merge from",
    spawnabletypes_path="Remote cfgspawnabletypes.xml path to merge from when crate loot is needed"
)
async def event_exportce(
    interaction: discord.Interaction,
    events_path: str = "",
    spawns_path: str = "",
    spawnabletypes_path: str = "",
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    built = await asyncio.to_thread(
        build_console_ce_event_files,
        guild_id,
        config,
        events_path,
        spawns_path,
        spawnabletypes_path
    )

    files = [
        discord.File(io.BytesIO(built["events_text"].encode("utf-8")), filename="events.xml"),
        discord.File(io.BytesIO(built["spawns_text"].encode("utf-8")), filename="cfgeventspawns.xml"),
    ]
    if built.get("spawnabletypes_text"):
        files.append(
            discord.File(
                io.BytesIO(built["spawnabletypes_text"].encode("utf-8")),
                filename="cfgspawnabletypes.xml"
            )
        )

    file_targets = [
        f"`events.xml` -> `{built['events_path']}`",
        f"`cfgeventspawns.xml` -> `{built['spawns_path']}`",
    ]
    if built.get("spawnabletypes_path"):
        file_targets.append(f"`cfgspawnabletypes.xml` -> `{built['spawnabletypes_path']}`")

    summary = "\n".join(built["messages"][-8:])
    await interaction.followup.send(
        "Console-safe event files exported. Upload these to the matching paths, then restart the server:\n"
        + "\n".join(file_targets)
        + "\n\n"
        + discord_safe_content(summary, 1200),
        files=files,
        ephemeral=True
    )


@events_group.command(name="uploadce", description="Admin: upload console-safe events.xml and cfgeventspawns.xml to Nitrado")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    events_path="Remote events.xml path. Leave blank for this map's default mission path.",
    spawns_path="Remote cfgeventspawns.xml path. Leave blank for this map's default mission path.",
    spawnabletypes_path="Remote cfgspawnabletypes.xml path. Used automatically when crate loot is needed.",
    consume_restart="True only when uploading immediately for the next restart count"
)
async def event_uploadce(
    interaction: discord.Interaction,
    events_path: str = "",
    spawns_path: str = "",
    spawnabletypes_path: str = "",
    consume_restart: bool = False,
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})

    success, built, messages = await asyncio.to_thread(
        upload_console_ce_event_files,
        guild_id,
        config,
        events_path,
        spawns_path,
        spawnabletypes_path,
        consume_restart
    )

    status = "uploaded" if success else "failed"
    summary = "\n".join(messages[-10:])
    restart_note = (
        "\n\nCE XML mode is now enabled for scheduled restart processing. Future scenario events will use native console XML instead of the bridge."
        if success else ""
    )
    await interaction.followup.send(
        f"Console CE event upload `{status}`.\n"
        f"`events.xml`: `{built['events_path']}`\n"
        f"`cfgeventspawns.xml`: `{built['spawns_path']}`\n"
        + (f"`cfgspawnabletypes.xml`: `{built['spawnabletypes_path']}`\n" if built.get("spawnabletypes_path") else "")
        + f"Records generated: `{built['record_count']}`\n\n"
        + discord_safe_content(summary, 1200)
        + restart_note,
        ephemeral=True
    )


@events_group.command(name="exportxml", description="Admin: export deliveries.xml for manual Nitrado upload")
@app_commands.default_permissions(administrator=True)
async def event_exportxml(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    xml_text = build_delivery_xml(
        delivery_queue,
        vehicle_rentals_queue,
        active_scenario_events(config)
    )
    file = discord.File(
        io.BytesIO(xml_text.encode("utf-8")),
        filename="deliveries.xml"
    )
    await interaction.response.send_message(
        "Manual fallback: upload this file to `/dayzxb/custom/deliveries.xml` on Nitrado, then restart the server. "
        "Use this when the bot host cannot reach Nitrado FTP.",
        file=file,
        ephemeral=True
    )


@events_group.command(name="bridgecode", description="Admin: export the manual init.c bridge snippet")
@app_commands.default_permissions(administrator=True)
async def event_bridgecode(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    instructions = (
        "CONSOLE NOTE: Xbox/PlayStation DayZ servers do not expose an official `init.c`, so this bridge snippet is for PC/custom hosts only. "
        "On console, use the supported XML/JSON files instead: `cfgspawnabletypes.xml` for spawned attachments, `types.xml` for loot economy, "
        "`globals.xml` for core timers/rules, `cfgeventspawns.xml` and `events.xml` for event/infected/vehicle/animal placement, and "
        "`cfgplayerspawn.json` for fresh spawn loadouts.\n\n"
        "Paste the bridge functions below into your mission `init.c` above `void main()`. "
        "Then add `SpawnWanderingDeliveries();` inside `main()`, after weather setup or near the end. "
        "or use `/installdayzbridge install:true` when FTP/DNS works again.\n\n"
        "After it is installed, upload `deliveries.xml` to `/dayzxb/custom/deliveries.xml` and restart the server.\n\n"
    )
    file = discord.File(
        io.BytesIO((instructions + WANDERING_DELIVERY_BRIDGE_CODE).encode("utf-8")),
        filename="wandering_bridge_v5_init_snippet.c"
    )
    await interaction.response.send_message(
        "Manual bridge fallback exported. This is for PC/custom hosts with mission `init.c` access; console servers cannot use this bridge.",
        file=file,
        ephemeral=True
    )


bot.tree.add_command(events_group)


console_group = app_commands.Group(
    name="console",
    description="Console-safe DayZ object spawner tools"
)


@console_group.command(name="setupobjects", description="Admin: install console object spawner JSON and cfggameplay reference")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    object_path="Remote path for the object spawner JSON",
    cfggameplay_path="Remote path to cfggameplay.json",
    spawner_ref="Reference written into WorldsData.objectSpawnersArr",
    upload="True uploads to Nitrado. False only previews status."
)
async def console_setupobjects(
    interaction: discord.Interaction,
    object_path: str = CONSOLE_OBJECT_SPAWNER_PATH,
    cfggameplay_path: str = "",
    spawner_ref: str = CONSOLE_OBJECT_SPAWNER_REF,
    upload: bool = True,
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    missing_api_fields = [
        field_name
        for field_name in ["nitrado_token", "service_id", "nitrado_user"]
        if not config.get(field_name)
    ]
    missing_ftp_fields = [
        field_name
        for field_name in ["ftp_user", "ftp_password"]
        if not config.get(field_name)
    ]
    settings = console_object_spawner_config(config)
    settings["object_path"] = object_path or CONSOLE_OBJECT_SPAWNER_PATH
    settings["spawner_ref"] = spawner_ref or CONSOLE_OBJECT_SPAWNER_REF

    cfg_ok, cfg_message, cfg_text, resolved_cfg_path = await asyncio.to_thread(
        download_cfggameplay_with_fallback,
        config,
        guild_id,
        cfggameplay_path
    )
    settings["cfggameplay_path"] = resolved_cfg_path

    try:
        updated_cfg, cfg_changed = update_cfggameplay_object_spawner(cfg_text, settings["spawner_ref"])
    except Exception as error:
        await interaction.followup.send(f"`cfggameplay.json` could not be parsed as JSON: `{error}`", ephemeral=True)
        return

    spawner_json = build_console_object_spawner_json(settings.get("objects", []))
    object_upload = (False, "Upload skipped.")
    cfg_upload = (False, "Upload skipped.")

    if upload:
        object_upload = await asyncio.to_thread(
            upload_text_file_to_nitrado,
            config,
            settings["object_path"],
            spawner_json
        )
        cfg_upload = await asyncio.to_thread(
            upload_text_file_to_nitrado,
            config,
            resolved_cfg_path,
            updated_cfg
        )
        settings["enabled"] = bool(object_upload[0] and cfg_upload[0])
    else:
        settings["enabled"] = False

    save_guild_configs()

    embed = discord.Embed(
        title="CONSOLE OBJECT SPAWNER SETUP",
        description=(
            "This uses DayZ console's `cfggameplay.json` `WorldsData.objectSpawnersArr` flow. "
            "No `init.c` is needed."
        ),
        color=0x2ECC71 if settings.get("enabled") else 0xE67E22
    )
    embed.add_field(name="Object Spawner", value=f"`{settings['object_path']}`", inline=False)
    embed.add_field(name="cfggameplay.json", value=f"`{resolved_cfg_path}`", inline=False)
    embed.add_field(name="Spawner Reference", value=f"`{settings['spawner_ref']}`", inline=False)
    embed.add_field(name="Objects", value=str(len(settings.get("objects", []))), inline=True)
    if missing_api_fields or missing_ftp_fields:
        missing_lines = []
        if missing_api_fields:
            missing_lines.append("API: " + ", ".join(f"`{field}`" for field in missing_api_fields))
        if missing_ftp_fields:
            missing_lines.append("FTP: " + ", ".join(f"`{field}`" for field in missing_ftp_fields))
        embed.add_field(
            name="Saved Server Login Missing",
            value=(
                "Run `/setup` with your Nitrado API and FTP details first, then run `/console setupobjects` again.\n"
                + "\n".join(missing_lines)
            )[:1000],
            inline=False
        )
    embed.add_field(name="cfggameplay Source", value=("Downloaded from server" if cfg_ok else cfg_message)[:900], inline=False)
    embed.add_field(name="cfggameplay Changed", value="Yes" if cfg_changed else "Already referenced", inline=True)
    embed.add_field(name="Object Upload", value=("OK" if object_upload[0] else object_upload[1])[:900], inline=False)
    embed.add_field(name="cfggameplay Upload", value=("OK" if cfg_upload[0] else cfg_upload[1])[:900], inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@console_group.command(name="addobject", description="Admin: add a static object to the console object spawner")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    class_name="DayZ classname to spawn",
    x="Map X coordinate",
    z="Map Z coordinate",
    y="Height coordinate, usually 0",
    yaw="Rotation/yaw",
    scale="Object scale",
    persistent="Whether to enable CE persistency for this object",
    upload_now="Upload the updated spawner JSON immediately"
)
async def console_addobject(
    interaction: discord.Interaction,
    class_name: str,
    x: str,
    z: str,
    y: str = "0",
    yaw: str = "0",
    scale: str = "1.0",
    persistent: bool = False,
    upload_now: bool = True,
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    settings = console_object_spawner_config(config)
    object_id = next_console_object_id(settings)
    record = dayz_object_record(class_name, x, z, y, yaw, 0, 0, scale, persistent, object_id)
    if not record:
        await interaction.followup.send("That object needs a valid classname plus numeric `x` and `z` coordinates.", ephemeral=True)
        return

    settings["objects"].append(record)
    save_guild_configs()

    upload_message = "Upload skipped. Run `/console uploadobjects` when ready."
    if upload_now:
        spawner_json = build_console_object_spawner_json(settings.get("objects", []))
        upload_ok, upload_message = await asyncio.to_thread(
            upload_text_file_to_nitrado,
            config,
            settings.get("object_path") or CONSOLE_OBJECT_SPAWNER_PATH,
            spawner_json
        )
        if not upload_ok:
            upload_message = f"Upload failed: {upload_message}"

    embed = discord.Embed(
        title="CONSOLE OBJECT ADDED",
        color=0x2ECC71
    )
    embed.add_field(name="Object ID", value=f"`{object_id}`", inline=True)
    embed.add_field(name="Class", value=f"`{record['name']}`", inline=False)
    embed.add_field(name="Position", value=f"`{record['pos'][0]} {record['pos'][1]} {record['pos'][2]}`", inline=False)
    embed.add_field(name="Yaw / Scale", value=f"`{record['ypr'][0]}` / `{record['scale']}`", inline=True)
    embed.add_field(name="Upload", value=discord_safe_content(upload_message, 900), inline=False)
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)


@console_group.command(name="uploadobjects", description="Admin: upload the current console object spawner JSON")
@app_commands.default_permissions(administrator=True)
async def console_uploadobjects(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    settings = console_object_spawner_config(config)
    spawner_json = build_console_object_spawner_json(settings.get("objects", []))
    upload_ok, upload_message = await asyncio.to_thread(
        upload_text_file_to_nitrado,
        config,
        settings.get("object_path") or CONSOLE_OBJECT_SPAWNER_PATH,
        spawner_json
    )
    await interaction.followup.send(
        discord_safe_content(
            f"{'Uploaded' if upload_ok else 'Upload failed'} `{len(settings.get('objects', []))}` object(s) to `{settings.get('object_path')}`.\n{upload_message}"
        ),
        ephemeral=True
    )


@console_group.command(name="exportobjects", description="Admin: export console object spawner JSON for manual upload")
@app_commands.default_permissions(administrator=True)
async def console_exportobjects(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    settings = console_object_spawner_config(config)
    spawner_json = build_console_object_spawner_json(settings.get("objects", []))
    file = discord.File(
        io.BytesIO(spawner_json.encode("utf-8")),
        filename=os.path.basename(settings.get("object_path") or "WanderingBotObjects.json")
    )
    await interaction.response.send_message(
        f"Manual fallback: upload this to `{settings.get('object_path')}` and make sure `cfggameplay.json` contains `{settings.get('spawner_ref')}` in `WorldsData.objectSpawnersArr`.",
        file=file,
        ephemeral=True
    )


@console_group.command(name="listobjects", description="Admin: list configured console object spawns")
@app_commands.default_permissions(administrator=True)
async def console_listobjects(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    settings = console_object_spawner_config(config)
    objects = settings.get("objects", [])
    if not objects:
        await interaction.response.send_message("No console object spawns configured yet.", ephemeral=True)
        return

    lines = []
    for item in objects[:25]:
        pos = item.get("pos") or ["?", "?", "?"]
        lines.append(f"`{item.get('id')}` `{item.get('name')}` at `{pos[0]} {pos[1]} {pos[2]}`")
    await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)


@console_group.command(name="deleteobject", description="Admin: remove one configured console object spawn")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(object_id="Object ID from /console listobjects", upload_now="Upload the updated spawner JSON immediately")
async def console_deleteobject(interaction: discord.Interaction, object_id: int, upload_now: bool = True):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    settings = console_object_spawner_config(config)
    before = len(settings.get("objects", []))
    settings["objects"] = [item for item in settings.get("objects", []) if int(item.get("id", 0) or 0) != int(object_id)]
    if len(settings["objects"]) == before:
        await interaction.followup.send(f"Object `{object_id}` not found.", ephemeral=True)
        return

    save_guild_configs()
    message = "Deleted locally."
    if upload_now:
        upload_ok, upload_message = await asyncio.to_thread(
            upload_text_file_to_nitrado,
            config,
            settings.get("object_path") or CONSOLE_OBJECT_SPAWNER_PATH,
            build_console_object_spawner_json(settings.get("objects", []))
        )
        message = "Deleted and uploaded." if upload_ok else f"Deleted locally, but upload failed: {upload_message}"

    await interaction.followup.send(discord_safe_content(message), ephemeral=True)


bot.tree.add_command(console_group)


@bot.tree.command(name="createfaction", description="Admin: create an official faction")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    name="Faction name",
    leader="Faction leader",
    member_1="Optional faction member",
    member_2="Optional faction member",
    member_3="Optional faction member",
    member_4="Optional faction member",
    member_5="Optional faction member",
    flag="Faction flag/name",
    role_color="Hex colour, example #2ecc71"
)
async def createfaction(
    interaction: discord.Interaction,
    name: str,
    leader: discord.Member,
    member_1: discord.Member = None,
    member_2: discord.Member = None,
    member_3: discord.Member = None,
    member_4: discord.Member = None,
    member_5: discord.Member = None,
    flag: str = "Not set",
    role_color: str = "#2ecc71"
):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    key = f"{guild_id}:{faction_key(name)}"

    if key in factions:
        await interaction.response.send_message("That faction already exists.", ephemeral=True)
        return

    try:
        color_value = int(role_color.replace("#", ""), 16)
        role_colour = discord.Color(color_value)
    except Exception:
        role_colour = discord.Color.green()

    role = await interaction.guild.create_role(
        name=f"Faction - {name}",
        colour=role_colour,
        reason="Wandering Bot faction creation"
    )

    member_ids = {leader.id}
    for picked_member in [member_1, member_2, member_3, member_4, member_5]:
        if picked_member:
            member_ids.add(picked_member.id)

    assigned = []
    for member_id in member_ids:
        member = interaction.guild.get_member(member_id)
        if member:
            await member.add_roles(role, reason="Wandering Bot faction membership")
            assigned.append(member.id)

    factions[key] = {
        "guild_id": guild_id,
        "name": name,
        "leader_id": leader.id,
        "members": assigned,
        "flag": flag,
        "role_id": role.id,
        "role_color": f"#{color_value:06x}" if "color_value" in locals() else "#2ecc71",
        "created": str(datetime.now(UTC))
    }
    save_factions()

    embed = discord.Embed(
        title="OFFICIAL FACTION CREATED",
        description="\n".join(faction_display_lines(factions[key])),
        color=role_colour
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(embed=style_embed(embed))


@bot.tree.command(name="addfactionmember", description="Admin: add a member to an official faction")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(name="Faction name", member="Discord member")
async def addfactionmember(interaction: discord.Interaction, name: str, member: discord.Member):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    key = f"{interaction.guild.id}:{faction_key(name)}"
    faction = factions.get(key)

    if not faction:
        await interaction.response.send_message("Faction not found.", ephemeral=True)
        return

    members = faction.setdefault("members", [])
    if member.id not in members:
        members.append(member.id)

    role = interaction.guild.get_role(int(faction.get("role_id", 0)))
    if role:
        await member.add_roles(role, reason="Wandering Bot faction membership")

    save_factions()
    await interaction.response.send_message(f"{member.mention} added to `{faction['name']}`.", ephemeral=True)


@bot.tree.command(name="removefactionmember", description="Admin: remove a member from an official faction")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(name="Faction name", member="Discord member")
async def removefactionmember(interaction: discord.Interaction, name: str, member: discord.Member):

    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    key = f"{interaction.guild.id}:{faction_key(name)}"
    faction = factions.get(key)

    if not faction:
        await interaction.response.send_message("Faction not found.", ephemeral=True)
        return

    faction["members"] = [member_id for member_id in faction.get("members", []) if member_id != member.id]

    role = interaction.guild.get_role(int(faction.get("role_id", 0)))
    if role:
        await member.remove_roles(role, reason="Wandering Bot faction membership removed")

    save_factions()
    await interaction.response.send_message(f"{member.mention} removed from `{faction['name']}`.", ephemeral=True)


@bot.tree.command(name="factions", description="List official factions")
async def list_factions(interaction: discord.Interaction):
    guild_prefix = f"{interaction.guild.id}:"
    guild_factions = [faction for key, faction in factions.items() if key.startswith(guild_prefix)]

    if not guild_factions:
        await interaction.response.send_message("No official factions have been created yet.", ephemeral=True)
        return

    lines = [
        f"**{faction.get('name')}** - Leader <@{faction.get('leader_id')}> - {len(faction.get('members', []))} members"
        for faction in guild_factions
    ]

    embed = discord.Embed(
        title="OFFICIAL FACTIONS",
        description="\n".join(lines[:25]),
        color=0x2ECC71
    )
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="factioninfo", description="Show official faction details")
@app_commands.describe(name="Faction name")
async def factioninfo(interaction: discord.Interaction, name: str):
    key = f"{interaction.guild.id}:{faction_key(name)}"
    faction = factions.get(key)

    if not faction:
        await interaction.response.send_message("Faction not found.", ephemeral=True)
        return

    member_lines = [f"<@{member_id}>" for member_id in faction.get("members", [])]
    embed = discord.Embed(
        title=f"FACTION: {faction.get('name')}",
        description="\n".join(faction_display_lines(faction)),
        color=0x2ECC71
    )
    embed.add_field(
        name="Members",
        value=", ".join(member_lines) if member_lines else "No members",
        inline=False
    )
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


# Slash command wrappers
extra_tools_group = app_commands.Group(
    name="tools",
    description="Extra utility and admin tools"
)


@bot.tree.command(name="helpme", description="Show command/help information")
async def slash_helpme(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "helpme")
@extra_tools_group.command(name="swearjar", description="Show swear jar leaderboard")
async def slash_swearjar(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "swearjar")
@bot.tree.command(name="heatmap", description="Show territory heatmap summary")
async def slash_heatmap(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "heatmap")
@bot.tree.command(name="toplongshots", description="Show longshot leaderboard")
async def slash_toplongshots(interaction: discord.Interaction):
    if not longshot_records:
        await interaction.response.send_message("No longshot records yet.", ephemeral=True)
        return
    await interaction.response.send_message(embed=build_showcase_longshots_embed(), ephemeral=True)
@bot.tree.command(name="topkills", description="Show top kill leaderboard")
async def slash_topkills(interaction: discord.Interaction):
    if not player_stats:
        await interaction.response.send_message("No stats available.", ephemeral=True)
        return
    await interaction.response.send_message(embed=build_showcase_topkills_embed(interaction.guild), ephemeral=True)
@extra_tools_group.command(name="staffroles", description="List staff roles")
@app_commands.default_permissions(administrator=True)
async def slash_staffroles(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "staffroles")
@bot.tree.command(name="mylink", description="Show your linked gamertag")
async def slash_mylink(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "mylink")
@bot.tree.command(name="wallet", description="Show your wallet")
async def slash_wallet(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "wallet")
@bot.tree.command(name="shop", description="Show shop")
async def slash_shop(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "shop")

@extra_tools_group.command(name="setadminrole", description="Set primary admin role")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(role="Existing Discord role")
async def slash_setadminrole(interaction: discord.Interaction, role: discord.Role):
    if not can_modify_admin_roles_interaction(interaction):
        await interaction.response.send_message(
            "Only a Discord administrator or the guild owner can change bot admin roles.",
            ephemeral=True
        )
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    config["admin_roles"] = [role.name]
    save_guild_configs()
    await interaction.response.send_message(f"Primary admin role set to {role.mention}.", ephemeral=True)


@extra_tools_group.command(
    name="setcountdownchannel",
    description="Set the channel where pre-restart countdown messages (30/15/5/1 min) are posted",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Channel for the countdown (leave empty to use the current channel)")
async def slash_set_countdown_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    target = channel or interaction.channel
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(
        guild_id, {"guild_name": interaction.guild.name, "channels": {}}
    )
    config.setdefault("channels", {})["restart_countdown"] = target.id
    save_guild_configs()
    await interaction.response.send_message(
        f"✅ Pre-restart countdown announcements (30/15/5/1 min + the post-restart message) will now be posted in {target.mention}.\n\n"
        f"Run `/extra unsetcountdownchannel` to revert to the default (`general_chat`).",
        ephemeral=True,
    )


@extra_tools_group.command(
    name="unsetcountdownchannel",
    description="Revert restart-countdown messages to post in general_chat",
)
@app_commands.default_permissions(administrator=True)
async def slash_unset_countdown_channel(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id, {})
    channels = config.get("channels", {})
    if "restart_countdown" in channels:
        channels.pop("restart_countdown", None)
        save_guild_configs()
        await interaction.response.send_message(
            "✅ Countdown channel override removed. Countdowns will go back to the default (`general_chat`).",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "No override was set. Countdowns are already going to the default channel (`general_chat`).",
            ephemeral=True,
        )


@extra_tools_group.command(
    name="setroasts",
    description="Enable or disable AI death roasts in the killfeed for this guild",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(state="Turn AI death roasts on or off")
@app_commands.choices(state=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
async def slash_set_roasts(interaction: discord.Interaction, state: app_commands.Choice[str]):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(
        guild_id, {"guild_name": interaction.guild.name, "channels": {}}
    )
    enabled = state.value == "on"
    config["roasts_enabled"] = enabled
    save_guild_configs()
    key_status = "✅ Universal LLM key is configured." if EMERGENT_LLM_KEY else (
        "⚠️ `EMERGENT_LLM_KEY` is not set on this bot — roasts will fall back "
        "to short pre-written one-liners until you add the key."
    )
    if enabled:
        await interaction.response.send_message(
            "💀 **AI Death Roasts: ON.** Each player-kill embed will now include a one-line trash-talk "
            f"line from the killfeed. {key_status}\n\nDisable with `/extra setroasts off`.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "🔇 **AI Death Roasts: OFF.** The killfeed will stay clean. Re-enable with `/extra setroasts on`.",
            ephemeral=True,
        )


@extra_tools_group.command(
    name="setroasttone",
    description="Live-switch the AI death-roast tone for this guild",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(tone="Tone preset for the LLM roast generator")
@app_commands.choices(tone=[
    app_commands.Choice(name="mixed (random)", value="mixed"),
    app_commands.Choice(name="edgy", value="edgy"),
    app_commands.Choice(name="pg13", value="pg13"),
    app_commands.Choice(name="brutal_clean", value="brutal_clean"),
])
async def slash_set_roasttone(interaction: discord.Interaction, tone: app_commands.Choice[str]):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(
        guild_id, {"guild_name": interaction.guild.name, "channels": {}}
    )
    config["roast_tone"] = tone.value
    save_guild_configs()
    await interaction.response.send_message(
        f"✅ Roast tone set to **{tone.name}**. Next kill will use the new vibe.",
        ephemeral=True,
    )


@extra_tools_group.command(
    name="setrecapchannel",
    description="Set the channel for daily/weekly recap auto-posts",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Channel for recaps (leave empty for current channel; falls back to killfeed)")
async def slash_set_recap_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    target = channel or interaction.channel
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(
        guild_id, {"guild_name": interaction.guild.name, "channels": {}}
    )
    config.setdefault("channels", {})["recap"] = target.id
    save_guild_configs()
    await interaction.response.send_message(
        f"✅ Daily/weekly recap auto-posts will be sent in {target.mention}.\n"
        f"They fire at **{RECAP_DAILY_HOUR_UTC:02d}:00 UTC**.",
        ephemeral=True,
    )


@bot.command()
async def setcountdownchannel(ctx, *, channel_mention: str = None):
    """Prefix variant: `!setcountdownchannel #channel` — or run with no
    argument inside the channel you want to use. Sets the channel where
    the bot posts its 30/15/5/1 minute pre-restart countdown messages."""
    if not has_member_admin_power(ctx.author):
        await ctx.send("Admin only.")
        return

    target = None
    if ctx.message.channel_mentions:
        target = ctx.message.channel_mentions[0]
    elif channel_mention:
        # Look up by name if user typed a bare name (not a #mention)
        name = channel_mention.lstrip("#").strip()
        target = discord.utils.get(ctx.guild.text_channels, name=name)

    if target is None:
        target = ctx.channel

    guild_id = str(ctx.guild.id)
    config = guild_configs.setdefault(
        guild_id, {"guild_name": ctx.guild.name, "channels": {}}
    )
    config.setdefault("channels", {})["restart_countdown"] = target.id
    save_guild_configs()
    await ctx.send(
        f"✅ Pre-restart countdown announcements will now be posted in {target.mention}.\n"
        f"(Run `!unsetcountdownchannel` to revert.)"
    )


@bot.command()
async def unsetcountdownchannel(ctx):
    if not has_member_admin_power(ctx.author):
        await ctx.send("Admin only.")
        return
    guild_id = str(ctx.guild.id)
    channels = guild_configs.get(guild_id, {}).get("channels", {})
    if "restart_countdown" in channels:
        channels.pop("restart_countdown", None)
        save_guild_configs()
        await ctx.send("✅ Countdown channel override removed.")
    else:
        await ctx.send("No countdown channel override was set.")


@extra_tools_group.command(name="addstaffrole", description="Add a staff role")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(role="Existing Discord role")
async def slash_addstaffrole(interaction: discord.Interaction, role: discord.Role):
    if not can_modify_admin_roles_interaction(interaction):
        await interaction.response.send_message(
            "Only a Discord administrator or the guild owner can change bot admin roles.",
            ephemeral=True
        )
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    roles = config.setdefault("admin_roles", DEFAULT_ADMIN_ROLES.copy())
    if role.name not in roles:
        roles.append(role.name)
    save_guild_configs()
    await interaction.response.send_message(f"Staff role added: {role.mention}.", ephemeral=True)
@extra_tools_group.command(name="giverole", description="Admin: give an existing role to a real Discord member")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(member="Discord member", role="Existing Discord role")
async def giverole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await member.add_roles(role, reason=f"Role given by {interaction.user}")
    await interaction.response.send_message(f"Added {role.mention} to {member.mention}.", ephemeral=True)
@extra_tools_group.command(name="removerole", description="Admin: remove an existing role from a real Discord member")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(member="Discord member", role="Existing Discord role")
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await member.remove_roles(role, reason=f"Role removed by {interaction.user}")
    await interaction.response.send_message(f"Removed {role.mention} from {member.mention}.", ephemeral=True)
@bot.tree.command(name="factionticket", description="Create faction request")
@app_commands.describe(faction_name="Faction name")
async def slash_factionticket(interaction: discord.Interaction, faction_name: str): await run_legacy_as_slash(interaction, "factionticket", faction_name=faction_name)
@bot.tree.command(name="factionapprove", description="Approve faction request")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(message_id="Ticket message ID")
async def slash_factionapprove(interaction: discord.Interaction, message_id: int): await run_legacy_as_slash(interaction, "factionapprove", message_id=message_id)
@bot.tree.command(name="purge", description="Purge recent messages")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(amount="Amount")
async def slash_purge(interaction: discord.Interaction, amount: int = 10): await run_legacy_as_slash(interaction, "purge", amount=amount)
@bot.tree.command(name="purgeuser", description="Purge user messages")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(member="Member", amount="Amount")
async def slash_purgeuser(interaction: discord.Interaction, member: discord.Member, amount: int = 50): await run_legacy_as_slash(interaction, "purgeuser", member=member, amount=amount)
@extra_tools_group.command(name="purgebots", description="Admin: purge bot messages")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(amount="Amount")
async def slash_purgebots(interaction: discord.Interaction, amount: int = 100): await run_legacy_as_slash(interaction, "purgebots", amount=amount)
@bot.tree.command(name="setradarchannel", description="Set radar channel")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Channel")
async def slash_setradarchannel(interaction: discord.Interaction, channel: discord.TextChannel): await run_legacy_as_slash(interaction, "setradarchannel", channel=channel)
@bot.tree.command(name="radarping", description="Send radar ping")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(x="X", y="Y", reason="Reason")
async def slash_radarping(interaction: discord.Interaction, x: str, y: str, reason: str = "Survivor Activity"): await run_legacy_as_slash(interaction, "radarping", x=x, y=y, reason=reason)
@bot.tree.command(name="admstatus", description="Admin: show ADM feed status")
@app_commands.default_permissions(administrator=True)
async def slash_admstatus(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "admstatus")


@bot.tree.command(name="whoami", description="Show what level of bot-admin access you have and what's linked to you")
async def slash_whoami(interaction: discord.Interaction):
    """Diagnostic command — shows every reason the bot thinks (or doesn't
    think) you're an admin, plus your linked gamertag and basic stats.
    Useful for figuring out 'why can/can't this person use /pvecomplete?'
    questions without trial and error."""
    member = interaction.user
    guild = interaction.guild
    guild_id = str(guild.id) if guild else None

    # Compute every admin tier
    is_global_owner = is_global_bot_owner_id(getattr(member, "id", ""))
    is_guild_owner = bool(guild and getattr(guild, "owner_id", None) == getattr(member, "id", None))
    has_admin_perm = bool(getattr(getattr(member, "guild_permissions", None), "administrator", False))

    matching_admin_roles = []
    if guild_id:
        config = guild_configs.get(guild_id, {}) or {}
        admin_roles = config.get("admin_roles", DEFAULT_ADMIN_ROLES)
        admin_role_set = {str(name).strip().lower() for name in (admin_roles or [])}
        for role in getattr(member, "roles", []) or []:
            if str(getattr(role, "name", "")).strip().lower() in admin_role_set:
                matching_admin_roles.append(role.name)

    is_bot_admin = is_global_owner or is_guild_owner or has_admin_perm or bool(matching_admin_roles)
    can_modify_roles = is_global_owner or is_guild_owner or has_admin_perm

    embed = discord.Embed(
        title=f"🪪 {member.display_name}",
        description=(
            "🟢 **You ARE a bot admin.**" if is_bot_admin
            else "🔴 **You are NOT a bot admin.**"
        ),
        color=0x2ECC71 if is_bot_admin else 0x95A5A6,
    )

    perms_lines = []
    perms_lines.append(("✅" if is_global_owner else "⬜") + " Global bot owner ID")
    perms_lines.append(("✅" if is_guild_owner else "⬜") + " Discord guild owner")
    perms_lines.append(("✅" if has_admin_perm else "⬜") + " Discord `Administrator` permission")
    if matching_admin_roles:
        perms_lines.append("✅ Bot `admin_roles` match: " + ", ".join(f"`{r}`" for r in matching_admin_roles))
    else:
        perms_lines.append("⬜ Bot `admin_roles` match — none of your roles are in the configured list")
    embed.add_field(
        name="🔐 Admin power sources",
        value="\n".join(perms_lines),
        inline=False,
    )

    embed.add_field(
        name="✏️ Can modify admin roles? (`/extra setadminrole` etc.)",
        value="✅ Yes" if can_modify_roles else "❌ No (requires Discord admin / guild owner / bot owner)",
        inline=False,
    )

    # Linked gamertag + stats
    discord_id = str(member.id)
    linked_player = None
    for player_name, info in linked_players.items():
        if str(info.get("discord_id", "")) == discord_id:
            linked_player = (player_name, info)
            break
    if linked_player:
        player_name, info = linked_player
        stats = player_stats.get(player_name, {})
        embed.add_field(
            name="🎮 Linked gamertag",
            value=f"**`{player_name}`** — linked since <t:{int(info.get('linked_at', 0))}:R>" if info.get("linked_at") else f"**`{player_name}`**",
            inline=False,
        )
        kills = stat_int(stats, "kills") if stats else 0
        deaths = stat_int(stats, "deaths") if stats else 0
        kd = kills if deaths == 0 else round(kills / max(1, deaths), 2)
        embed.add_field(name="☠️ Kills", value=str(kills), inline=True)
        embed.add_field(name="💀 Deaths", value=str(deaths), inline=True)
        embed.add_field(name="⚖️ K/D", value=str(kd), inline=True)
    else:
        embed.add_field(
            name="🎮 Linked gamertag",
            value="❌ No gamertag linked yet — run `/linkgamer <your in-game name>` to start tracking stats.",
            inline=False,
        )

    embed.set_thumbnail(url=getattr(member.display_avatar, "url", BOT_IMAGE))
    embed.set_footer(text="Wandering Bot Alpha — Identity Check")
    embed.timestamp = datetime.now(UTC)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


# =========================================================
# /playercard — full career stat card
# =========================================================

def build_player_card_embed(guild_id, player_name):
    stats = player_stats.get(player_name, {})
    if not stats:
        return None
    gid = str(guild_id)
    kills = stat_int(stats, "kills") if stats else 0
    deaths = stat_int(stats, "deaths") if stats else 0
    headshots = stat_int(stats, "headshots") if stats else 0
    vehicle_kills = stat_int(stats, "vehicle_kills") if stats else 0
    vehicle_deaths = stat_int(stats, "vehicle_deaths") if stats else 0
    rampages = stat_int(stats, "rampages") if stats else 0
    multikill_best = stat_int(stats, "multikill_best") if stats else 0
    bounty_claims = stat_int(stats, "bounty_claims") if stats else 0
    bounty_earnings = stat_int(stats, "bounty_earnings") if stats else 0
    longest_shot = float(stats.get("longest_shot_distance", 0) or 0)
    longest_weapon = stats.get("longest_shot_weapon", "") or "—"
    longest_victim = stats.get("longest_shot_victim", "") or "—"
    current_streak = stat_int(stats, "current_streak_days") if stats else 0
    longest_streak = stat_int(stats, "longest_streak_days") if stats else 0
    online_seconds = stat_int(stats, "time_online_seconds") if stats else 0
    cuts = stat_int(stats, "cuts") if stats else 0
    suicides = stat_int(stats, "suicides") if stats else 0
    zombies = stat_int(stats, "zombie_deaths") if stats else 0
    builds = stat_int(stats, "builds") if stats else 0
    raids = stat_int(stats, "raids") if stats else 0
    animals = stat_int(stats, "animals_hunted") if stats else 0
    kd = kills if deaths == 0 else round(kills / max(1, deaths), 2)
    hs_rate = round((headshots / kills) * 100, 1) if kills > 0 else 0.0

    embed = discord.Embed(
        title=f"🪪 PLAYER CARD — {player_name}",
        description=(
            f"`{guild_configs.get(gid, {}).get('guild_name', 'Server')}` "
            f"survivor dossier."
        ),
        color=0x1ABC9C,
    )
    embed.add_field(name="☠️ Kills", value=str(kills), inline=True)
    embed.add_field(name="💀 Deaths", value=str(deaths), inline=True)
    embed.add_field(name="⚖️ K/D", value=str(kd), inline=True)
    embed.add_field(name="💥 Headshots", value=f"{headshots} ({hs_rate}%)", inline=True)
    embed.add_field(name="🔥 Rampages", value=f"{rampages} (best: {multikill_best})", inline=True)
    embed.add_field(
        name="🎯 Longest Shot",
        value=(
            f"{longest_shot:.0f}m with {longest_weapon}\non {longest_victim}"
            if longest_shot > 0 else "—"
        ),
        inline=False,
    )
    embed.add_field(name="🚗 Vehicle Kills", value=str(vehicle_kills), inline=True)
    embed.add_field(name="🚗💀 Vehicle Deaths", value=str(vehicle_deaths), inline=True)
    embed.add_field(name="🩸 Survival Streak", value=f"{current_streak}d (best: {longest_streak}d)", inline=True)
    if bounty_claims:
        embed.add_field(
            name="💰 Bounty Hunter",
            value=f"{bounty_claims} claim(s) • {bounty_earnings:,} {BOUNTY_CURRENCY}",
            inline=True,
        )
    embed.add_field(name="⏱️ Time Online", value=format_duration(online_seconds), inline=True)
    embed.add_field(
        name="📋 Misc",
        value=(
            f"Zombie deaths: {zombies}  •  Suicides: {suicides}  •  Cuts: {cuts}\n"
            f"Builds: {builds}  •  Raids: {raids}  •  Animals: {animals}"
        ),
        inline=False,
    )

    # 🔫 Current alive-streak / personal-best
    spree = (alive_streaks.get(gid) or {}).get(player_name) or {}
    cur_spree = int(spree.get("current_spree", 0) or 0)
    best_spree = int(spree.get("best_spree", 0) or 0)
    if cur_spree or best_spree:
        embed.add_field(
            name="🔫 Kill Spree",
            value=f"This life: **{cur_spree}** • Personal best: **{best_spree}**",
            inline=True,
        )

    # 👹 Top nemeses (who killed this player most)
    top_nem = get_top_nemeses(gid, player_name, limit=3)
    if top_nem:
        embed.add_field(
            name="👹 Top Nemeses",
            value="\n".join(f"• `{name}` ({n}x)" for name, n in top_nem),
            inline=True,
        )
    # 🎯 Favourite victims
    top_vic = get_top_victims(gid, player_name, limit=3)
    if top_vic:
        embed.add_field(
            name="🎯 Favourite Victims",
            value="\n".join(f"• `{name}` ({n}x)" for name, n in top_vic),
            inline=True,
        )

    # 🏆 Achievements
    ach = _player_achievements(gid, player_name)
    unlocked = ach.get("unlocked", [])
    if unlocked:
        badges = " ".join(
            ACHIEVEMENT_DEFS[b][1] for b in unlocked if b in ACHIEVEMENT_DEFS
        )
        embed.add_field(
            name=f"🏆 Achievements ({len(unlocked)}/{len(ACHIEVEMENT_DEFS)})",
            value=badges + f"\n*Hover/tap emoji or run `/whoami` to inspect.*",
            inline=False,
        )

    if stats.get("first_adm_seen"):
        embed.set_footer(text=f"First seen in ADM: {stats.get('first_adm_seen', 'Unknown')}")
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.timestamp = datetime.now(UTC)
    return style_embed(embed)


@bot.tree.command(name="playercard", description="Show your career stat card (or someone else's)")
@app_commands.describe(player_name="In-game name (omit to use your linked gamertag)")
async def slash_playercard(interaction: discord.Interaction, player_name: str = None):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    if not player_name:
        # Try to resolve via linked_players
        discord_id = str(interaction.user.id)
        for linked_name, info in linked_players.items():
            if str(info.get("discord_id", "")) == discord_id:
                player_name = linked_name
                break
        if not player_name:
            await interaction.response.send_message(
                "❌ You haven't linked a gamertag yet. Run `/linkgamer <your in-game name>` first, "
                "or pass `/playercard <name>` to look up someone else.",
                ephemeral=True,
            )
            return
    embed = build_player_card_embed(guild_id, player_name)
    if not embed:
        await interaction.response.send_message(
            f"❌ No stats found for **{player_name}**. Make sure the name matches exactly what shows in the ADM logs.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(embed=embed)


# =========================================================
# /bounty — set / list / claim history / clear
# =========================================================

bounty_group = app_commands.Group(name="bounty", description="DayZ bounty system — put a price on someone's head.")


@bounty_group.command(name="set", description="Place a bounty on a player's head")
@app_commands.describe(player="Target in-game name", amount=f"{BOUNTY_CURRENCY} to add to the bounty pool")
async def slash_bounty_set(interaction: discord.Interaction, player: str, amount: int):
    if amount <= 0:
        await interaction.response.send_message("Amount must be positive.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    posted_by = interaction.user.display_name
    entry = add_bounty(guild_id, player, amount, posted_by)
    if not entry:
        await interaction.response.send_message("Could not set bounty.", ephemeral=True)
        return
    embed = discord.Embed(
        title="💰 BOUNTY POSTED",
        description=f"**{entry['target']}** is now worth **{entry['amount']:,} {entry.get('currency', BOUNTY_CURRENCY)}**.",
        color=0xF1C40F,
    )
    embed.add_field(name="Posted by", value=posted_by, inline=True)
    embed.add_field(name="Pool", value=f"{entry['amount']:,} {entry.get('currency', BOUNTY_CURRENCY)}", inline=True)
    embed.set_footer(text="Wandering Bot Alpha — Bounty System")
    await interaction.response.send_message(embed=style_embed(embed))


@bounty_group.command(name="list", description="List all active bounties on this server")
async def slash_bounty_list(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    items = list_bounties(guild_id)
    items.sort(key=lambda b: int(b.get("amount", 0) or 0), reverse=True)
    embed = discord.Embed(title="💰 ACTIVE BOUNTIES", color=0xF1C40F)
    if not items:
        embed.description = "No active bounties. Run `/bounty set <player> <amount>` to start one."
    else:
        lines = []
        for idx, b in enumerate(items[:25], start=1):
            lines.append(
                f"**{idx}.** `{b.get('target', 'Unknown')}` — "
                f"**{int(b.get('amount', 0)):,} {b.get('currency', BOUNTY_CURRENCY)}** "
                f"(by {b.get('posted_by', '?')})"
            )
        embed.description = "\n".join(lines)
    embed.set_footer(text="Wandering Bot Alpha — Bounty Board")
    embed.timestamp = datetime.now(UTC)
    await interaction.response.send_message(embed=style_embed(embed))


@bounty_group.command(name="clear", description="Admin: remove a bounty without anyone claiming it")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(player="Target whose bounty should be cleared")
async def slash_bounty_clear(interaction: discord.Interaction, player: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    removed = clear_bounty(guild_id, player)
    if not removed:
        await interaction.response.send_message(f"No active bounty on **{player}**.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"✅ Cleared bounty on **{removed.get('target', player)}** "
        f"({int(removed.get('amount', 0)):,} {removed.get('currency', BOUNTY_CURRENCY)} refunded to the void).",
        ephemeral=True,
    )


bot.tree.add_command(bounty_group)


# =========================================================
# 🏅 LIVE LEADERBOARD (bounty hunters / streaks / rampage kings)
# =========================================================

last_mega_leaderboard_message_ids = {}


# =========================================================
# Leaderboard categories (6) — used by both server + global scopes
# =========================================================

LEADERBOARD_CATEGORIES = [
    {
        "key": "kills",       "title": "☠️  MOST KILLS",
        "source": "player_stats", "stat_key": "kills",
        "value": lambda v: f"{int(v):,} kills",
    },
    {
        "key": "deaths",      "title": "💀  MOST DEATHS",
        "source": "player_stats", "stat_key": "deaths",
        "value": lambda v: f"{int(v):,} deaths",
    },
    {
        "key": "time_played", "title": "⏱️  MOST TIME PLAYED",
        "source": "player_stats", "stat_key": "time_online_seconds",
        "value": lambda v: format_duration(int(v or 0)),
    },
    {
        "key": "builds",      "title": "🔨  MOST BUILT",
        "source": "player_stats", "stat_key": "builds",
        "value": lambda v: f"{int(v):,} parts",
    },
    {
        "key": "kill_spree",  "title": "🔫  HIGHEST KILL STREAK",
        "source": "alive_streaks", "stat_key": "best_spree",
        "value": lambda v: f"{int(v)} kills w/o dying",
    },
    {
        "key": "longshot",    "title": "🎯  LONGEST SHOT",
        "source": "longshot_records", "stat_key": "distance",
        "value": lambda v: f"{float(v):.0f}m",
    },
    {
        "key": "swears",      "title": "🤬  MOST SWEARING",
        "source": "swear_jar", "stat_key": "count",
        "value": lambda v: f"{int(v):,} swears",
    },
    {
        "key": "flags",       "title": "🚩  MOST FLAGS RAISED",
        "source": "player_stats", "stat_key": "flags_raised",
        "value": lambda v: f"{int(v):,} flags",
    },
    {
        "key": "animal_deaths", "title": "🐺  MOST DEATHS BY ANIMAL",
        "source": "player_stats", "stat_key": "animal_deaths",
        "value": lambda v: f"{int(v):,} deaths",
    },
    {
        "key": "zombie_deaths", "title": "🧟  MOST DEATHS BY ZOMBIES",
        "source": "player_stats", "stat_key": "zombie_deaths",
        "value": lambda v: f"{int(v):,} deaths",
    },
]


def gather_category_rows(category, scope, guild_id=None, limit=10):
    """Return [(player, value_str), ...] for a single category.
    scope='server' uses guild_id filter; scope='global' aggregates."""
    sk = category["stat_key"]
    src = category["source"]

    if src == "player_stats":
        rows = []
        for player, stats in player_stats.items():
            v = int(stats.get(sk, 0) or 0)
            if v <= 0:
                continue
            if scope == "server":
                if str(stats.get("guild_id", "")) != str(guild_id):
                    continue
            rows.append((player, v))
        rows.sort(key=lambda r: r[1], reverse=True)
        return [(p, category["value"](v)) for p, v in rows[:limit]]

    if src == "longshot_records":
        candidates = []
        if scope == "server":
            for entry in (longshot_records.get(str(guild_id)) or []):
                candidates.append((entry.get("killer", "?"), float(entry.get("distance", 0) or 0)))
        else:
            for gid, entries in longshot_records.items():
                for entry in entries:
                    candidates.append((entry.get("killer", "?"), float(entry.get("distance", 0) or 0)))
        best = {}
        for killer, dist in candidates:
            if dist > best.get(killer, 0):
                best[killer] = dist
        rows = sorted(best.items(), key=lambda r: r[1], reverse=True)
        return [(p, category["value"](v)) for p, v in rows[:limit]]

    if src == "alive_streaks":
        out = []
        if scope == "server":
            for player, entry in (alive_streaks.get(str(guild_id)) or {}).items():
                v = int(entry.get(sk, 0) or 0)
                if v > 0:
                    out.append((player, v))
        else:
            best_per_player = {}
            for gid, players in alive_streaks.items():
                if not isinstance(players, dict):
                    continue
                for player, entry in players.items():
                    if not isinstance(entry, dict):
                        continue
                    v = int(entry.get(sk, 0) or 0)
                    if v > best_per_player.get(player, 0):
                        best_per_player[player] = v
            out = list(best_per_player.items())
        out.sort(key=lambda r: r[1], reverse=True)
        return [(p, category["value"](v)) for p, v in out[:limit]]

    if src == "swear_jar":
        # swear_jar is a flat dict keyed by Discord user_id, with
        # 'name' and 'count' fields. Not per-guild — same data shown
        # in both server and global scopes (consistent with how it's
        # stored).
        rows = []
        for user_id, entry in swear_jar.items():
            if not isinstance(entry, dict):
                continue
            v = int(entry.get(sk, 0) or 0)
            if v <= 0:
                continue
            name = entry.get("name", f"user_{user_id}")
            # Drop the #discriminator if it's a legacy User#1234 format
            name = name.split("#")[0] if "#" in name else name
            rows.append((name, v))
        rows.sort(key=lambda r: r[1], reverse=True)
        return [(p, category["value"](v)) for p, v in rows[:limit]]

    return []


def _rank_icon(idx):
    """Return the rank icon for a 1-indexed rank position (1..10)."""
    table = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    if 1 <= idx <= len(table):
        return table[idx - 1]
    return f"`{idx:>2}.`"


def build_scope_leaderboard_embed(guild_id, scope, scope_label, scope_emoji, color):
    """Build ONE rich Discord embed for a single scope (server OR global),
    with all 10 categories as embed fields arranged in an inline grid.

    Each field is a top-10 list using rank-medal emoji + bold name +
    monospaced value, kept under Discord's 1024-char-per-field cap."""
    embed = discord.Embed(
        title=f"{scope_emoji}  {scope_label}",
        description="*Top 10 per category — refreshed every hour.*",
        color=color,
    )

    for cat in LEADERBOARD_CATEGORIES:
        rows = gather_category_rows(cat, scope=scope, guild_id=guild_id, limit=10)
        if not rows:
            value = "_— no data yet —_"
        else:
            lines = []
            for idx, (player, val_str) in enumerate(rows, start=1):
                icon = _rank_icon(idx)
                name_clip = (player or "?")[:18]
                lines.append(f"{icon}  **{name_clip}** · `{val_str}`")
            value = "\n".join(lines)
            # Discord cap: 1024 chars per field
            if len(value) > 1020:
                value = value[:1020] + "…"
        embed.add_field(name=cat["title"], value=value, inline=True)

    embed.set_footer(text="Wandering Bot Alpha — Live Leaderboard")
    embed.timestamp = datetime.now(UTC)
    return style_embed(embed)


def build_mega_leaderboard_summary_embed():
    """Compact lead-in embed posted alongside the two scope embeds."""
    embed = discord.Embed(
        title="🏅 LIVE LEADERBOARDS — Server & Global",
        description=(
            "Auto-refreshes **every hour** — the previous post is deleted on each refresh.\n\n"
            "**🏠 Server** — top 10 on this server\n"
            "**🌍 Global** — top 10 across every Wandering Bot guild\n\n"
            "**Tracked:** ☠️ Kills · 💀 Deaths · ⏱️ Time Played · 🔨 Builds · "
            "🔫 Kill Streak · 🎯 Longest Shot · 🤬 Swearing · 🚩 Flags · "
            "🐺 Animal Deaths · 🧟 Zombie Deaths"
        ),
        color=0xE67E22,
    )
    embed.set_footer(text="Wandering Bot Alpha — Live Leaderboard • hourly")
    embed.timestamp = datetime.now(UTC)
    return style_embed(embed)


async def post_or_update_mega_leaderboard(guild_id, config):
    """Delete the previous leaderboard message(s) and post a fresh one
    with three stacked embeds: summary header + Server scope + Global
    scope. Runs hourly."""
    channels = config.get("channels", {})
    ch_id = channels.get("mega_leaderboard")
    if not ch_id:
        return False, "no channel configured"
    channel = bot.get_channel(ch_id)
    if not channel:
        return False, "channel not found"

    # ── Delete previous bot messages we tracked ─────────────────
    last_ids = last_mega_leaderboard_message_ids.get(str(guild_id), [])
    for mid in last_ids:
        try:
            old = await channel.fetch_message(mid)
            await old.delete()
        except Exception:
            pass
    # Also sweep any stray bot leaderboard messages
    try:
        await purge_self_dashboard_messages(channel, limit=15)
    except Exception:
        pass

    guild_name = guild_configs.get(str(guild_id), {}).get("guild_name", "Server")

    summary_embed = build_mega_leaderboard_summary_embed()
    server_embed = build_scope_leaderboard_embed(
        guild_id, "server",
        f"{guild_name.upper()} — SERVER LEADERBOARD",
        "🏠", 0x9B59B6,
    )
    global_embed = build_scope_leaderboard_embed(
        guild_id, "global",
        "GLOBAL LEADERBOARD — ALL SERVERS",
        "🌍", 0xF1C40F,
    )

    # Discord allows up to 10 embeds per message — three is fine.
    try:
        sent = await channel.send(embeds=[summary_embed, server_embed, global_embed])
    except Exception as send_err:
        print(f"[MEGA LEADERBOARD] send failed: {send_err}")
        return False, f"send failed: {send_err}"

    try:
        await sent.pin()
    except Exception:
        pass

    last_mega_leaderboard_message_ids[str(guild_id)] = [sent.id]
    return True, "posted"


@tasks.loop(hours=1)
async def mega_leaderboard_loop():
    for guild_id, config in active_guild_config_items():
        try:
            await post_or_update_mega_leaderboard(guild_id, config)
        except Exception as error:
            print(f"[MEGA LEADERBOARD] {guild_id} failed: {error}")


leaderboard_group = app_commands.Group(
    name="leaderboard",
    description="Live auto-updating leaderboard (bounty hunters, streaks, rampages)",
)


@leaderboard_group.command(name="setup", description="Set the channel for the live leaderboard message")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Channel where the auto-updating leaderboard message lives (defaults to current channel)")
async def slash_leaderboard_setup(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    target = channel or interaction.channel
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(
        guild_id, {"guild_name": interaction.guild.name, "channels": {}}
    )
    config.setdefault("channels", {})["mega_leaderboard"] = target.id
    # Reset cached message id so we post a brand-new pinned message
    last_mega_leaderboard_message_ids.pop(guild_id, None)
    save_guild_configs()
    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, info = await post_or_update_mega_leaderboard(guild_id, config)
    if ok:
        await interaction.followup.send(
            f"✅ Live leaderboard set up in {target.mention}. "
            f"It will refresh **every hour** automatically (deletes the old "
            f"message and posts a fresh **Server + Global** leaderboard).",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            f"⚠️ Channel saved but initial post failed: `{info}`. "
            f"It will retry on the next refresh tick.",
            ephemeral=True,
        )


@leaderboard_group.command(name="refresh", description="Force-refresh the live leaderboard now")
@app_commands.default_permissions(administrator=True)
async def slash_leaderboard_refresh(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id, {})
    if not config.get("channels", {}).get("mega_leaderboard"):
        await interaction.response.send_message(
            "No live-leaderboard channel set. Run `/leaderboard setup` first.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, info = await post_or_update_mega_leaderboard(guild_id, config)
    await interaction.followup.send(
        f"✅ Refreshed (`{info}`)." if ok else f"❌ Refresh failed: `{info}`",
        ephemeral=True,
    )


@leaderboard_group.command(name="unset", description="Disable the live leaderboard for this guild")
@app_commands.default_permissions(administrator=True)
async def slash_leaderboard_unset(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id, {})
    channels = config.get("channels", {})
    if "mega_leaderboard" in channels:
        channels.pop("mega_leaderboard", None)
        save_guild_configs()
        last_mega_leaderboard_message_ids.pop(guild_id, None)
        await interaction.response.send_message(
            "✅ Live leaderboard disabled. The pinned message will stop updating "
            "(you can delete it manually whenever you like).",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "Live leaderboard wasn't configured for this guild.",
            ephemeral=True,
        )


@leaderboard_group.command(name="hall", description="🏅 All-time Hall of Fame for this server")
async def slash_leaderboard_hall(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    gid = str(guild_id)

    embed = discord.Embed(
        title="🏅 SERVER HALL OF FAME",
        description="The greatest moments this server has ever seen.",
        color=0xF1C40F,
    )

    # Longest shot ever
    all_shots = longshot_records.get(gid, [])
    if all_shots:
        top = all_shots[0]
        embed.add_field(
            name="🎯 Longest Shot Ever",
            value=(
                f"**{top.get('killer', '?')}** dropped **{top.get('victim', '?')}**\n"
                f"at **{float(top.get('distance', 0) or 0):.1f}m** with **{top.get('weapon', '?')}**"
            ),
            inline=False,
        )

    # Biggest rampage ever (career multikill_best)
    rampage_rows = sorted(
        [(p, s) for p, s in player_stats.items() if str(s.get("guild_id", "")) == gid],
        key=lambda row: int(row[1].get("multikill_best", 0) or 0),
        reverse=True,
    )
    if rampage_rows and int(rampage_rows[0][1].get("multikill_best", 0) or 0) > 0:
        p, s = rampage_rows[0]
        embed.add_field(
            name="🔥 Biggest Rampage",
            value=f"**{p}** — **{int(s.get('multikill_best', 0))}** kills in 60s",
            inline=True,
        )

    # Longest survival streak ever
    streak_rows = sorted(
        ((survival_streaks.get(gid) or {}).items()),
        key=lambda row: int(row[1].get("longest_days", 0) or 0),
        reverse=True,
    )
    if streak_rows and int(streak_rows[0][1].get("longest_days", 0) or 0) > 0:
        p, s = streak_rows[0]
        embed.add_field(
            name="🩸 Longest Survival",
            value=f"**{p}** — **{int(s.get('longest_days', 0))}** days",
            inline=True,
        )

    # Top all-time bounty hunter
    bh_rows = sorted(
        [(p, s) for p, s in player_stats.items() if str(s.get("guild_id", "")) == gid and int(s.get("bounty_earnings", 0) or 0) > 0],
        key=lambda row: int(row[1].get("bounty_earnings", 0) or 0),
        reverse=True,
    )
    if bh_rows:
        p, s = bh_rows[0]
        embed.add_field(
            name="💰 Top Bounty Hunter",
            value=f"**{p}** — **{int(s.get('bounty_earnings', 0)):,} {BOUNTY_CURRENCY}**",
            inline=True,
        )

    # Top kill-spree ever
    spree_rows = sorted(
        (alive_streaks.get(gid) or {}).items(),
        key=lambda row: int(row[1].get("best_spree", 0) or 0),
        reverse=True,
    )
    if spree_rows and int(spree_rows[0][1].get("best_spree", 0) or 0) > 0:
        p, s = spree_rows[0]
        embed.add_field(
            name="🔫 Longest Kill Spree",
            value=f"**{p}** — **{int(s.get('best_spree', 0))}** kills without dying",
            inline=True,
        )

    # Most kills all-time
    kill_rows = sorted(
        [(p, s) for p, s in player_stats.items() if str(s.get("guild_id", "")) == gid],
        key=lambda row: int(row[1].get("kills", 0) or 0),
        reverse=True,
    )
    if kill_rows and int(kill_rows[0][1].get("kills", 0) or 0) > 0:
        p, s = kill_rows[0]
        embed.add_field(
            name="☠️ Most PvP Kills",
            value=f"**{p}** — **{int(s.get('kills', 0))}** kills",
            inline=True,
        )

    # Top headhunter
    hs_rows = sorted(
        [(p, s) for p, s in player_stats.items() if str(s.get("guild_id", "")) == gid],
        key=lambda row: int(row[1].get("headshots", 0) or 0),
        reverse=True,
    )
    if hs_rows and int(hs_rows[0][1].get("headshots", 0) or 0) > 0:
        p, s = hs_rows[0]
        embed.add_field(
            name="💥 Most Headshots",
            value=f"**{p}** — **{int(s.get('headshots', 0))}** HS",
            inline=True,
        )

    if not embed.fields:
        embed.description = "No legendary moments recorded yet. Go make some history."

    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha — Hall of Fame")
    embed.timestamp = datetime.now(UTC)
    await interaction.response.send_message(embed=style_embed(embed))


@leaderboard_group.command(name="challenges", description="🎯 See today's daily challenge + progress")
async def slash_leaderboard_challenges(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    state = get_or_roll_daily_challenge(guild_id)
    ch = state.get("challenge") or {}
    completed_by = state.get("completed_by") or []
    progress = state.get("progress") or {}

    embed = discord.Embed(
        title=f"🎯 DAILY CHALLENGE — {state.get('date', '')}",
        description=f"**{ch.get('name', '?')}** — *{ch.get('desc', '')}*",
        color=0x2ECC71,
    )
    embed.add_field(name="🏆 Reward", value=f"{int(ch.get('reward', 0)):,} Pennies", inline=True)
    embed.add_field(name="🎯 Target", value=str(ch.get("target", "?")), inline=True)
    embed.add_field(name="✅ Completed by", value=str(len(completed_by)), inline=True)

    if completed_by:
        embed.add_field(
            name="🥇 Finishers",
            value=", ".join(f"`{p}`" for p in completed_by[:10]),
            inline=False,
        )

    # Top in-progress (not yet completed)
    leaderboard = [
        (p, n) for p, n in progress.items()
        if p not in completed_by and int(n or 0) > 0
    ]
    leaderboard.sort(key=lambda x: int(x[1] or 0), reverse=True)
    if leaderboard:
        embed.add_field(
            name="📊 In Progress",
            value="\n".join(
                f"• `{p}` — {int(n)}/{ch.get('target', '?')}"
                for p, n in leaderboard[:5]
            ),
            inline=False,
        )

    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha — Daily Challenges")
    embed.timestamp = datetime.now(UTC)
    await interaction.response.send_message(embed=style_embed(embed))


bot.tree.add_command(leaderboard_group)


# =========================================================
# /recap — daily / weekly recap (manual)
# =========================================================

def _format_top(d, k=3):
    items = sorted((d or {}).items(), key=lambda x: x[1], reverse=True)[:k]
    return ", ".join(f"`{name}` ({n})" for name, n in items) if items else "—"


def build_recap_embed(guild_id, day_key, *, title_prefix="📰 DAILY RECAP"):
    gid = str(guild_id)
    bucket = (daily_recap_data.get(gid) or {}).get(day_key)
    embed = discord.Embed(
        title=f"{title_prefix} — {day_key}",
        color=0x3498DB,
    )
    if not bucket or not bucket.get("total_kills"):
        embed.description = "No PvP kills recorded for this date."
        embed.set_thumbnail(url=BOT_IMAGE)
        embed.timestamp = datetime.now(UTC)
        return style_embed(embed)
    total = bucket.get("total_kills", 0)
    hs = bucket.get("headshots", 0)
    veh = bucket.get("vehicle_kills", 0)
    hs_rate = round((hs / total) * 100, 1) if total else 0
    biggest = bucket.get("biggest_shot") or {}
    embed.description = (
        f"**{total}** kills • **{hs}** headshots ({hs_rate}%) • **{veh}** vehicle kills"
    )
    embed.add_field(name="🏆 Top Killers", value=_format_top(bucket.get("killers"), 3), inline=False)
    embed.add_field(name="🔫 Deadliest Weapons", value=_format_top(bucket.get("weapons"), 3), inline=False)
    embed.add_field(name="📍 Deadliest Zones", value=_format_top(bucket.get("zones"), 3), inline=False)
    if biggest and biggest.get("distance"):
        embed.add_field(
            name="🎯 Biggest Shot",
            value=f"**{biggest.get('killer', '?')}** → {biggest.get('victim', '?')} • {float(biggest.get('distance', 0)):.0f}m ({biggest.get('weapon', '?')})",
            inline=False,
        )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha — Daily Recap")
    embed.timestamp = datetime.now(UTC)
    return style_embed(embed)


def build_weekly_recap_embed(guild_id):
    gid = str(guild_id)
    today = datetime.now(UTC).date()
    keys = [(today - timedelta(days=i)).isoformat() for i in range(7)]
    agg = {"total_kills": 0, "headshots": 0, "vehicle_kills": 0,
           "killers": {}, "weapons": {}, "zones": {},
           "biggest_shot": {"distance": 0}}
    for key in keys:
        bucket = (daily_recap_data.get(gid) or {}).get(key)
        if not bucket:
            continue
        agg["total_kills"] += int(bucket.get("total_kills", 0) or 0)
        agg["headshots"] += int(bucket.get("headshots", 0) or 0)
        agg["vehicle_kills"] += int(bucket.get("vehicle_kills", 0) or 0)
        for k, v in (bucket.get("killers") or {}).items():
            agg["killers"][k] = agg["killers"].get(k, 0) + v
        for k, v in (bucket.get("weapons") or {}).items():
            agg["weapons"][k] = agg["weapons"].get(k, 0) + v
        for k, v in (bucket.get("zones") or {}).items():
            agg["zones"][k] = agg["zones"].get(k, 0) + v
        big = bucket.get("biggest_shot") or {}
        if float(big.get("distance", 0) or 0) > float(agg["biggest_shot"].get("distance", 0) or 0):
            agg["biggest_shot"] = big

    embed = discord.Embed(
        title=f"📰 WEEKLY RECAP — last 7 days",
        color=0x2980B9,
        description=(
            f"**{agg['total_kills']}** kills • **{agg['headshots']}** headshots • "
            f"**{agg['vehicle_kills']}** vehicle kills"
        ),
    )
    embed.add_field(name="🏆 Top Killers", value=_format_top(agg["killers"], 5), inline=False)
    embed.add_field(name="🔫 Deadliest Weapons", value=_format_top(agg["weapons"], 5), inline=False)
    embed.add_field(name="📍 Deadliest Zones", value=_format_top(agg["zones"], 5), inline=False)
    big = agg.get("biggest_shot") or {}
    if big and big.get("distance"):
        embed.add_field(
            name="🎯 Biggest Shot of the Week",
            value=f"**{big.get('killer', '?')}** → {big.get('victim', '?')} • {float(big.get('distance', 0)):.0f}m ({big.get('weapon', '?')})",
            inline=False,
        )
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha — Weekly Recap")
    embed.timestamp = datetime.now(UTC)
    return style_embed(embed)


@extra_tools_group.command(name="recap", description="Show the daily or weekly server recap")
@app_commands.describe(period="today / yesterday / week")
@app_commands.choices(period=[
    app_commands.Choice(name="today", value="today"),
    app_commands.Choice(name="yesterday", value="yesterday"),
    app_commands.Choice(name="week", value="week"),
])
async def slash_recap(interaction: discord.Interaction, period: app_commands.Choice[str] = None):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    period_value = period.value if period else "today"
    if period_value == "week":
        embed = build_weekly_recap_embed(guild_id)
    elif period_value == "yesterday":
        embed = build_recap_embed(guild_id, _yesterday_key(), title_prefix="📰 RECAP")
    else:
        embed = build_recap_embed(guild_id, _today_key(), title_prefix="📰 TODAY SO FAR")
    await interaction.response.send_message(embed=embed)


# =========================================================
# AI News Bulletin
# =========================================================

async def generate_news_bulletin(guild_name, day_key, bucket):
    """Use Emergent LLM key to produce a short Reuters-style bulletin
    summarizing the day. Falls back to a deterministic template."""
    if not bucket or not bucket.get("total_kills"):
        return None
    top_killer = max((bucket.get("killers") or {}).items(), key=lambda x: x[1], default=("?", 0))
    top_weapon = max((bucket.get("weapons") or {}).items(), key=lambda x: x[1], default=("?", 0))
    top_zone = max((bucket.get("zones") or {}).items(), key=lambda x: x[1], default=("?", 0))
    big = bucket.get("biggest_shot") or {}
    fallback = (
        f"**{guild_name} — {day_key}.** {bucket['total_kills']} kills on the books. "
        f"`{top_killer[0]}` led the leaderboard ({top_killer[1]}). "
        f"`{top_weapon[0]}` was the weapon of choice. "
        f"`{top_zone[0]}` ran red. "
        + (f"Longest confirmed shot: {float(big.get('distance', 0)):.0f}m by `{big.get('killer','?')}`."
           if big.get("distance") else "")
    )
    if not EMERGENT_LLM_KEY:
        return fallback
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as error:
        print(f"[NEWS] emergentintegrations import failed: {error}")
        return fallback
    prompt = (
        "Write a 2-3 sentence dry, Reuters-style news bulletin summarising today's DayZ killfeed. "
        "No emojis, no markdown bold. Reference at least one player name and one zone.\n\n"
        f"Server: {guild_name}\nDate: {day_key}\n"
        f"Total kills: {bucket['total_kills']}\nHeadshots: {bucket['headshots']}\n"
        f"Vehicle kills: {bucket['vehicle_kills']}\n"
        f"Top killer: {top_killer[0]} ({top_killer[1]} kills)\n"
        f"Deadliest weapon: {top_weapon[0]}\n"
        f"Deadliest zone: {top_zone[0]}\n"
        f"Biggest shot: {float(big.get('distance', 0)):.0f}m by {big.get('killer', '?')} on {big.get('victim', '?')}\n"
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"news-{day_key}-{guild_name[:20]}",
            system_message="You are a deadpan post-apocalyptic newsreader. Keep it dry and short.",
        ).with_model(AI_ROAST_PROVIDER, AI_ROAST_MODEL)
        response = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=15)
        text = (str(response or "")).strip().strip('"').strip("'")
        return text or fallback
    except Exception as error:
        print(f"[NEWS] LLM bulletin failed ({error}) — using fallback")
        return fallback


# =========================================================
# Daily recap loop — runs hourly, posts at RECAP_DAILY_HOUR_UTC
# =========================================================

def _recap_target_channel(guild_id):
    config = guild_configs.get(str(guild_id), {})
    channels = config.get("channels", {})
    ch = channels.get("recap") or channels.get("killfeed") or channels.get("general_chat")
    return bot.get_channel(ch) if ch else None


@tasks.loop(minutes=30)
async def recap_loop():
    """Every 30 minutes, check every active guild — if today's recap hour
    has been reached and we haven't posted yet for yesterday, post it."""
    try:
        now = datetime.now(UTC)
        if now.hour != RECAP_DAILY_HOUR_UTC and now.hour != (RECAP_DAILY_HOUR_UTC + 1) % 24:
            return
        yesterday = _yesterday_key(now)
        for guild_id, config in active_guild_config_items():
            try:
                if recap_posted.get(str(guild_id)) == yesterday:
                    continue
                channel = _recap_target_channel(guild_id)
                if not channel:
                    continue
                bucket = (daily_recap_data.get(str(guild_id)) or {}).get(yesterday)
                if not bucket:
                    recap_posted[str(guild_id)] = yesterday
                    save_recap_posted()
                    continue
                recap_embed = build_recap_embed(guild_id, yesterday, title_prefix="📰 DAILY RECAP")
                await channel.send(embed=recap_embed)
                if NEWS_BULLETIN_ENABLED:
                    bulletin = await generate_news_bulletin(
                        guild_display_name(guild_id), yesterday, bucket
                    )
                    if bulletin:
                        news_embed = discord.Embed(
                            title="📡 SURVIVOR NEWS BULLETIN",
                            description=bulletin,
                            color=0x7F8C8D,
                        )
                        news_embed.set_footer(text=f"Wandering Bot Alpha — News • {yesterday}")
                        news_embed.timestamp = datetime.now(UTC)
                        await channel.send(embed=style_embed(news_embed))
                recap_posted[str(guild_id)] = yesterday
                save_recap_posted()
            except Exception as guild_err:
                print(f"[RECAP LOOP] guild {guild_id} failed: {guild_err}")
    except Exception as error:
        print(f"[RECAP LOOP] top-level error: {error}")


# =========================================================
# /spectator — live snapshot of online players + recent kills
# =========================================================

@extra_tools_group.command(name="spectator", description="Live snapshot: who's online + recent kills + active hotspots")
async def slash_spectator(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    online = sorted(online_players.get(guild_id, set()))
    locations = player_last_coords.get(guild_id, {})
    embed = discord.Embed(
        title="📡 LIVE SPECTATOR FEED",
        description=f"**{len(online)}** survivor(s) online right now.",
        color=0x1ABC9C,
    )
    # Online + last known zone
    lines = []
    for player in online[:20]:
        coord_record = locations.get(player) or {}
        zone_text = coord_record.get("zone") or coord_record.get("zone_name") or "Unknown"
        lines.append(f"• `{player}` — {zone_text}")
    if lines:
        embed.add_field(name="🟢 Online", value="\n".join(lines), inline=False)
    # Recent kills (last 90s)
    now_ts = datetime.now(UTC).timestamp()
    ev_deque = recent_kill_events.get(guild_id, [])
    fresh = [e for e in ev_deque if now_ts - e.get("ts", 0) <= 600][-10:]
    if fresh:
        embed.add_field(
            name="☠️ Recent Kills (last 10 mins)",
            value="\n".join(f"• `{e['killer']}` → `{e['victim']}` ({e.get('weapon','?')}) in *{e.get('zone','?')}*" for e in fresh),
            inline=False,
        )
    # Today's hot zone
    today_bucket = (daily_recap_data.get(guild_id) or {}).get(_today_key()) or {}
    zones = today_bucket.get("zones") or {}
    if zones:
        embed.add_field(name="🔥 Today's Hot Zone", value=_format_top(zones, 1), inline=True)
    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering Bot Alpha — Live Spectator")
    embed.timestamp = datetime.now(UTC)
    await interaction.response.send_message(embed=style_embed(embed))


# =========================================================
# /sendmessage — Nitrado in-game broadcast (best-effort REST)
# =========================================================

def nitrado_send_chat(config, message):
    """Best-effort: POST to Nitrado's gameserver chat endpoint. If the
    endpoint or token isn't authorised, returns (False, error_message)."""
    token = config.get("nitrado_token")
    service_id = config.get("service_id")
    if not token or not service_id:
        return False, "Missing nitrado_token / service_id in guild config."
    url = f"https://api.nitrado.net/services/{service_id}/gameservers/games/dayz/chat"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            data={"message": message},
            timeout=10,
        )
        if resp.status_code in (200, 201, 204):
            return True, "Sent."
        return False, f"Nitrado returned HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as error:
        return False, f"Request failed: {error}"


@extra_tools_group.command(name="reloadguilds", description="Admin: reload saved guild configs after redeploy")
@app_commands.default_permissions(administrator=True)
async def slash_reloadguilds(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "reloadguilds")
@bot.tree.command(name="restartadm", description="Admin: restart and run the ADM feed")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(force="Reprocess recent ADM lines")
async def slash_restartadm(interaction: discord.Interaction, force: bool = False):
    await run_legacy_as_slash(interaction, "restartadm", force="force" if force else "no")
@bot.tree.command(name="restartserver", description="Restart server")
@app_commands.default_permissions(administrator=True)
async def slash_restartserver(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "restartserver")


# =========================================================
# /server group — server admin (restarts, base damage, in-game chat)
# =========================================================

server_group = app_commands.Group(
    name="server",
    description="DayZ server admin tools (restart schedule, base damage, in-game chat)",
)


@server_group.command(name="togglebasedamage", description="Toggle base damage on/off via Nitrado")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(state="on or off")
async def slash_server_togglebasedamage(interaction: discord.Interaction, state: str):
    await run_legacy_as_slash(interaction, "togglebasedamage", state=state)


@server_group.command(name="setrestartinterval", description="Set the server restart interval (hours)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(hours="Hours 1-24")
async def slash_server_setrestartinterval(interaction: discord.Interaction, hours: int):
    await run_legacy_as_slash(interaction, "setrestartinterval", hours=hours)


@server_group.command(name="setrestartstart", description="Set the first daily restart hour (UTC)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(hour="Hour 0-23")
async def slash_server_setrestartstart(interaction: discord.Interaction, hour: int):
    await run_legacy_as_slash(interaction, "setrestartstart", hour=hour)


@server_group.command(name="cancelrestarts", description="Disable the recurring server restart schedule")
@app_commands.default_permissions(administrator=True)
async def slash_server_cancelrestarts(interaction: discord.Interaction):
    await run_legacy_as_slash(interaction, "cancelrestarts")


@server_group.command(name="listrestarts", description="List the current restart schedule")
@app_commands.default_permissions(administrator=True)
async def slash_server_listrestarts(interaction: discord.Interaction):
    await run_legacy_as_slash(interaction, "listrestarts")


@server_group.command(name="sendmessage", description="Admin: broadcast a chat message into the live DayZ server")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(message="Text to broadcast in-game (max 240 chars)")
async def slash_server_sendmessage(interaction: discord.Interaction, message: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id) if interaction.guild else ""
    config = guild_configs.get(guild_id, {})
    text = message.strip()[:240]
    if not text:
        await interaction.response.send_message("Message cannot be empty.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, info = await asyncio.to_thread(nitrado_send_chat, config, text)
    if ok:
        await interaction.followup.send(f"📡 Broadcast sent: `{text}`", ephemeral=True)
    else:
        await interaction.followup.send(
            "❌ Could not send in-game broadcast.\n"
            f"```\n{info}\n```\n"
            "Note: some Nitrado plans / consoles do not expose the chat endpoint.",
            ephemeral=True,
        )


bot.tree.add_command(server_group)
@bot.tree.command(name="buy", description="Buy an item and queue delivery")
@app_commands.describe(item_name="Item", x="Map X", y="Map Y")
async def slash_buy(interaction: discord.Interaction, item_name: str, x: str, y: str): await run_legacy_as_slash(interaction, "buy", item_name=item_name, x=x, y=y)
def auto_fetch_types_xml_from_server(config, guild_id):
    """Try every standard Nitrado console & PC types.xml path and return
    (success, message, local_temp_path) on the first hit.

    The caller is responsible for cleaning up the parent temp directory
    of `local_temp_path` once they're done with it.
    """
    map_key = server_map_key(guild_id) if guild_id else None
    missions = map_mission_folder_names(map_key) if map_key else [
        "dayzOffline.chernarusplus",
        "dayzOffline.enoch",
        "dayzOffline.sakhal",
        "dayzOffline.sakhalplus",
        "dayzOffline.namalsk",
    ]
    roots = [
        "/dayzxb_missions",
        "/dayzxb/mpmissions",
        "/dayzps_missions",
        "/dayzps/mpmissions",
        "/mpmissions",
    ]
    tried = []
    for root in roots:
        for mission in missions:
            remote = f"{root}/{mission}/db/types.xml"
            tried.append(remote)
            ok, msg, content = download_text_file_from_nitrado(config, remote)
            if ok and content and "<types>" in content and "<type " in content:
                tmp_dir = tempfile.mkdtemp(prefix="wb_typesxml_auto_")
                local = os.path.join(tmp_dir, "types.xml")
                try:
                    with open(local, "w", encoding="utf-8") as fh:
                        fh.write(content)
                except Exception as write_err:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return False, f"Found types.xml at {remote} but failed to save: {write_err}", None
                return True, remote, local
    return False, "Tried " + ", ".join(tried[:6]) + (f" (+{len(tried)-6} more)" if len(tried) > 6 else ""), None


@extra_tools_group.command(name="importtypesxml", description="Admin: auto-import your server's types.xml into the shop")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    types_file="(optional) Attach a types.xml file directly. Leave blank to auto-pull from your Nitrado server.",
    default_price="Fallback price for items with no price set (default 100)",
    source_path="(advanced) Server-side filesystem path to a types.xml — only useful if you've SSH'd one onto the bot host",
)
async def slash_importtypesxml(
    interaction: discord.Interaction,
    types_file: discord.Attachment = None,
    default_price: int = 100,
    source_path: str = None,
):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    guild_id = str(interaction.guild.id) if interaction.guild else None
    config = guild_configs.get(guild_id, {}) if guild_id else {}

    resolved_source = None
    cleanup_dir = None
    source_label = None

    # ── 1) Admin-attached file (priority — overrides everything) ──
    if types_file:
        if not types_file.filename.lower().endswith(".xml"):
            await interaction.followup.send(
                f"❌ `{types_file.filename}` doesn't look like an XML file. Attach a `types.xml` (or any `*.xml`) and try again.",
                ephemeral=True
            )
            return
        if types_file.size > 50 * 1024 * 1024:
            await interaction.followup.send(
                f"❌ `{types_file.filename}` is {types_file.size // (1024*1024)} MB — too big for a types.xml.",
                ephemeral=True
            )
            return
        try:
            cleanup_dir = tempfile.mkdtemp(prefix="wb_typesxml_upload_")
            resolved_source = os.path.join(cleanup_dir, types_file.filename)
            await types_file.save(resolved_source)
            source_label = f"Discord attachment ({types_file.filename})"
        except Exception as download_err:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)
            await interaction.followup.send(
                f"❌ Failed to download the attached file: `{download_err}`",
                ephemeral=True
            )
            return

    # ── 2) Auto-pull from Nitrado (PRIMARY automatic path) ──
    elif not source_path:
        ok, msg_or_path, local_path = await asyncio.to_thread(
            auto_fetch_types_xml_from_server, config, guild_id
        )
        if ok:
            resolved_source = local_path
            cleanup_dir = os.path.dirname(local_path)
            source_label = f"Nitrado: `{msg_or_path}`"
        else:
            await interaction.followup.send(
                "❌ Couldn't auto-fetch `types.xml` from your Nitrado server.\n\n"
                f"Tried these paths: {msg_or_path}\n\n"
                "Three options to fix this:\n"
                "1. Make sure Nitrado API/FTP is set up in your guild config (`/setup`)\n"
                "2. Re-run this command and **attach** your `types.xml` to the `types_file` option\n"
                "3. SSH a `types.xml` next to the bot and re-run with the `source_path` option",
                ephemeral=True
            )
            return

    # ── 3) Manual source_path fallback ──
    else:
        resolved_source = source_path
        source_label = f"local path: `{source_path}`"

    # ── Run the import ──
    try:
        added, updated, types_path = await asyncio.to_thread(
            load_shop_items_from_types_xml,
            resolved_source,
            default_price,
            False
        )
    except Exception as import_err:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)
        await interaction.followup.send(
            f"❌ Import failed while parsing the XML: `{import_err}`",
            ephemeral=True
        )
        return

    if cleanup_dir:
        shutil.rmtree(cleanup_dir, ignore_errors=True)

    if not types_path:
        await interaction.followup.send(
            "❌ The file was reachable but contained no parseable `<type>` entries.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🛒 TYPES.XML IMPORTED TO SHOP",
        description=f"**Source:** {source_label}",
        color=0x2ECC71
    )
    embed.add_field(name="Items Added", value=str(added), inline=True)
    embed.add_field(name="Items Updated", value=str(updated), inline=True)
    embed.add_field(name="Total Shop Items", value=str(len(shop_items)), inline=True)
    embed.add_field(
        name="Default Price",
        value=f"`{default_price}` pennies (applied to items without a price in types.xml)",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.followup.send(embed=style_embed(embed), ephemeral=False)
@bot.tree.command(name="addshopitem", description="Admin: add an item to the shop")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(item_name="Item classname", price="Price in pennies", category="Shop category")
async def slash_addshopitem(interaction: discord.Interaction, item_name: str, price: int, category: str = "General"):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "addshopitem", item_name=item_name, price=price, category=category)
@bot.tree.command(name="editshopitem", description="Admin: edit a shop item")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(item_name="Item classname", price="Optional new price", category="Optional new category")
async def slash_editshopitem(interaction: discord.Interaction, item_name: str, price: int = None, category: str = None):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "editshopitem", item_name=item_name, price=price, category=category)
@bot.tree.command(name="toggleshopitem", description="Admin: enable or disable a shop item")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(item_name="Item classname")
async def slash_toggleshopitem(interaction: discord.Interaction, item_name: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "toggleshopitem", item_name=item_name)
@bot.tree.command(name="removeshopitem", description="Admin: remove an item from the shop")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(item_name="Item classname")
async def slash_removeshopitem(interaction: discord.Interaction, item_name: str):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "removeshopitem", item_name=item_name)
@bot.tree.command(name="givepennies", description="Admin: give pennies to a member")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(member="Discord member", amount="Pennies to add")
async def slash_givepennies(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "givepennies", member=member, amount=amount)
@extra_tools_group.command(name="shopcategories", description="Show shop categories")
async def slash_shopcategories(interaction: discord.Interaction):
    await run_legacy_as_slash(interaction, "shopcategories")
@extra_tools_group.command(name="channelstatus", description="Admin: show bot channels disabled by deletion")
@app_commands.default_permissions(administrator=True)
async def slash_channelstatus(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    disabled = sorted(disabled_channel_keys(config))
    if disabled:
        text = "\n".join(f"`{key}` - {DEFAULT_CHANNEL_NAMES.get(key, key)}" for key in disabled)
    else:
        text = "No bot channels are currently marked as owner-deleted."
    await interaction.response.send_message(text[:1900], ephemeral=True)
@extra_tools_group.command(name="channelpacks", description="Admin: show channel restore packs")
@app_commands.default_permissions(administrator=True)
async def slash_channelpacks(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.send_message(format_channel_restore_packs(), ephemeral=True)
@extra_tools_group.command(name="restorechannels", description="Admin: restore owner-deleted bot channels")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel_key="Optional bot channel key to restore, or leave blank for all deleted bot channels")
async def slash_restorechannels(interaction: discord.Interaction, channel_key: str = None):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    restored, error = await restore_disabled_bot_channels(interaction.guild, config, channel_key)
    if error:
        await interaction.followup.send(error, ephemeral=True)
        return
    if not restored:
        await interaction.followup.send("No deleted bot channels needed restoring.", ephemeral=True)
        return
    await interaction.followup.send("Restored:\n" + "\n".join(restored[:30]), ephemeral=True)
@extra_tools_group.command(name="restorechannelpack", description="Admin: restore a pack of bot channels")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(pack="Channel pack to restore")
@app_commands.choices(pack=[
    app_commands.Choice(name="all", value="all"),
    app_commands.Choice(name="pve", value="pve"),
    app_commands.Choice(name="live", value="live"),
    app_commands.Choice(name="staff", value="staff"),
    app_commands.Choice(name="economy", value="economy"),
    app_commands.Choice(name="factions", value="factions"),
    app_commands.Choice(name="community", value="community"),
    app_commands.Choice(name="info", value="info"),
])
async def slash_restorechannelpack(interaction: discord.Interaction, pack: app_commands.Choice[str]):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    config = guild_configs.setdefault(str(interaction.guild.id), {"guild_name": interaction.guild.name, "channels": {}})
    pack_key = pack.value
    keys = CHANNEL_RESTORE_PACKS.get(pack_key)
    if not keys:
        await interaction.followup.send(f"Unknown channel pack `{pack_key}`.", ephemeral=True)
        return

    restored, error = await restore_disabled_bot_channels(interaction.guild, config, channel_keys=keys)
    if error:
        await interaction.followup.send(error, ephemeral=True)
        return
    if not restored:
        await interaction.followup.send(f"No `{pack_key}` channels needed restoring.", ephemeral=True)
        return
    await interaction.followup.send(
        f"Restored `{pack_key}` channel pack:\n" + "\n".join(restored[:30]),
        ephemeral=True
    )
bot.tree.add_command(extra_tools_group)
@extra_tools_group.command(name="rentvehicle", description="Rent a vehicle")
@app_commands.describe(vehicle_name="Vehicle", rental_hours="Hours", x="Map X", y="Map Y")
async def slash_rentvehicle(interaction: discord.Interaction, vehicle_name: str, rental_hours: int, x: str, y: str): await run_legacy_as_slash(interaction, "rentvehicle", vehicle_name=vehicle_name, rental_hours=rental_hours, x=x, y=y)
@extra_tools_group.command(name="resetvehicle", description="Admin: reset a vehicle at a spawn position on next restart")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(vehicle_name="DayZ vehicle class name", x="Map X", y="Map Y", radius="Delete matching old vehicles within this many meters")
async def slash_resetvehicle(interaction: discord.Interaction, vehicle_name: str, x: str, y: str, radius: int = 35):
    await run_legacy_as_slash(interaction, "resetvehicle", vehicle_name=vehicle_name, x=x, y=y, radius=radius)
@extra_tools_group.command(name="resetvehicles", description="Admin: reset all vehicles on next restart, with optional exclusions")
@app_commands.default_permissions(administrator=True)
async def slash_resetvehicles(interaction: discord.Interaction):
    if not has_interaction_admin_power(interaction):
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    vehicle_classes = known_vehicle_classes()
    excluded = vehicle_reset_exclusions(config)
    excluded_text = ", ".join(f"`{item}`" for item in excluded) or "None"

    embed = discord.Embed(
        title="ALL-VEHICLE RESET",
        description=(
            "This queues a map-wide vehicle cleanup for the next restart delivery run. "
            "You do not need to enter coordinates. Use the dropdown only for vehicle classes you want to leave alone."
        ),
        color=0xE67E22
    )
    embed.add_field(name="Detected Vehicle Options", value=str(len(vehicle_classes)), inline=True)
    embed.add_field(name="Current Exclusions", value=excluded_text[:1000], inline=False)
    embed.add_field(
        name="Before Using",
        value="Run `/installdayzbridge install:true` after this update so your server has the v5 bridge.",
        inline=False
    )
    embed.set_thumbnail(url=BOT_IMAGE)
    await interaction.response.send_message(
        embed=style_embed(embed),
        view=VehicleResetExcludeView(guild_id, config),
        ephemeral=True
    )

# =========================================================
# DAYZ INIT.C DELIVERY LOADER (NITRADO SIDE)
# =========================================================

# ADD THIS TO YOUR DAYZ SERVER init.c FILE
# This loads deliveries.xml on restart.
# Your bot already uploads the XML automatically.
# This is the final bridge.

'''
void SpawnWanderingDeliveries()
{
    string path = "$profile:custom/deliveries.xml";

    FileHandle file = OpenFile(path, FileMode.READ);

    if (!file)
    {
        Print("[WANDERING BOT] deliveries.xml not found");
        return;
    }

    string line;

    while (FGets(file, line) > 0)
    {
        if (line.Contains("<object"))
        {
            string itemName;
            string position;

            int nameStart = line.IndexOf("name=\"") + 6;
            int nameEnd = line.IndexOf("\"", nameStart);

            itemName = line.Substring(nameStart, nameEnd - nameStart);

            int posStart = line.IndexOf("pos=\"") + 5;
            int posEnd = line.IndexOf("\"", posStart);

            position = line.Substring(posStart, posEnd - posStart);

            TStringArray posSplit = new TStringArray;
            position.Split(" ", posSplit);

            if (posSplit.Count() >= 3)
            {
                vector spawnPos = Vector(
                    posSplit.Get(0).ToFloat(),
                    posSplit.Get(1).ToFloat(),
                    posSplit.Get(2).ToFloat()
                );

                EntityAI spawned = EntityAI.Cast(
                    GetGame().CreateObject(itemName, spawnPos)
                );

                if (spawned)
                {
                    Print("[WANDERING BOT] Spawned: " + itemName);
                }
            }
        }
    }

    CloseFile(file);
}

// =====================================================
// CALL THIS INSIDE main() AFTER WEATHER SETUP
// =====================================================

SpawnWanderingDeliveries();
'''

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")
    print(f"DATA ROOT: {os.path.abspath(DATA_ROOT)}")

    ensure_folder(DATA_ROOT)
    ensure_folder(GUILD_DATA_FOLDER)

    load_guild_configs()
    load_processed_adm_lines()
    bootstrap_runtime_from_connected_guilds()
    await repair_display_names_for_active_guilds()
    await ensure_pve_channels_for_active_guilds()
    load_player_stats()
    load_heatmap()
    load_swear_jar()
    load_linked_players()
    load_support_tickets()
    load_factions()
    load_pve_challenges()
    load_longshot_records()
    load_first_blood()
    load_daily_recap()
    load_bounties()
    load_survival_streaks()
    load_recap_posted()
    load_achievements()
    load_nemesis()
    load_alive_streaks()
    load_daily_challenges()
    load_wandering_emojis()
    print(f"WANDERING EMOJIS LOADED: {len(wandering_emojis)}")
    load_shop()
    load_wallets()
    load_delivery_queue()

    await publish_bot_updates_for_active_guilds()

    for guild_id, config in active_guild_config_items():
        try:
            if pve_config(config).get("enabled", True):
                posted = await ensure_pve_channel_quests(guild_id, config)
                if posted:
                    print(f"PVE QUEST SLOTS SEEDED {guild_display_name(guild_id)}: {len(posted)}")
        except Exception as error:
            print(f"PVE QUEST SLOT SEED ERROR {guild_id}: {error}")

    active_count = len(list(active_guild_config_items()))
    active_names = [
        guild_configs[guild_id].get("guild_name", guild_id)
        for guild_id, _ in active_guild_config_items()
    ]
    print(f"ACTIVE CONFIGURED GUILDS LOADED: {active_count}/{len(guild_configs)}")
    print(f"ACTIVE GUILDS: {', '.join(active_names) if active_names else 'none'}")

    await start_background_tasks()

    print("[ADM STARTUP] Starting ADM startup protocol for active guilds.")
    startup_results = await refresh_adm_feeds()
    log_adm_protocol_results(startup_results, "ADM STARTUP")

    global_commands = list(bot.tree.get_commands())

    for guild in bot.guilds:
        try:
            bot.tree.clear_commands(guild=guild)
            bot.tree.copy_global_to(guild=guild)
            guild_synced = await bot.tree.sync(guild=guild)
            guild_command_names = ", ".join(command.name for command in guild_synced)
            print(f"GUILD SLASH COMMANDS SYNCED {guild.name}: {len(guild_synced)}")
            print(f"GUILD SLASH COMMAND NAMES {guild.name}: {guild_command_names}")
        except Exception as sync_error:
            print(f"GUILD SLASH SYNC ERROR {guild.id}: {sync_error}")

    try:
        bot.tree.clear_commands(guild=None)
        cleared_global = await bot.tree.sync()
        print(f"GLOBAL SLASH COMMAND COPIES CLEARED: {len(cleared_global)}")
    except Exception as sync_error:
        print(f"GLOBAL SLASH CLEAR ERROR: {sync_error}")
    finally:
        for command in global_commands:
            try:
                bot.tree.add_command(command)
            except Exception:
                pass

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)
