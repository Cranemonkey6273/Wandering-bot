# =========================================================
# WANDERING BOT ALPHA - MULTI GUILD EDITION
# =========================================================

import os
import re
import json
import random
import hashlib
import asyncio
import requests
import tempfile
import xml.etree.ElementTree as ET
from ftplib import FTP_TLS
import discord

from datetime import datetime, UTC
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
SUPPORT_TICKETS_FILE = data_path("support_tickets.json")
WANDERING_EMOJIS_FILE = data_path("wandering_emojis.json")
FACTIONS_FILE = data_path("factions.json")

# =========================================================
# GLOBALS
# =========================================================

guild_configs = {}
processed_lines = {}
online_players = {}
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
longshot_records = {}
swear_jar = {}
player_chat_tracker = {}
linked_players = {}
last_funny_message_time = {}
last_funny_index = {}
last_emoji_showcase_time = {}
support_tickets = {}
wandering_emojis = {}
factions = {}
last_ai_direct_response_time = {}
last_owner_mention_time = {}

HEATMAP_MODES = [
    "pvp",
    "zombie",
    "cuts",
    "building",
    "raids",
    "flags",
    "suicide",
    "placed",
    "all"
]

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
    "cuts_feed": "🩸⚕️・injury-intel・⚕️🩸",
    "placed_feed": "🧰🏕️・placement-intel・🏕️🧰",
    "online": "✅🎮・online-survivors・🎮✅",
    "leaderboards": "🏆📊・leaderboards・📊🏆",
    "heatmap": "🔥🗺️・heatmap・🗺️🔥",
    "longshots": "🎯🏹・longshots・🏹🎯",
    "restart_alerts": "📢⏰・restart-alerts・⏰📢",
    "welcome": "👋🟩・welcome・🟩👋",
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
    "command_logs": "📜🛡️・command-logs・🛡️📜",
    "purchase_logs": "💳📦・purchase-logs・📦💳",
    "vehicle_rentals": "🚗💰・vehicle-rentals・💰🚗",
    "rental_logs": "🛻📒・rental-logs・📒🛻",
    "company_announcements": "📢・wandering-company-announcements・📢"
}

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
    "welcome": ["welcome", "newsurvivor"],
    "general_chat": ["survivorchat", "generalchat", "general", "chat"],
    "factions_chat": ["factionschat", "factions", "factionchat"],
    "faction_list": ["factionlist", "factionslist"],
    "help_channel": ["helpdesk", "help", "support"],
    "clips_channel": ["dayzclips", "clips", "media"],
    "economy": ["blackmarket", "economy", "shop", "market"],
    "ai_chat": ["survivorai", "aichat", "ai"],
    "admin_logs": ["adminlogs", "stafflogs"],
    "command_logs": ["commandlogs", "commands"],
    "purchase_logs": ["purchaselogs", "purchases"],
    "vehicle_rentals": ["vehiclerentals", "rentvehicles", "rentals"],
    "rental_logs": ["rentallogs"],
    "faction_tickets": ["factiontickets", "factionrequests"],
    "faction_staff": ["factionstaff"],
    "zombie_feed": ["zombiefeed", "infectedfeed", "zmbfeed", "zombies"],
    "unconscious_feed": ["unconsciousfeed", "medicalfeed", "unconscious"],
    "cuts_feed": ["cutsfeed", "injuryintel", "injuryfeed", "bleedoutfeed"],
    "placed_feed": ["placedfeed", "placementintel", "placementfeed", "buildplaced"],
    "company_announcements": ["wanderingcompanyannouncements", "companyannouncements"]
}

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


def resolve_guild_role(guild, role_name):
    wanted = str(role_name).strip().lower()

    for role in guild.roles:
        if role.name.lower() == wanted:
            return role

    return None


def extract_player_name(line):
    match = re.search(r'Player "([^"]+)"', line)
    return match.group(1) if match else "Unknown"


def extract_adm_coords(line):
    match = re.search(r"pos=<([^>]+)>", line)
    return match.group(1) if match else None


def build_adm_map_link(line):
    coords = extract_adm_coords(line)
    return build_izurvive_link(coords) if coords else None


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
    }.get(event_type)


def guild_heatmap_mode(guild_id):
    mode = guild_configs.get(str(guild_id), {}).get("heatmap_mode", "pvp")
    return mode if mode in HEATMAP_MODES else "pvp"


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


def map_coords_to_pixel(coords):
    try:
        x_text, y_text = coords.split(",")[:2]
        x = float(x_text.strip())
        y = float(y_text.strip())
    except Exception:
        return None

    # Chernarus-ish ADM coordinate range. Good enough for useful plotting.
    px = int(max(0, min(511, (x / 15360) * 512)))
    py = int(max(0, min(383, 384 - ((y / 15360) * 384))))
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


async def get_or_create_feed_channel(guild, config, key, name, private=False):
    channels = config.setdefault("channels", {})
    existing_id = channels.get(key)

    if existing_id:
        existing = guild.get_channel(existing_id)
        if existing:
            return existing

    for channel in guild.text_channels:
        if normalize_discord_name(channel.name) == normalize_discord_name(name):
            channels[key] = channel.id
            save_guild_configs()
            return channel

    overwrites = None
    if private:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }
        for role in guild.roles:
            if role.permissions.administrator or role.name in config.get("admin_roles", DEFAULT_ADMIN_ROLES):
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel = await guild.create_text_channel(name, overwrites=overwrites)
    channels[key] = channel.id
    save_guild_configs()
    return channel


async def send_special_adm_feed(guild_id, config, event_type, line):
    guild = bot.get_guild(int(guild_id)) if str(guild_id).isdigit() else None
    if not guild:
        return

    feed_map = {
        "flag_raise": ("flag_feed", "🏴📡・flag-intel・📡🏴", True, "🏴 FLAG RAISED", 0x2ECC71),
        "flag_lower": ("flag_feed", "🏴📡・flag-intel・📡🏴", True, "🏴 FLAG LOWERED", 0xE67E22),
        "cut": ("cuts_feed", "🩸⚕️・injury-intel・⚕️🩸", True, "🩸 SURVIVOR INJURED", 0xE74C3C),
        "bleedout": ("cuts_feed", "🩸⚕️・injury-intel・⚕️🩸", True, "☠️ SURVIVOR BLED OUT", 0x8E1B1B),
        "suicide": ("cuts_feed", "🩸⚕️・injury-intel・⚕️🩸", True, "⚰️ SUICIDE EVENT", 0x6C3483),
        "respawn": ("cuts_feed", "🩸⚕️・injury-intel・⚕️🩸", True, "🔁 RESPAWN CHOSEN", 0x3498DB),
        "packed": ("placed_feed", "🧰🏕️・placement-intel・🏕️🧰", True, "📦 ITEM PACKED", 0xF1C40F),
        "placed": ("placed_feed", "🧰🏕️・placement-intel・🏕️🧰", True, "🧱 PLACEMENT ACTIVITY", 0x1ABC9C),
    }

    if event_type not in feed_map:
        return

    key, channel_name, private, title, color = feed_map[event_type]
    channel = await get_or_create_feed_channel(guild, config, key, channel_name, private)
    player = extract_player_name(line)
    map_link = build_adm_map_link(line)

    details = "Event captured from ADM feed."
    if event_type == "placed":
        placed_match = re.search(r'placed ([^<]+)', line, re.IGNORECASE)
        if placed_match:
            details = f"Placed: {placed_match.group(1).strip()[:120]}"
    elif event_type == "packed":
        packed_match = re.search(r'packed ([^<]+)', line, re.IGNORECASE)
        if packed_match:
            details = f"Packed: {packed_match.group(1).strip()[:120]}"
    elif event_type in {"cut", "bleedout", "suicide", "respawn"}:
        details = "Medical/combat status event logged."

    embed = create_feed_embed(
        title=title,
        color=color,
        player=player,
        details=details,
        coords=extract_adm_coords(line)
    )
    if map_link:
        embed.add_field(name="Map", value=f"[Open Location](<{map_link}>)", inline=True)
    await channel.send(embed=embed)


async def send_swear_jar_feed(message, found_words, fine, pennies_total):
    guild_id = str(message.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": message.guild.name, "channels": {}})
    channel = await get_or_create_feed_channel(message.guild, config, "swear_jar_feed", "swear-jar")

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
    if bot.user not in message.mentions:
        return

    now_ts = datetime.now(UTC).timestamp()
    key = f"{message.guild.id}:{message.author.id}"

    if now_ts - last_ai_direct_response_time.get(key, 0) < 45:
        return

    last_ai_direct_response_time[key] = now_ts

    help_lines = [
        "I am awake. Unfortunately for everyone, I have opinions. Ask me about raids, loot, bases, sickness, or why your car achieved orbit.",
        "Yes, survivor? I can help with bot commands, DayZ advice, or emotional support after another deeply avoidable death.",
        "Radio check received. Tell me what you need and I will pretend we are all making sensible choices.",
    ]

    await message.channel.send(wb_text("ai", random.choice(help_lines)))

    # Occasional DayZ-themed AI image response (about 20% chance) if enabled.
    if random.random() < 0.20:
        image_url = generate_dayz_image_url(message.content)
        if image_url:
            embed = discord.Embed(
                title="🎨 DayZ Field Sketch",
                description="AI-generated vibe image based on the conversation.",
                color=0x8E44AD
            )
            embed.set_image(url=image_url)
            embed.set_footer(text="Generated image may be stylized/non-literal.")
            await message.channel.send(embed=style_embed(embed))


def generate_dayz_image_url(prompt_text: str):
    cleaned = re.sub(r"\s+", " ", str(prompt_text)).strip()
    if not cleaned:
        cleaned = "DayZ survivor scene at sunset, cinematic, realistic"
    full_prompt = f"DayZ style scene, Chernarus mood, {cleaned[:180]}"
    try:
        from urllib.parse import quote_plus
        return f"https://image.pollinations.ai/prompt/{quote_plus(full_prompt)}"
    except Exception:
        return None


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


async def maybe_send_wandering_personality(message, now_ts):
    if not message.guild:
        return

    guild_id = str(message.guild.id)
    last_seen = last_emoji_showcase_time.get(guild_id, 0)

    if now_ts - last_seen < 1800:
        return

    roll = random.random()

    if roll < 0.012:
        last_emoji_showcase_time[guild_id] = now_ts
        await message.channel.send(
            f"{random_wandering_emoji()} {random.choice(WANDERING_EMOJI_SHOWCASE_LINES)}"
        )

    elif roll < 0.018:
        last_emoji_showcase_time[guild_id] = now_ts
        await message.channel.send(
            wb_text("radio", random.choice(WANDERING_SWEAR_LINES))
        )

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
        "vehicle_reset_enabled": False,
        "vehicle_reset_schedule_utc_hour": 5,
        "vehicle_reset_baseline_events_path": "",
        "vehicle_reset_target_events_path": "/dayzxb/mpmissions/dayzOffline.chernarusplus/db/events.xml",
        "vehicle_reset_persistence_paths": [],
        "vehicle_reset_last_run_date": "",
        "channels": {}
    }


def channel_matches_saved_key(channel, key):
    normalized = normalize_discord_name(channel.name)
    aliases = set(CHANNEL_ALIASES.get(key, []))
    desired = DEFAULT_CHANNEL_NAMES.get(key)

    if desired:
        aliases.add(normalize_discord_name(desired))

    if key == "connections" and "disconnect" in normalized:
        return False

    return normalized in aliases or any(alias and alias in normalized for alias in aliases)


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


def ensure_player_stat_record(player_name, guild_id=None):
    if player_name not in player_stats or not isinstance(player_stats.get(player_name), dict):
        player_stats[player_name] = {
            "kills": 0,
            "deaths": 0,
            "raids": 0,
            "builds": 0,
            "guild_id": str(guild_id) if guild_id is not None else ""
        }

    if guild_id is not None:
        player_stats[player_name]["guild_id"] = str(guild_id)

    return player_stats[player_name]


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


def stable_line_hash(line):
    return hashlib.sha256(
        line.encode("utf-8", errors="ignore")
    ).hexdigest()


def load_processed_adm_lines():
    global processed_lines

    data = load_json(PROCESSED_ADM_FILE)
    processed_lines = {}

    for guild_id, hashes in data.items():
        if isinstance(hashes, list):
            processed_lines[str(guild_id)] = set(str(item) for item in hashes)


def stamp_adm_tail_checkpoint(guild_id, lines):
    guild_id = str(guild_id)
    if not lines:
        return
    tail_hash = stable_line_hash(lines[-1].strip())
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    config["adm_last_tail_hash"] = tail_hash
    save_guild_configs()


def save_processed_adm_lines():
    data = {}

    for guild_id, hashes in processed_lines.items():
        hash_list = list(hashes)
        data[guild_id] = hash_list[-1000:]

    save_json(PROCESSED_ADM_FILE, data)


def remember_processed_line(guild_id, line_hash):
    ensure_guild_runtime(guild_id)
    processed_lines[guild_id].add(line_hash)

    if len(processed_lines[guild_id]) > 1000:
        processed_lines[guild_id] = set(list(processed_lines[guild_id])[-1000:])

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

    return "Unknown"


def ensure_guild_runtime(guild_id):

    if guild_id not in processed_lines:
        processed_lines[guild_id] = set()

    if guild_id not in online_players:
        online_players[guild_id] = set()

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
        plotted = map_coords_to_pixel(coords)
        if plotted:
            mode_points.append(plotted)
            points[mode] = mode_points[-300:]

    save_heatmap()


def classify_event(line):

    lower = line.lower()
    zombie_terms = ["infected", "zombie", "zmb"]
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

    if " packed " in lower:
        return "packed"

    if " placed " in lower:
        return "placed"

    if any(term in lower for term in unconscious_terms):
        return "unconscious"

    if any(term in lower for term in zombie_terms):

        if any(word in lower for word in ["killed", "died", "dead"]):
            return "zombie_kill"

        if any(word in lower for word in ["hit", "attacked", "damage", "wound"]):
            return "zombie_hit"

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

def ping_latest_adm_log(config):

    token = config.get("nitrado_token")
    service_id = config.get("service_id")
    nitrado_user = config.get("nitrado_user")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    search_paths = [
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

    for search_path in search_paths:

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

            print("[PING STATUS]", response.status_code)

            if response.status_code != 200:
                continue

            data = response.json()

            entries = (
                data
                .get("data", {})
                .get("entries", [])
            )

            print(f"[SEARCH PATH] {search_path}")

            for entry in entries:
                print(f"FOUND FILE: {entry.get('name')}")

            matching_logs = [
                entry for entry in entries
                if re.match(
                    r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                    entry.get("name", ""),
                    re.IGNORECASE
                )
            ]

            if not matching_logs:
                print("NO MATCHING ADM FILES")
                continue

            matching_logs.sort(
                key=lambda x: x.get("modified_at", ""),
                reverse=True
            )

            latest = matching_logs[0]

            print("LATEST ADM FOUND:", latest.get("path"))

            return latest

        except Exception as error:
            print(error)

    return None

# =========================================================
# LIVE DASHBOARD SETTINGS
# =========================================================

ONLINE_UPDATE_MINUTES = 30
LEADERBOARD_UPDATE_MINUTES = 30
HEATMAP_UPDATE_MINUTES = 30

last_online_message_ids = {}
last_leaderboard_message_ids = {}
last_heatmap_message_ids = {}

# =========================================================
# CLICKABLE MAP LINKS
# =========================================================

def build_izurvive_link(coords):

    try:

        split_coords = coords.split(",")

        x = split_coords[0].strip()
        y = split_coords[1].strip()

        return f"https://dayz.ginfo.gg/#location={x};{y}"

    except:
        return None


ZONE_POINTS = {
    "NWAF": (330, 120), "Tisy": (220, 70), "Zelenogorsk": (170, 220),
    "Chernogorsk": (120, 290), "Elektrozavodsk": (360, 300), "Vybor": (210, 140),
    "Berezino": (430, 150), "Severograd": (360, 95)
}


def generate_guild_heatmap_image(guild_id: str, mode=None):
    import math
    import struct
    import zlib

    width = 512
    height = 384
    mode = mode or guild_heatmap_mode(guild_id)
    pixels = [
        [(94, 126, 102, 255) for _ in range(width)]
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

    def draw_grid():
        for x in range(0, width, 64):
            for y in range(height):
                blend_pixel(x, y, (170, 200, 180, 80))

        for y in range(0, height, 48):
            for x in range(width):
                blend_pixel(x, y, (170, 200, 180, 80))

        for x in range(40, width - 40):
            coast_y = int(300 + math.sin(x / 24) * 18)
            for y in range(coast_y, height):
                blend_pixel(x, y, (72, 124, 170, 180))

    def png_chunk(chunk_type, data):
        chunk = chunk_type + data
        return (
            struct.pack(">I", len(data))
            + chunk
            + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        )

    draw_grid()
    zone_counts = heat_counts_for_mode(guild_id, mode)
    max_count = max(zone_counts.values()) if zone_counts else 1

    for point in heat_points_for_mode(guild_id, mode):
        px, py = point
        draw_heat_circle(px, py, 36, (255, 60, 0, 90))
        draw_heat_circle(px, py, 18, (255, 210, 0, 190))
        draw_cross(px, py)

    for zone, count in zone_counts.items():
        if zone not in ZONE_POINTS:
            continue

        x, y = ZONE_POINTS[zone]
        intensity = max(0.2, min(1.0, count / max_count))

        draw_heat_circle(x, y, 70, (255, 45, 0, int(45 * intensity)))
        draw_heat_circle(x, y, 48, (255, 80, 0, int(90 * intensity)))
        draw_heat_circle(x, y, 25, (255, 180, 0, int(170 * intensity)))
        draw_cross(x, y)

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
# =========================================================
# AUTO GUILD SETUP
# =========================================================

@bot.event
async def on_guild_join(guild):

    guild_id = str(guild.id)

    if guild_id in guild_configs:
        return

    category = await guild.create_category("🟩🟩🟩┃WANDERING HQ┃🟩🟩🟩")
    live_category = await guild.create_category("🟥🟧🟨┃LIVE SERVER FEEDS┃🟨🟧🟥")
    info_category = await guild.create_category("🟦🟩🟦┃SERVER INFO┃🟦🟩🟦")
    community_category = await guild.create_category("🟪🟩🟪┃SURVIVOR COMMS┃🟪🟩🟪")
    staff_category = await guild.create_category("🛡️🟥🛡️┃STAFF OPS┃🛡️🟥🛡️")
    economy_category = await guild.create_category("💰🟨💰┃ECONOMY┃💰🟨💰")
    faction_category = await guild.create_category("🏴🟩🏴┃FACTIONS┃🏴🟩🏴")
    support_category = await guild.create_category("❓🟦❓┃HELP & SUPPORT┃❓🟦❓")

    async def make_channel(name, *, cat=None):

        return await guild.create_text_channel(
            name,
            category=cat or category
        )

    killfeed = await make_channel("🔥🔥・killfeed・🔥🔥", cat=live_category)
    raids = await make_channel("🚨🏴・raids・🏴🚨", cat=live_category)
    builds = await make_channel("🔨🧱・building・🧱🔨", cat=live_category)
    connections = await make_channel("🟢✅・connected・✅🟢", cat=live_category)
    disconnects = await make_channel("🔴⛔・disconnects・⛔🔴", cat=live_category)
    zombie_feed = await make_channel("🧟🧟・zombie-feed・🧟🧟", cat=live_category)
    unconscious_feed = await make_channel("🩹⚠️・unconscious-feed・⚠️🩹", cat=live_category)

    online = await make_channel("✅🎮・online-survivors・🎮✅", cat=info_category)
    leaderboards = await make_channel("🏆📊・leaderboards・📊🏆", cat=info_category)
    heatmap_channel = await make_channel("🔥🗺️・heatmap・🗺️🔥", cat=info_category)
    longshot_channel = await make_channel("🎯🏹・longshots・🏹🎯", cat=info_category)
    restart_alerts = await make_channel("📢⏰・restart-alerts・⏰📢", cat=info_category)

    welcome_channel = await make_channel("👋🟩・welcome・🟩👋", cat=community_category)
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
    command_logs = await make_channel("📜🛡️・command-logs・🛡️📜", cat=staff_category)
    purchase_logs = await make_channel("💳📦・purchase-logs・📦💳", cat=economy_category)
    vehicle_rentals = await make_channel("🚗💰・vehicle-rentals・💰🚗", cat=economy_category)
    rental_logs = await make_channel("🛻📒・rental-logs・📒🛻", cat=economy_category)
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
            "welcome": welcome_channel.id,
            "general_chat": general_chat.id,
            "factions_chat": factions_chat.id,
            "faction_list": faction_list.id,
            "help_channel": help_channel.id,
            "clips_channel": clips_channel.id,
            "economy": economy_channel.id,
            "ai_chat": ai_channel.id,
            "admin_logs": admin_logs.id,
            "command_logs": command_logs.id,
            "purchase_logs": purchase_logs.id,
            "vehicle_rentals": vehicle_rentals.id,
            "rental_logs": rental_logs.id,
            "faction_tickets": faction_tickets.id,
            "faction_staff": faction_staff.id,
            "zombie_feed": zombie_feed.id,
            "unconscious_feed": unconscious_feed.id,
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
    ftp_password="Your Nitrado FTP password"
)
async def setup_command(
    interaction: discord.Interaction,
    nitrado_token: str,
    service_id: str,
    nitrado_user: str,
    ftp_user: str,
    ftp_password: str
):

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)

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
        "support": ["helpsupport", "helpdesk", "support"]
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
        "welcome": ["welcome", "newsurvivor", "joins"],
        "general_chat": ["survivorchat", "generalchat", "general", "chat"],
        "factions_chat": ["factionschat", "factions", "factionchat"],
        "faction_list": ["factionlist", "factionslist"],
        "help_channel": ["helpdesk", "help", "support"],
        "clips_channel": ["dayzclips", "clips", "media"],
        "economy": ["blackmarket", "economy", "shop", "market"],
        "ai_chat": ["survivorai", "aichat", "ai"],
        "admin_logs": ["adminlogs", "stafflogs"],
        "command_logs": ["commandlogs", "commands"],
        "purchase_logs": ["purchaselogs", "purchases"],
        "vehicle_rentals": ["vehiclerentals", "rentvehicles", "rentals"],
        "rental_logs": ["rentallogs"],
        "faction_tickets": ["factiontickets", "factionrequests"],
        "faction_staff": ["factionstaff"],
        "zombie_feed": ["zombiefeed", "infectedfeed", "zmbfeed", "zombies"],
        "unconscious_feed": ["unconsciousfeed", "medicalfeed", "unconscious"]
    }

    def channel_matches_key(channel, key, desired_name):
        normalized = normalize_discord_name(channel.name)
        desired = normalize_discord_name(desired_name)
        aliases = set(channel_aliases.get(key, []))
        aliases.add(desired)

        if key == "connections" and "disconnect" in normalized:
            return False

        return normalized in aliases or any(alias and alias in normalized for alias in aliases)

    async def ensure_channel(key, name, *, cat=None):
        target_category = cat or category
        channels = guild_configs[guild_id].setdefault("channels", {})
        existing_id = channels.get(key)

        if existing_id:
            existing_channel = interaction.guild.get_channel(existing_id)
            if existing_channel:
                try:
                    await existing_channel.edit(name=name, category=target_category)
                except Exception:
                    pass
                return existing_channel

            channels.pop(key, None)

        for existing_channel in interaction.guild.text_channels:
            if channel_matches_key(existing_channel, key, name):
                channels[key] = existing_channel.id
                try:
                    await existing_channel.edit(name=name, category=target_category)
                except Exception:
                    pass
                return existing_channel

        channel = await interaction.guild.create_text_channel(
            name,
            category=target_category
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

    await ensure_channel("online", "✅🎮・online-survivors・🎮✅", cat=info_category)
    await ensure_channel("leaderboards", "🏆📊・leaderboards・📊🏆", cat=info_category)
    await ensure_channel("heatmap", "🔥🗺️・heatmap・🗺️🔥", cat=info_category)
    await ensure_channel("longshots", "🎯🏹・longshots・🏹🎯", cat=info_category)
    await ensure_channel("restart_alerts", "📢⏰・restart-alerts・⏰📢", cat=info_category)

    await ensure_channel("welcome", "👋🟩・welcome・🟩👋", cat=community_category)
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
    await ensure_channel("command_logs", "📜🛡️・command-logs・🛡️📜", cat=staff_category)
    await ensure_channel("purchase_logs", "💳📦・purchase-logs・📦💳", cat=economy_category)
    await ensure_channel("vehicle_rentals", "🚗💰・vehicle-rentals・💰🚗", cat=economy_category)
    await ensure_channel("rental_logs", "🛻📒・rental-logs・📒🛻", cat=economy_category)

    guild_configs[guild_id]["nitrado_token"] = nitrado_token
    guild_configs[guild_id]["service_id"] = service_id
    guild_configs[guild_id]["nitrado_user"] = nitrado_user.strip()
    guild_configs[guild_id]["ftp_user"] = ftp_user
    guild_configs[guild_id]["ftp_password"] = ftp_password

    save_guild_configs()

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
                "`/heatmap` - territory activity summary\n"
                "`/topkills` - kill leaderboard\n"
                "`/toplongshots` - global longshot leaderboard\n"
                "Auto channels: killfeed, raids, building, zombie-feed, unconscious-feed, online, leaderboards, heatmap"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="ADMIN SETUP & MODERATION",
            value=(
                "`/setadminrole role_name` - replace the primary bot admin role\n"
                "`/addstaffrole role_name` - add another role allowed to use staff tools\n"
                "`/staffroles` - list staff roles\n"
                "`/purge amount` - clear recent messages\n"
                "`/purgeuser member amount` - clear a member's messages\n"
                "`/purgebots amount` - clear bot messages"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="SERVER CONTROL & RADAR",
            value=(
                "`/restartserver` - trigger a Nitrado restart\n"
                "`/setrestartinterval hours` - set restart interval\n"
                "`/setrestartstart hour` - set UTC restart start hour\n"
                "`/listrestarts` - show restart schedule\n"
                "`/togglebasedamage state` - log base damage state\n"
                "`/setradarchannel channel` - choose radar channel\n"
                "`/radarping x y reason` - send a manual map ping"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="ECONOMY, SHOP, REWARDS & PUNISHMENTS",
            value=(
                "`/wallet` - check wallet\n"
                "`/shop` - view black market\n"
                "`/buy item_name x y` - queue item delivery\n"
                "`/rentvehicle vehicle_name rental_hours x y` - queue vehicle rental\n"
                "Shop admin: `/addshopitem`, `/editshopitem`, `/toggleshopitem`, `/removeshopitem`, `/givepennies`, `/shopcategories`, `/importtypesxml`\n"
                "Admin rules: `/addreward`, `/addpunishment`, `/listrules`, `/removerule`"
            ),
            inline=False
        )

        setup_embed.add_field(
            name="TRANSLATION SYSTEM",
            value=(
                "`/translationconfig mode target_language source_language source_channel target_channel`\n"
                "Modes: `off`, `same`, `channel`\n"
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
                "Add `SpawnWanderingDeliveries();` to your DayZ `init.c` after weather setup. "
                "That enables restart delivery spawning from the XML this bot uploads."
            ),
            inline=False
        )

        setup_embed.set_thumbnail(url=BOT_IMAGE)
        setup_embed.set_footer(
            text="Wandering System created by CraneMonkey6273"
        )

        await help_channel.send(embed=style_embed(setup_embed))

    await interaction.followup.send(
        "✅ Wandering Bot fully connected and operational.",
        ephemeral=True
    )

# =========================================================
# NITRADO XML DELIVERY BRIDGE
# =========================================================

def upload_delivery_xml_to_nitrado(config, xml_path):

    try:

        ftp_host = "ftp.nitrado.net"
        ftp_user = config.get("ftp_user")
        ftp_pass = config.get("ftp_password")

        if not ftp_user or not ftp_pass:

            print("FTP DETAILS NOT CONFIGURED")
            return False

        ftp = FTP_TLS(ftp_host)

        ftp.login(ftp_user, ftp_pass)
        ftp.prot_p()

        target_path = (
            "/dayzxb/custom/deliveries.xml"
        )

        with open(xml_path, "rb") as xml_file:

            ftp.storbinary(
                f"STOR {target_path}",
                xml_file
            )

        ftp.quit()

        print("DELIVERY XML UPLOADED TO NITRADO")

        return True

    except Exception as error:

        print(error)
        return False


def run_vehicle_reset(config):
    try:
        ftp_host = "ftp.nitrado.net"
        ftp_user = config.get("ftp_user")
        ftp_pass = config.get("ftp_password")

        if not ftp_user or not ftp_pass:
            return False, "FTP details are missing."

        baseline_path = config.get("vehicle_reset_baseline_events_path", "").strip()
        target_events_path = config.get("vehicle_reset_target_events_path", "").strip()
        persistence_paths = config.get("vehicle_reset_persistence_paths", [])

        if not baseline_path or not os.path.exists(baseline_path):
            return False, "Baseline events.xml path is missing or not found on bot host."

        ftp = FTP_TLS(ftp_host)
        ftp.login(ftp_user, ftp_pass)
        ftp.prot_p()

        with open(baseline_path, "rb") as events_file:
            ftp.storbinary(f"STOR {target_events_path}", events_file)

        deleted = 0
        for remote_path in persistence_paths:
            if not str(remote_path).strip():
                continue
            try:
                ftp.delete(remote_path)
                deleted += 1
            except Exception:
                continue

        ftp.quit()
        return True, f"Uploaded events.xml and deleted {deleted} configured persistence file(s)."
    except Exception as error:
        return False, str(error)

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

def create_feed_embed(title, color, player=None, details=None, weapon=None, coords=None):

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
        map_link = build_izurvive_link(coords)

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

    config_tail_hash = str(config.get("adm_last_tail_hash", "")).strip()
    if lines and not config_tail_hash:
        # First run after setup/redeploy: checkpoint current tail so old events are not replayed.
        stamp_adm_tail_checkpoint(guild_id, lines)
        return

    if lines and config_tail_hash:
        start_index = None
        for idx, raw in enumerate(lines):
            if stable_line_hash(raw.strip()) == config_tail_hash:
                start_index = idx + 1
                break
        if start_index is not None:
            lines = lines[start_index:]

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

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"EVENT: {event_type} | {line}")

        ensure_guild_runtime(guild_id)

        zone = get_zone_from_line(line)
        coords = extract_adm_coords(line)
        heat_mode = heatmap_mode_for_event(event_type)

        if heat_mode:
            increase_heat(guild_id, zone, heat_mode, coords)

        await send_special_adm_feed(guild_id, config, event_type, line)

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

            embed.timestamp = datetime.now(UTC)

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

            if coords:

                map_link = build_izurvive_link(coords)

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

            embed.timestamp = datetime.now(UTC)

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

            map_link = build_izurvive_link(coords)

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

            embed.timestamp = datetime.now(UTC)

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

                map_link = build_izurvive_link(coords)

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

            embed.timestamp = datetime.now(UTC)

            await raid_channel.send(embed=embed)

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

                embed.timestamp = datetime.now(UTC)

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

                embed.timestamp = datetime.now(UTC)

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
                    map_link = build_izurvive_link(coords)
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

                embed.timestamp = datetime.now(UTC)

                await unconscious_channel.send(
                    embed=style_embed(embed)
                )
        # ================= KILLFEED =================

        elif event_type == "kill" and killfeed_channel:

            killer_match = re.search(
                r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)',
                line
            )

            coords_match = re.search(
                r'pos=<([^>]+)>',
                line
            )

            coords = (
                coords_match.group(1)
                if coords_match else None
            )

            if killer_match:

                killer = killer_match.group(1)
                victim = killer_match.group(2)
                weapon = killer_match.group(3)

                distance_match = re.search(
                    r'from ([0-9]+\.?[0-9]*)m',
                    line,
                    re.IGNORECASE
                )

                distance = (
                    float(distance_match.group(1))
                    if distance_match else 0
                )

                embed = discord.Embed(
                    title="☠️ PLAYER KILL",
                    color=0x992D22
                )

                embed.add_field(
                    name="🔫 Killer",
                    value=killer,
                    inline=True
                )

                embed.add_field(
                    name="💀 Victim",
                    value=victim,
                    inline=True
                )

                if distance > 0:

                    embed.add_field(
                        name="🎯 Distance",
                        value=f"{distance}m",
                        inline=True
                    )

                embed.add_field(
                    name="🪖 Weapon",
                    value=weapon,
                    inline=False
                )

                if coords:

                    map_link = build_izurvive_link(coords)

                    if map_link:

                        embed.add_field(
                            name="📍 Kill Location",
                            value=f"[🔵 Open Map](<{map_link}>)",
                            inline=False
                        )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Alpha • PvP Intelligence"
                )

                embed.timestamp = datetime.now(UTC)

                await killfeed_channel.send(
                    embed=embed
                )

                guild_longshot = longshot_records.get(guild_id, {
                    "killer": "None",
                    "distance": 0,
                    "weapon": "Unknown"
                })

                if distance > guild_longshot.get("distance", 0):

                    longshot_records[guild_id] = {
                        "killer": killer,
                        "victim": victim,
                        "distance": distance,
                        "weapon": weapon
                    }

                    longshot_channel = bot.get_channel(
                        channels.get("longshots")
                    )

                    if longshot_channel:

                        longshot_embed = discord.Embed(
                            title="🎯 NEW SERVER LONGSHOT RECORD",
                            description=(
                                f"{killer} just set a new longshot record!"
                            ),
                            color=0xF1C40F
                        )

                        longshot_embed.add_field(
                            name="🎯 Distance",
                            value=f"{distance}m",
                            inline=True
                        )

                        longshot_embed.add_field(
                            name="🔫 Weapon",
                            value=weapon,
                            inline=True
                        )

                        longshot_embed.add_field(
                            name="💀 Victim",
                            value=victim,
                            inline=True
                        )

                        if coords:

                            map_link = build_izurvive_link(coords)

                            if map_link:

                                longshot_embed.add_field(
                                    name="📍 Kill Location",
                                    value=f"[🔵 Open Map](<{map_link}>)",
                                    inline=False
                                )

                        longshot_embed.set_thumbnail(url=BOT_IMAGE)

                        longshot_embed.set_footer(
                            text="Wandering Bot Alpha • Longshot Tracking"
                        )

                        longshot_embed.timestamp = datetime.now(UTC)

                        await longshot_channel.send(
                            embed=style_embed(longshot_embed)
                        )

                killer_stats = ensure_player_stat_record(killer, guild_id)
                victim_stats = ensure_player_stat_record(victim, guild_id)
                killer_stats["kills"] = int(killer_stats.get("kills", 0)) + 1
                victim_stats["deaths"] = int(victim_stats.get("deaths", 0)) + 1
                save_player_stats()

    # Update tail checkpoint after processing so redeploys continue from newest known line.
    if lines:
        stamp_adm_tail_checkpoint(guild_id, lines)

# =========================================================
# ADM LOOP
# =========================================================

async def refresh_adm_for_guild(guild_id, config, *, force=False):

    ensure_guild_runtime(guild_id)

    if force:
        processed_lines[guild_id] = set()
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

# =========================================================
# SWEAR JAR
# =========================================================

@bot.event
async def on_member_join(member):

    guild_id = str(member.guild.id)

    config = guild_configs.get(guild_id, {})

    channels = config.get("channels", {})

    welcome_channel = bot.get_channel(
        channels.get("welcome")
    )

    if not welcome_channel:
        return

    import random

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

    for keyword, response in AI_RESPONSES.items():

        if keyword in lower:

            await message.channel.send(wb_text("ai", response))

            break

    user_id = str(message.author.id)
    now_ts = datetime.now(UTC).timestamp()

    if user_id not in player_chat_tracker:

        player_chat_tracker[user_id] = {
            "recent_messages": 0,
            "recent_swears": 0,
            "clean_messages": 0,
            "eligible": False
        }

    # low-frequency fun chatter with anti-repeat + anti-spam guards
    if now_ts - last_funny_message_time.get(user_id, 0) > 900:
        import random
        if random.random() < 0.04:
            idx = random.randrange(len(FUNNY_ROTATION))
            if idx == last_funny_index.get(user_id, -1):
                idx = (idx + 1) % len(FUNNY_ROTATION)
            last_funny_index[user_id] = idx
            last_funny_message_time[user_id] = now_ts
            await message.channel.send(wb_text("spark", FUNNY_ROTATION[idx]))

    await maybe_reply_to_bot_mention(message, lower)
    await maybe_owner_mention_remark(message)
    await maybe_send_wandering_personality(message, now_ts)

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

    if not BOT_OWNER_SECRET_CODE:
        return False

    if secret_code != BOT_OWNER_SECRET_CODE:
        return False

    if BOT_OWNER_GUILD_ID and str(interaction.guild_id) != str(BOT_OWNER_GUILD_ID):
        return False

    return True


async def reject_owner_command(interaction):
    await interaction.response.send_message(
        "Owner command rejected.",
        ephemeral=True
    )

@bot.listen("on_command")
async def log_command_usage(ctx):

    try:

        guild_id = str(ctx.guild.id)

        config = guild_configs.get(guild_id, {})

        channels = config.get("channels", {})

        command_log_channel = bot.get_channel(
            channels.get("command_logs")
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
        name="Live Intelligence",
        value=(
            "`/online` - online survivors\n"
            "`/serverstatus` - bot status\n"
            "`/heatmap` - PvP heatmap summary\n"
            "`/topkills` - top kills\n"
            "`/toplongshots` - longshot leaderboard\n"
            "`/playerstats player_name` - player lookup"
        ),
        inline=False
    )

    embed.add_field(
        name="Admin Tools",
        value=(
            "`/setadminrole role_name`\n"
            "`/addstaffrole role_name`\n"
            "`/staffroles`\n"
            "`/purge amount`\n"
            "`/purgeuser member amount`\n"
            "`/purgebots amount`"
        ),
        inline=False
    )

    embed.add_field(
        name="Server Control",
        value=(
            "`/restartserver`\n"
            "`/admstatus`\n"
            "`/restartadm force`\n"
            "`/reloadguilds`\n"
            "`/setrestartinterval hours`\n"
            "`/setrestartstart hour`\n"
            "`/listrestarts`\n"
            "`/togglebasedamage state`\n"
            "`/setradarchannel channel`\n"
            "`/radarping x y reason`"
        ),
        inline=False
    )

    embed.add_field(
        name="Economy & Rules",
        value=(
            "`/wallet`, `/shop`, `/buy`, `/rentvehicle`\n"
            "`/addreward keyword amount`\n"
            "`/addpunishment keyword amount`\n"
            "`/listrules`\n"
            "`/removerule rule_number`\n"
            "`/importtypesxml source_path default_price`\n"
            "`/addshopitem item_name price category`\n"
            "`/editshopitem item_name price category`\n"
            "`/toggleshopitem item_name`, `/removeshopitem item_name`\n"
            "`/givepennies member amount`, `/shopcategories`"
        ),
        inline=False
    )

    embed.add_field(
        name="Translation, Factions & Support",
        value=(
            "`/translationconfig mode target_language source_language source_channel target_channel`\n"
            "`/linkgamer gamertag`, `/mylink`\n"
            "`/factionticket faction_name`, `/factionapprove message_id`\n"
            "`/supportbot issue` - admin ticket to the bot owner"
        ),
        inline=False
    )

    embed.set_thumbnail(url=BOT_IMAGE)
    embed.set_footer(text="Wandering System created by CraneMonkey6273")

    await ctx.send(embed=style_embed(embed))

    admin_vehicle_embed = discord.Embed(
        title="🛠️ ADMIN GUIDE: VEHICLE-ONLY RESET (How To Use)",
        description=(
            "This guide is for owners/admins only. It explains what each vehicle reset command does "
            "and the safe order to run them."
        ),
        color=0x3498DB
    )

    admin_vehicle_embed.add_field(
        name="1) Configure baseline + schedule",
        value=(
            "`/configurevehiclereset enabled schedule_utc_hour baseline_events_path target_events_path`\n"
            "Example: `/configurevehiclereset on 5 /home/container/events_baseline.xml "
            "/dayzxb/mpmissions/dayzOffline.chernarusplus/db/events.xml`\n"
            "- `enabled`: `on/off`\n"
            "- `schedule_utc_hour`: 0-23 UTC\n"
            "- `baseline_events_path`: local file on bot host\n"
            "- `target_events_path`: remote server events.xml path"
        ),
        inline=False
    )

    admin_vehicle_embed.add_field(
        name="2) Set vehicle persistence files only",
        value=(
            "`/setvehiclepersistpaths path1,path2,path3`\n"
            "Only include files related to vehicle persistence. "
            "If you include broader persistence files, other world state may reset too."
        ),
        inline=False
    )

    admin_vehicle_embed.add_field(
        name="3) Run instantly or let scheduler run daily",
        value=(
            "`/runvehiclereset` runs now.\n"
            "Scheduler runs daily at configured UTC hour when enabled.\n"
            "Use admin logs/console to verify success messages."
        ),
        inline=False
    )

    admin_vehicle_embed.add_field(
        name="What this reset does",
        value=(
            "1. Uploads your baseline `events.xml`.\n"
            "2. Deletes only configured persistence paths.\n"
            "3. Leaves everything else untouched unless you configured broad paths."
        ),
        inline=False
    )

    admin_vehicle_embed.set_thumbnail(url=BOT_IMAGE)
    admin_vehicle_embed.set_footer(text="Always backup before resets.")

    await ctx.send(embed=style_embed(admin_vehicle_embed))

    admin_full_guide = discord.Embed(
        title="📘 ADMIN GUIDE: WHAT COMMANDS DO + HOW TO USE THEM",
        description=(
            "Quick practical guide for server owners/admins. "
            "Use slash commands; examples show the normal usage pattern."
        ),
        color=0x9B59B6
    )

    admin_full_guide.add_field(
        name="👥 Roles & Permissions",
        value=(
            "`/setadminrole role_name` → sets primary bot admin role.\n"
            "`/addstaffrole role_name` → allows additional role to use admin tools.\n"
            "`/staffroles` → lists who can run admin commands."
        ),
        inline=False
    )

    admin_full_guide.add_field(
        name="🧹 Moderation",
        value=(
            "`/purge amount` → delete recent messages in current channel.\n"
            "`/purgeuser member amount` → delete recent messages by one member.\n"
            "`/purgebots amount` → clean recent bot messages."
        ),
        inline=False
    )

    admin_full_guide.add_field(
        name="🖥️ Server Control & Restart Tools",
        value=(
            "`/restartserver` → requests a Nitrado restart.\n"
            "`/setrestartinterval hours` + `/setrestartstart hour` → define UTC restart cadence.\n"
            "`/listrestarts` → shows current restart schedule.\n"
            "`/togglebasedamage state` → log/announce base damage state.\n"
            "`/admstatus` + `/restartadm force` → monitor/recover ADM feed loop."
        ),
        inline=False
    )

    admin_full_guide.add_field(
        name="📡 Radar / Alerts",
        value=(
            "`/setradarchannel channel` → where radar pings are posted.\n"
            "`/radarping x y reason` → send manual map ping with context for staff/player alerts."
        ),
        inline=False
    )

    admin_full_guide.add_field(
        name="🛒 Economy & Shop Admin",
        value=(
            "`/importtypesxml source_path default_price` → bulk import shop items from types.xml.\n"
            "`/addshopitem`, `/editshopitem`, `/toggleshopitem`, `/removeshopitem` → maintain shop catalog.\n"
            "`/givepennies member amount` → manual balance adjustments.\n"
            "`/shopcategories` → review catalog counts by category."
        ),
        inline=False
    )

    admin_full_guide.add_field(
        name="⚖️ Auto Reward / Punishment Rules",
        value=(
            "`/addreward keyword amount` → add pennies when keyword appears.\n"
            "`/addpunishment keyword amount` → remove pennies when keyword appears.\n"
            "`/listrules` + `/removerule rule_number` → audit and clean chat economy rules."
        ),
        inline=False
    )

    admin_full_guide.add_field(
        name="🌍 Translation, Identity, Factions, Support",
        value=(
            "`/translationconfig ...` → set auto translation mode/channel/languages.\n"
            "`/linkgamer gamertag`, `/mylink` → map Discord ↔ gamertag identity.\n"
            "`/factionticket`, `/factionapprove` → faction request pipeline.\n"
            "`/supportbot issue` → private admin ticket to bot owner."
        ),
        inline=False
    )

    admin_full_guide.add_field(
        name="🧠 Safe Usage Pattern (Recommended)",
        value=(
            "1) Configure roles first (`/setadminrole`, `/addstaffrole`).\n"
            "2) Configure server/restart channels and radar.\n"
            "3) Configure economy/shop and moderation rules.\n"
            "4) Run vehicle reset setup only after backups are verified."
        ),
        inline=False
    )

    admin_full_guide.set_thumbnail(url=BOT_IMAGE)
    admin_full_guide.set_footer(text="Need details for a command? Ask admin to run /helpme again.")

    await ctx.send(embed=style_embed(admin_full_guide))

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
async def pvestatus(ctx):
    embed = discord.Embed(
        title="🛡️ PVE SYSTEM STATUS",
        description="PVE command layer is active for announcements and planning.",
        color=0x2ECC71
    )
    embed.add_field(
        name="Current",
        value="Use existing feeds (`/zombiefeed`, `/unconsciousfeed`, `/heatmap`) for live PVE pressure monitoring.",
        inline=False
    )
    embed.add_field(
        name="Planned Expansion",
        value="Rotating PVE objectives, faction PVE contracts, and timed hotspot alerts.",
        inline=False
    )
    await ctx.send(embed=style_embed(embed))


@bot.command()
async def quests(ctx):
    embed = discord.Embed(
        title="📜 QUEST BOARD",
        description="Quest module is currently informational.",
        color=0xF1C40F
    )
    embed.add_field(
        name="How to use now",
        value="Staff can post active quests in your announcements/help channels and track completion manually.",
        inline=False
    )
    embed.add_field(
        name="Next step",
        value="Automated quest templates + reward payouts can be wired into the wallet/shop system.",
        inline=False
    )
    await ctx.send(embed=style_embed(embed))


@bot.command()
async def dayzimage(ctx, *, prompt: str = "abandoned military checkpoint at dusk"):
    image_url = generate_dayz_image_url(prompt)
    if not image_url:
        await ctx.send("❌ Could not generate image URL right now.")
        return

    embed = discord.Embed(
        title="🖼️ DAYZ AI IMAGE",
        description=f"Prompt: `{prompt[:180]}`",
        color=0x9B59B6
    )
    embed.set_image(url=image_url)
    embed.set_footer(text="AI generated scene for community flavor content.")
    await ctx.send(embed=style_embed(embed))


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

    sorted_players = sorted(
        player_stats.items(),
        key=lambda x: x[1].get("kills", 0),
        reverse=True
    )

    lines = []

    for index, (player, stats) in enumerate(
        sorted_players[:10],
        start=1
    ):

        lines.append(
            f"{index}. {player} - {stats.get('kills', 0)} kills"
        )

    embed = discord.Embed(
        title="☠️ TOP KILLS",
        description="\n".join(lines),
        color=0x992D22
    )

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================================================
# CUSTOM ROLE CONFIGURATION
# =========================================================

@bot.command()
async def setadminrole(ctx, *, role_name: str):

    if not ctx.author.guild_permissions.administrator:
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

    if not ctx.author.guild_permissions.administrator:
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

# =========================================================
# SCHEDULED RESTART LOOP
# =========================================================

DEFAULT_RESTART_INTERVAL_HOURS = 4

last_restart_hour = {}
restart_warning_tracker = {}

@tasks.loop(minutes=1)
async def scheduled_restart_loop():

    global last_restart_hour

    now = datetime.now(UTC)

    current_hour = now.hour
    current_minute = now.minute

    for guild_id, config in active_guild_config_items():

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

                await announce_channel.send(
                    embed=style_embed(embed)
                )

                token = config.get("nitrado_token")
                service_id = config.get("service_id")

                if token and service_id:

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

    user_id = str(ctx.author.id)

    linked_players[user_id] = {
        "discord_name": str(ctx.author),
        "gamertag": gamertag
    }

    save_linked_players()

    embed = discord.Embed(
        title="🔗 GAMERTAG LINKED",
        description=(
            f"Your Discord account is now linked to: `{gamertag}`"
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
    user_id = str(interaction.user.id)
    linked_players[user_id] = {
        "discord_name": str(interaction.user),
        "gamertag": gamertag
    }
    save_linked_players()
    embed = discord.Embed(
        title="🔗 GAMERTAG LINKED",
        description=f"Linked to: `{gamertag}`",
        color=0x2ECC71
    )
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
@commands.has_permissions(administrator=True)
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
        
        if not scheduled_vehicle_reset_loop.is_running():
            scheduled_vehicle_reset_loop.start()

    except RuntimeError:
        pass

# =========================================================
# LIVE ONLINE DASHBOARD
# =========================================================

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
                text="Wandering Bot Alpha • Auto Refresh Every 15 Minutes"
            )

            embed.timestamp = datetime.now(UTC)

            old_message_id = last_online_message_ids.get(guild_id)
            if old_message_id:
                try:
                    old_message = await online_channel.fetch_message(old_message_id)
                    await old_message.delete()
                except Exception:
                    pass

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
                    if lines else "No PvP activity detected yet."
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

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Heatmap Refresh Every 15 Minutes"
            )

            embed.timestamp = datetime.now(UTC)

            old_message_id = last_heatmap_message_ids.get(guild_id)
            if old_message_id:
                try:
                    old_message = await heatmap_channel.fetch_message(old_message_id)
                    await old_message.delete()
                except Exception:
                    pass

            sent_message = await heatmap_channel.send(embed=embed, file=file)
            last_heatmap_message_ids[guild_id] = sent_message.id
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

            sorted_players = sorted(
                player_stats.items(),
                key=lambda x: x[1].get("kills", 0),
                reverse=True
            )

            lines = []

            for index, (player, stats) in enumerate(
                sorted_players[:10],
                start=1
            ):

                lines.append(
                    f"{index}. {player} — ☠️ {stats.get('kills', 0)} | 💀 {stats.get('deaths', 0)}"
                )

            global_lines = lines[:5]

            guild_lines = []
            guild_only = []
            for player, stats in player_stats.items():
                if str(stats.get("guild_id", "")) == guild_id:
                    guild_only.append((player, stats))
            guild_only.sort(key=lambda x: x[1].get("kills", 0), reverse=True)
            for idx, (player, stats) in enumerate(guild_only[:5], start=1):
                guild_lines.append(
                    f"{idx}. {player} — ☠️ {stats.get('kills', 0)} | 💀 {stats.get('deaths', 0)}"
                )

            embed = discord.Embed(
                title="🏆 LEADERBOARDS (GLOBAL + THIS SERVER) 🏆",
                color=0xF1C40F
            )
            embed.add_field(
                name="🌍 Global Top 5",
                value=(
                    "\n".join(global_lines)
                    if global_lines else
                    "No kill stats yet. Leaderboard fills after kill events are detected in ADM."
                ),
                inline=False
            )
            embed.add_field(
                name="🏠 This Server Top 5",
                value=(
                    "\n".join(guild_lines)
                    if guild_lines else
                    "No server-specific kill stats yet. Check ADM feed and wait for next kill event."
                ),
                inline=False
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Alpha • Leaderboards Refresh Every 15 Minutes"
            )

            embed.timestamp = datetime.now(UTC)

            old_message_id = last_leaderboard_message_ids.get(guild_id)
            if old_message_id:
                try:
                    old_message = await leaderboard_channel.fetch_message(old_message_id)
                    await old_message.delete()
                except Exception:
                    pass

            sent_message = await leaderboard_channel.send(embed=embed)
            last_leaderboard_message_ids[guild_id] = sent_message.id

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
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "types.xml"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "types.xml.xml"),
]

shop_items = {}
wallets = {}
delivery_queue = []
vehicle_rentals_queue = []


def find_types_xml(source_path=None):
    candidates = []

    if source_path:
        candidates.append(source_path)

    candidates.extend(TYPES_XML_CANDIDATES)

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

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
    global delivery_queue

    if os.path.exists(DELIVERY_QUEUE_FILE):

        with open(DELIVERY_QUEUE_FILE, "r") as f:
            delivery_queue = json.load(f)


def save_delivery_queue():

    with open(DELIVERY_QUEUE_FILE, "w") as f:
        json.dump(delivery_queue, f, indent=4)


DEFAULT_DAILY_TRANSACTION_LIMIT = 5
VEHICLE_RENTAL_FILE = "vehicle_rentals.json"


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

                delivery_file = os.path.join(
                    GUILD_DATA_FOLDER,
                    f"{guild_id}_deliveries.json"
                )

                output = {
                    "items": delivery_queue,
                    "vehicles": vehicle_rentals_queue,
                    "generated": str(now)
                }

                with open(delivery_file, "w") as f:
                    json.dump(output, f, indent=4)

                print(f"DELIVERY FILE GENERATED FOR {guild_id}")

                # =========================================
                # XML DELIVERY GENERATION
                # =========================================

                xml_lines = []

                xml_lines.append('<objects>')

                # ================= ITEMS =================

                for delivery in delivery_queue:

                    item_name = delivery.get("item")
                    x = delivery.get("x")
                    y = delivery.get("y")

                    xml_lines.append(
                        f'<object name="{item_name}" pos="{x} 0 {y}" />'
                    )

                # ================= VEHICLES =================

                for rental in vehicle_rentals_queue:

                    vehicle_name = rental.get("vehicle")
                    x = rental.get("x")
                    y = rental.get("y")

                    xml_lines.append(
                        f'<object name="{vehicle_name}" pos="{x} 0 {y}" />'
                    )

                xml_lines.append('</objects>')

                xml_output_path = os.path.join(
                    GUILD_DATA_FOLDER,
                    f"{guild_id}_deliveries.xml"
                )

                with open(xml_output_path, "w") as xml_file:

                    xml_file.write("\n".join(xml_lines))

                print(f"XML DELIVERY FILE GENERATED FOR {guild_id}")

                upload_success = upload_delivery_xml_to_nitrado(
                    config,
                    xml_output_path
                )

                if upload_success:

                    print(f"DELIVERY XML BRIDGED TO SERVER {guild_id}")

                    delivery_queue.clear()
                    vehicle_rentals_queue.clear()

                    save_delivery_queue()

        except Exception as error:
            print(error)


@tasks.loop(minutes=5)
async def scheduled_vehicle_reset_loop():
    now = datetime.now(UTC)
    today = now.date().isoformat()

    for guild_id, config in active_guild_config_items():
        try:
            if not config.get("vehicle_reset_enabled", False):
                continue

            schedule_hour = int(config.get("vehicle_reset_schedule_utc_hour", 5))
            last_run = str(config.get("vehicle_reset_last_run_date", ""))

            if now.hour != schedule_hour or now.minute > 5 or last_run == today:
                continue

            ok, msg = run_vehicle_reset(config)
            if ok:
                config["vehicle_reset_last_run_date"] = today
                save_guild_configs()
            print(f"[VEHICLE RESET][{guild_id}] {msg}")
        except Exception as error:
            print(f"[VEHICLE RESET][{guild_id}] {error}")


# =========================================================
# TYPES.XML SHOP MANAGEMENT SYSTEM
# =========================================================

@bot.command()
@commands.has_permissions(administrator=True)
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
@commands.has_permissions(administrator=True)
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
@commands.has_permissions(administrator=True)
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
@commands.has_permissions(administrator=True)
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
@commands.has_permissions(administrator=True)
async def importtypesxml(ctx, source_path: str = None, default_price: int = 100):

    added, updated, types_path = load_shop_items_from_types_xml(
        source_path,
        default_price,
        overwrite=False
    )

    if not types_path:
        await ctx.send("No types.xml file found. Put `types.xml` beside the bot or in `guild_data`.")
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


@bot.command()
@commands.has_permissions(administrator=True)
async def configurevehiclereset(
    ctx,
    enabled: str,
    schedule_utc_hour: int,
    baseline_events_path: str,
    target_events_path: str = "/dayzxb/mpmissions/dayzOffline.chernarusplus/db/events.xml"
):
    guild_id = str(ctx.guild.id)
    config = guild_configs.setdefault(guild_id, new_guild_config(ctx.guild))
    config["vehicle_reset_enabled"] = enabled.lower() in {"on", "true", "1", "yes"}
    config["vehicle_reset_schedule_utc_hour"] = max(0, min(23, schedule_utc_hour))
    config["vehicle_reset_baseline_events_path"] = baseline_events_path
    config["vehicle_reset_target_events_path"] = target_events_path
    save_guild_configs()
    await ctx.send("✅ Vehicle reset configuration saved.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setvehiclepersistpaths(ctx, *, paths_csv: str):
    guild_id = str(ctx.guild.id)
    config = guild_configs.setdefault(guild_id, new_guild_config(ctx.guild))
    config["vehicle_reset_persistence_paths"] = [
        p.strip() for p in paths_csv.split(",") if p.strip()
    ]
    save_guild_configs()
    await ctx.send(f"✅ Saved {len(config['vehicle_reset_persistence_paths'])} vehicle persistence path(s).")


@bot.command()
@commands.has_permissions(administrator=True)
async def runvehiclereset(ctx):
    guild_id = str(ctx.guild.id)
    config = guild_configs.setdefault(guild_id, new_guild_config(ctx.guild))
    ok, msg = run_vehicle_reset(config)
    await ctx.send(("✅" if ok else "❌") + f" {msg}")


# =========================================================
# ADMIN SHOP MANAGEMENT
# =========================================================


@bot.command()
@commands.has_permissions(administrator=True)
async def removeshopitem(ctx, *, item_name: str):

    if item_name not in shop_items:

        await ctx.send("Item not found.")
        return

    del shop_items[item_name]

    save_shop()

    await ctx.send(f"🗑️ Removed {item_name} from the shop.")


@bot.command()
@commands.has_permissions(administrator=True)
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
async def player_lottery(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
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
@app_commands.describe(issue="Briefly describe your bot issue")
async def supportbot(interaction: discord.Interaction, issue: str):

    if not interaction.user.guild_permissions.administrator:
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

@bot.tree.command(name="translationconfig", description="Admin: configure automatic translation")
@app_commands.describe(
    mode="off, same, or channel",
    target_language="Target language code, example: en, es, fr, de",
    source_language="Source language code or auto",
    source_channel="Optional source channel. Blank means all channels.",
    target_channel="Required for channel mode"
)
async def translationconfig(
    interaction: discord.Interaction,
    mode: str,
    target_language: str = "en",
    source_language: str = "auto",
    source_channel: discord.TextChannel = None,
    target_channel: discord.TextChannel = None
):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    mode = mode.lower().strip()

    if mode not in ["off", "same", "channel"]:
        await interaction.response.send_message("Mode must be `off`, `same`, or `channel`.", ephemeral=True)
        return

    if mode == "channel" and not target_channel:
        await interaction.response.send_message("Channel mode needs a target_channel.", ephemeral=True)
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
        color=0x1ABC9C
    )
    embed.add_field(name="Mode", value=mode, inline=True)
    embed.add_field(name="Source", value=source_channel.mention if source_channel else "All channels", inline=True)
    embed.add_field(name="Target", value=target_channel.mention if target_channel else "Same channel", inline=True)
    embed.add_field(name="Language", value=f"{source_language} -> {target_language}", inline=False)
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)


@bot.tree.command(name="addreward", description="Admin: reward pennies when a keyword appears in chat")
@app_commands.describe(keyword="Word or phrase to detect", amount="Pennies to add")
async def addreward(interaction: discord.Interaction, keyword: str, amount: int):

    if not interaction.user.guild_permissions.administrator:
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
@app_commands.describe(keyword="Word or phrase to detect", amount="Pennies to remove")
async def addpunishment(interaction: discord.Interaction, keyword: str, amount: int):

    if not interaction.user.guild_permissions.administrator:
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


@bot.tree.command(name="listrules", description="Admin: list reward and punishment rules")
async def listrules(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
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
@app_commands.describe(rule_number="Rule number from /listrules")
async def removerule(interaction: discord.Interaction, rule_number: int):

    if not interaction.user.guild_permissions.administrator:
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


@bot.tree.command(name="setheatmapmode", description="Admin: choose what the heatmap tracks")
@app_commands.describe(mode="pvp, zombie, cuts, building, raids, flags, suicide, placed, or all")
async def setheatmapmode(interaction: discord.Interaction, mode: str):

    if not interaction.user.guild_permissions.administrator:
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


@bot.tree.command(name="setservermap", description="Admin: set the server map label used by heatmap feeds")
@app_commands.describe(map_name="Example: chernarus, livonia, deerisle, namalsk")
async def setservermap(interaction: discord.Interaction, map_name: str):

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    config["server_map"] = map_name.lower().strip()
    save_guild_configs()

    await interaction.response.send_message(
        f"Server map set to `{config['server_map']}`.",
        ephemeral=True
    )


@bot.tree.command(name="createfaction", description="Admin: create an official faction")
@app_commands.describe(
    name="Faction name",
    leader="Faction leader",
    members="Optional extra members as @mentions",
    flag="Faction flag/name",
    role_color="Hex colour, example #2ecc71"
)
async def createfaction(
    interaction: discord.Interaction,
    name: str,
    leader: discord.Member,
    members: str = "",
    flag: str = "Not set",
    role_color: str = "#2ecc71"
):

    if not interaction.user.guild_permissions.administrator:
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
    for mention_id in re.findall(r"\d{15,25}", members or ""):
        member = interaction.guild.get_member(int(mention_id))
        if member:
            member_ids.add(member.id)

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
@app_commands.describe(name="Faction name", member="Discord member")
async def addfactionmember(interaction: discord.Interaction, name: str, member: discord.Member):

    if not interaction.user.guild_permissions.administrator:
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
@app_commands.describe(name="Faction name", member="Discord member")
async def removefactionmember(interaction: discord.Interaction, name: str, member: discord.Member):

    if not interaction.user.guild_permissions.administrator:
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
@bot.tree.command(name="helpme", description="Show command/help information")
async def slash_helpme(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "helpme")
@bot.tree.command(name="swearjar", description="Show swear jar leaderboard")
async def slash_swearjar(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "swearjar")
@bot.tree.command(name="heatmap", description="Show territory heatmap summary")
async def slash_heatmap(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "heatmap")
@bot.tree.command(name="toplongshots", description="Show longshot leaderboard")
async def slash_toplongshots(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "toplongshots")
@bot.tree.command(name="topkills", description="Show top kill leaderboard")
async def slash_topkills(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "topkills")
@bot.tree.command(name="staffroles", description="List staff roles")
async def slash_staffroles(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "staffroles")
@bot.tree.command(name="mylink", description="Show your linked gamertag")
async def slash_mylink(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "mylink")
@bot.tree.command(name="wallet", description="Show your wallet")
async def slash_wallet(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "wallet")
@bot.tree.command(name="shop", description="Show shop")
async def slash_shop(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "shop")
@bot.tree.command(name="pvestatus", description="Show PVE module status")
async def slash_pvestatus(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "pvestatus")
@bot.tree.command(name="quests", description="Show quest board status")
async def slash_quests(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "quests")
@bot.tree.command(name="dayzimage", description="Generate a DayZ-themed AI image")
@app_commands.describe(prompt="Describe the scene")
async def slash_dayzimage(interaction: discord.Interaction, prompt: str): await run_legacy_as_slash(interaction, "dayzimage", prompt=prompt)
@bot.tree.command(name="runvehiclereset", description="Admin: run vehicle-only reset now")
async def slash_runvehiclereset(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "runvehiclereset")

@bot.tree.command(name="setadminrole", description="Set primary admin role")
@app_commands.describe(role="Existing Discord role")
async def slash_setadminrole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    config["admin_roles"] = [role.name]
    save_guild_configs()
    await interaction.response.send_message(f"Primary admin role set to {role.mention}.", ephemeral=True)
@bot.tree.command(name="addstaffrole", description="Add a staff role")
@app_commands.describe(role="Existing Discord role")
async def slash_addstaffrole(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    guild_id = str(interaction.guild.id)
    config = guild_configs.setdefault(guild_id, {"guild_name": interaction.guild.name, "channels": {}})
    roles = config.setdefault("admin_roles", DEFAULT_ADMIN_ROLES.copy())
    if role.name not in roles:
        roles.append(role.name)
    save_guild_configs()
    await interaction.response.send_message(f"Staff role added: {role.mention}.", ephemeral=True)
@bot.tree.command(name="giverole", description="Admin: give an existing role to a real Discord member")
@app_commands.describe(member="Discord member", role="Existing Discord role")
async def giverole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await member.add_roles(role, reason=f"Role given by {interaction.user}")
    await interaction.response.send_message(f"Added {role.mention} to {member.mention}.", ephemeral=True)
@bot.tree.command(name="removerole", description="Admin: remove an existing role from a real Discord member")
@app_commands.describe(member="Discord member", role="Existing Discord role")
async def removerole(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await member.remove_roles(role, reason=f"Role removed by {interaction.user}")
    await interaction.response.send_message(f"Removed {role.mention} from {member.mention}.", ephemeral=True)
@bot.tree.command(name="factionticket", description="Create faction request")
@app_commands.describe(faction_name="Faction name")
async def slash_factionticket(interaction: discord.Interaction, faction_name: str): await run_legacy_as_slash(interaction, "factionticket", faction_name=faction_name)
@bot.tree.command(name="factionapprove", description="Approve faction request")
@app_commands.describe(message_id="Ticket message ID")
async def slash_factionapprove(interaction: discord.Interaction, message_id: int): await run_legacy_as_slash(interaction, "factionapprove", message_id=message_id)
@bot.tree.command(name="purge", description="Purge recent messages")
@app_commands.describe(amount="Amount")
async def slash_purge(interaction: discord.Interaction, amount: int = 10): await run_legacy_as_slash(interaction, "purge", amount=amount)
@bot.tree.command(name="purgeuser", description="Purge user messages")
@app_commands.describe(member="Member", amount="Amount")
async def slash_purgeuser(interaction: discord.Interaction, member: discord.Member, amount: int = 50): await run_legacy_as_slash(interaction, "purgeuser", member=member, amount=amount)
@bot.tree.command(name="purgebots", description="Purge bot messages")
@app_commands.describe(amount="Amount")
async def slash_purgebots(interaction: discord.Interaction, amount: int = 100): await run_legacy_as_slash(interaction, "purgebots", amount=amount)
@bot.tree.command(name="setradarchannel", description="Set radar channel")
@app_commands.describe(channel="Channel")
async def slash_setradarchannel(interaction: discord.Interaction, channel: discord.TextChannel): await run_legacy_as_slash(interaction, "setradarchannel", channel=channel)
@bot.tree.command(name="radarping", description="Send radar ping")
@app_commands.describe(x="X", y="Y", reason="Reason")
async def slash_radarping(interaction: discord.Interaction, x: str, y: str, reason: str = "Survivor Activity"): await run_legacy_as_slash(interaction, "radarping", x=x, y=y, reason=reason)
@bot.tree.command(name="admstatus", description="Admin: show ADM feed status")
async def slash_admstatus(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "admstatus")
@bot.tree.command(name="reloadguilds", description="Admin: reload saved guild configs after redeploy")
async def slash_reloadguilds(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "reloadguilds")
@bot.tree.command(name="restartadm", description="Admin: restart and run the ADM feed")
@app_commands.describe(force="Reprocess recent ADM lines")
async def slash_restartadm(interaction: discord.Interaction, force: bool = False):
    await run_legacy_as_slash(interaction, "restartadm", force="force" if force else "no")
@bot.tree.command(name="restartserver", description="Restart server")
async def slash_restartserver(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "restartserver")
@bot.tree.command(name="togglebasedamage", description="Toggle base damage")
@app_commands.describe(state="on or off")
async def slash_togglebasedamage(interaction: discord.Interaction, state: str): await run_legacy_as_slash(interaction, "togglebasedamage", state=state)
@bot.tree.command(name="setrestartinterval", description="Set restart interval")
@app_commands.describe(hours="Hours 1-24")
async def slash_setrestartinterval(interaction: discord.Interaction, hours: int): await run_legacy_as_slash(interaction, "setrestartinterval", hours=hours)
@bot.tree.command(name="setrestartstart", description="Set restart start hour UTC")
@app_commands.describe(hour="Hour 0-23")
async def slash_setrestartstart(interaction: discord.Interaction, hour: int): await run_legacy_as_slash(interaction, "setrestartstart", hour=hour)
@bot.tree.command(name="listrestarts", description="List restart schedule")
async def slash_listrestarts(interaction: discord.Interaction): await run_legacy_as_slash(interaction, "listrestarts")
@bot.tree.command(name="playerstats", description="Lookup player stats")
@app_commands.describe(player_name="Player name")
async def slash_playerstats(interaction: discord.Interaction, player_name: str): await run_legacy_as_slash(interaction, "playerstats", player_name=player_name)
@bot.tree.command(name="buy", description="Buy an item and queue delivery")
@app_commands.describe(item_name="Item", x="Map X", y="Map Y")
async def slash_buy(interaction: discord.Interaction, item_name: str, x: str, y: str): await run_legacy_as_slash(interaction, "buy", item_name=item_name, x=x, y=y)
@bot.tree.command(name="importtypesxml", description="Admin: preload shop from vanilla types.xml")
@app_commands.describe(source_path="Optional path to types.xml", default_price="Fallback price")
async def slash_importtypesxml(interaction: discord.Interaction, source_path: str = None, default_price: int = 100):
    await run_legacy_as_slash(interaction, "importtypesxml", source_path=source_path, default_price=default_price)
@bot.tree.command(name="addshopitem", description="Admin: add an item to the shop")
@app_commands.describe(item_name="Item classname", price="Price in pennies", category="Shop category")
async def slash_addshopitem(interaction: discord.Interaction, item_name: str, price: int, category: str = "General"):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "addshopitem", item_name=item_name, price=price, category=category)
@bot.tree.command(name="editshopitem", description="Admin: edit a shop item")
@app_commands.describe(item_name="Item classname", price="Optional new price", category="Optional new category")
async def slash_editshopitem(interaction: discord.Interaction, item_name: str, price: int = None, category: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "editshopitem", item_name=item_name, price=price, category=category)
@bot.tree.command(name="toggleshopitem", description="Admin: enable or disable a shop item")
@app_commands.describe(item_name="Item classname")
async def slash_toggleshopitem(interaction: discord.Interaction, item_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "toggleshopitem", item_name=item_name)
@bot.tree.command(name="removeshopitem", description="Admin: remove an item from the shop")
@app_commands.describe(item_name="Item classname")
async def slash_removeshopitem(interaction: discord.Interaction, item_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "removeshopitem", item_name=item_name)
@bot.tree.command(name="givepennies", description="Admin: give pennies to a member")
@app_commands.describe(member="Discord member", amount="Pennies to add")
async def slash_givepennies(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await run_legacy_as_slash(interaction, "givepennies", member=member, amount=amount)
@bot.tree.command(name="shopcategories", description="Show shop categories")
async def slash_shopcategories(interaction: discord.Interaction):
    await run_legacy_as_slash(interaction, "shopcategories")
@bot.tree.command(name="rentvehicle", description="Rent a vehicle")
@app_commands.describe(vehicle_name="Vehicle", rental_hours="Hours", x="Map X", y="Map Y")
async def slash_rentvehicle(interaction: discord.Interaction, vehicle_name: str, rental_hours: int, x: str, y: str): await run_legacy_as_slash(interaction, "rentvehicle", vehicle_name=vehicle_name, rental_hours=rental_hours, x=x, y=y)

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
    load_player_stats()
    load_heatmap()
    load_swear_jar()
    load_linked_players()
    load_support_tickets()
    load_factions()
    load_wandering_emojis()
    print(f"WANDERING EMOJIS LOADED: {len(wandering_emojis)}")
    load_shop()
    load_wallets()
    load_delivery_queue()

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

    try:
        synced = await bot.tree.sync()
        print(f"SLASH COMMANDS SYNCED: {len(synced)}")
    except Exception as sync_error:
        print(sync_error)

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)
