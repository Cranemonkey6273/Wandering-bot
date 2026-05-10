import os
import re
import json
import asyncio
import requests
import discord

from datetime import datetime, UTC
from discord.ext import commands, tasks

# =========================
# ENV VARIABLES
# =========================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

NITRADO_TOKEN = os.getenv("NITRADO_API_TOKEN")

SERVICE_ID = "18965708"
NITRADO_USER = "ni12248929_1"
PLATFORM = "dayzxb"

# =========================
# CHANNEL IDS
# =========================

KILLFEED_CHANNEL_ID = int(
    os.getenv("KILLFEED_CHANNEL_ID", 0)
)

RAID_CHANNEL_ID = int(
    os.getenv("RAID_CHANNEL_ID", 0)
)

BUILD_CHANNEL_ID = int(
    os.getenv("BUILD_CHANNEL_ID", 0)
)

CONNECT_CHANNEL_ID = int(
    os.getenv("CONNECT_CHANNEL_ID", 0)
)

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================
# FILES
# =========================

LOCAL_LOG_FILE = "live.ADM"

STATE_FILE = "adm_state.json"
SWEAR_JAR_FILE = "swear_jar.json"
PLAYER_STATS_FILE = "player_stats.json"
HEATMAP_FILE = "heatmap.json"
PLAYER_SESSIONS_FILE = "player_sessions.json"
FACTIONS_FILE = "factions.json"

# =========================
# GLOBALS
# =========================

adm_state = {
    "last_modified": "",
    "last_line": 0,
    "last_text": ""
}

processed_lines = set()

online_players = set()
territory_heat = {}
player_stats = {}
player_sessions = {}
swear_jar = {}
kill_streaks = {}

factions = {}

ADMIN_ROLE_IDS = [
    123456789012345678
]
recent_pvp_events = []

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "wanker",
    "bollocks"
]

BOT_IMAGE = (
    "https://media.discordapp.net/"
    "attachments/1499787777636831324/"
    "1501685742433206342/"
    "7A382429-B666-4A9F-B890-17C0F7981709.png"
)

# =========================
# SAVE / LOAD
# =========================

def save_json(file_name, data):

    try:

        with open(file_name, "w") as f:

            json.dump(
                data,
                f,
                indent=4
            )

    except Exception as error:

        print(f"SAVE ERROR {file_name}")
        print(error)


def load_json(file_name, default):

    try:

        if os.path.exists(file_name):

            with open(file_name, "r") as f:

                return json.load(f)

    except Exception as error:

        print(f"LOAD ERROR {file_name}")
        print(error)

    return default

# =========================
# HELPERS
# =========================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    return embed


def extract_timestamp(filename):

    match = re.search(
        r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$",
        filename,
        re.IGNORECASE
    )

    if not match:
        return datetime.fromtimestamp(0)

    date_part = match.group(1)

    time_part = match.group(2).replace("-", ":")

    return datetime.fromisoformat(
        f"{date_part}T{time_part}"
    )


def ensure_player(player_name):

    if player_name not in player_stats:

        player_stats[player_name] = {
            "kills": 0,
            "deaths": 0,
            "raids": 0,
            "builds": 0
        }


def ensure_session(player_name):

    if player_name not in player_sessions:

        player_sessions[player_name] = {
            "total_seconds": 0,
            "last_seen": "",
            "connected_at": "",
            "sessions": 0
        }


def ensure_kill_streak(player_name):

    if player_name not in kill_streaks:

        kill_streaks[player_name] = 0


def get_zone_from_line(line):

    lower = line.lower()

    if "nwaf" in lower or "airfield" in lower:
        return "NWAF"

    if "tisy" in lower:
        return "Tisy"

    if "zeleno" in lower:
        return "Zelenogorsk"

    if "cherno" in lower:
        return "Chernogorsk"

    if "electro" in lower:
        return "Elektrozavodsk"

    if "vybor" in lower:
        return "Vybor"

    return "Unknown"


def check_warzone(zone):

    current_time = datetime.now(UTC)

    recent_pvp_events.append({
        "zone": zone,
        "time": current_time
    })

    cutoff = current_time.timestamp() - 600

    recent_pvp_events[:] = [
        event for event in recent_pvp_events
        if event["time"].timestamp() > cutoff
    ]

    zone_count = len([
        event for event in recent_pvp_events
        if event["zone"] == zone
    ])

    return zone_count


def increase_heat(zone):

    territory_heat[zone] = (
        territory_heat.get(zone, 0) + 1
    )

    save_json(
        HEATMAP_FILE,
        territory_heat
    )


def parse_kill_event(line):

    match = re.search(
        r'Player "([^"]+)" killed Player "([^"]+)" with ([^ ]+)',
        line,
        re.IGNORECASE
    )

    if not match:
        return None

    return {
        "killer": match.group(1),
        "victim": match.group(2),
        "weapon": match.group(3)
    }


def parse_advanced_kill(line):

    distance_match = re.search(
        r'from ([\d\.]+) meters',
        line,
        re.IGNORECASE
    )

    headshot = (
        "head" in line.lower()
    )

    return {
        "distance": (
            distance_match.group(1)
            if distance_match
            else "Unknown"
        ),
        "headshot": headshot
    }

# =========================
# API ADM CHECK
# =========================

def ping_latest_adm_log():

    url = (
        f"https://api.nitrado.net/services/"
        f"{SERVICE_ID}/gameservers/file_server/list"
    )

    headers = {
        "Authorization": f"Bearer {NITRADO_TOKEN}",
        "Accept": "application/json"
    }

    params = {
        "dir": (
            f"/games/{NITRADO_USER}"
            f"/noftp/{PLATFORM}"
            f"/config/"
        ),
        "search": "*DayZServer*"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20
        )

        print(
            "[PING] HTTP Status:",
            response.status_code
        )

        if response.status_code != 200:

            print(response.text)

            return None

        data = response.json()

        if data.get("status") != "success":

            print(data)

            return None

        entries = (
            data
            .get("data", {})
            .get("entries", [])
        )

        matching_logs = [

            entry for entry in entries

            if re.match(
                r"^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$",
                entry.get("name", ""),
                re.IGNORECASE
            )
        ]

        if not matching_logs:

            print("NO ADM LOGS FOUND")

            return None

        matching_logs.sort(
            key=lambda entry: extract_timestamp(
                entry.get("name", "")
            ),
            reverse=True
        )

        latest_log = matching_logs[0]

        return latest_log

    except Exception as error:

        print("API ERROR")
        print(error)

        return None

# =========================
# DOWNLOAD ADM
# =========================

def download_latest_adm(latest_log):

    try:

        download_url = (
            f"https://api.nitrado.net/services/"
            f"{SERVICE_ID}/gameservers/file_server/download"
        )

        headers = {
            "Authorization": f"Bearer {NITRADO_TOKEN}"
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

            print("DOWNLOAD FAILED")
            print(response.text)

            return False

        data = response.json()

        token_url = (
            data
            .get("data", {})
            .get("token", {})
            .get("url")
        )

        if not token_url:

            print("NO DOWNLOAD URL")

            return False

        file_response = requests.get(
            token_url,
            timeout=30
        )

        with open(
            LOCAL_LOG_FILE,
            "wb"
        ) as f:

            f.write(file_response.content)

        print("ADM DOWNLOADED")

        return True

    except Exception as error:

        print("DOWNLOAD ERROR")
        print(error)

        return False

# =========================
# EVENT CLASSIFIER
# =========================

def classify_event(line):

    lower = line.lower()

    if "disconnected" in lower:
        return "disconnect"

    if (
        "connecting" in lower
        or "connected" in lower
    ):
        return "connect"

    if "killed" in lower:
        return "kill"

    if (
        "placed" in lower
        or "built" in lower
        or "mounted" in lower
    ):
        return "build"

    if (
        "destroyed" in lower
        or "dismantled" in lower
        or "explosive" in lower
    ):
        return "raid"

    return None

# =========================
# ADM PARSER
# =========================

async def parse_adm():

    if not os.path.exists(LOCAL_LOG_FILE):
        return

    with open(
        LOCAL_LOG_FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    start_index = adm_state.get(
        "last_line",
        0
    )

    new_lines = lines[start_index:]

    adm_state["last_line"] = len(lines)

    save_json(
        STATE_FILE,
        adm_state
    )

    killfeed_channel = bot.get_channel(
        KILLFEED_CHANNEL_ID
    )

    raid_channel = bot.get_channel(
        RAID_CHANNEL_ID
    )

    build_channel = bot.get_channel(
        BUILD_CHANNEL_ID
    )

    connect_channel = bot.get_channel(
        CONNECT_CHANNEL_ID
    )

    for raw_line in new_lines:

        line = raw_line.strip()

        if not line:
            continue

        line_hash = hash(line)

        if line_hash in processed_lines:
            continue

        processed_lines.add(line_hash)

        event_type = classify_event(line)

        if not event_type:
            continue

        print(
            f"EVENT: {event_type} | {line}"
        )

        # CONNECT

        if (
            event_type == "connect"
            and connect_channel
        ):

            player_match = re.search(
                r'Player "([^"]+)"',
                line,
                re.IGNORECASE
            )

            player_name = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            online_players.add(player_name)

            ensure_session(player_name)

            player_sessions[player_name][
                "connected_at"
            ] = datetime.now(UTC).isoformat()

            player_sessions[player_name][
                "sessions"
            ] += 1

            save_json(
                PLAYER_SESSIONS_FILE,
                player_sessions
            )

            embed = discord.Embed(
        title="🏴 SERVER FACTIONS",
        description="\\n\\n".join(lines),
        color=0x5865F2
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def createfaction(ctx, faction_name):

    if not any(
        role.id in ADMIN_ROLE_IDS
        for role in ctx.author.roles
    ):

        await ctx.send(
            "You do not have permission."
        )

        return

    if faction_name in factions:

        await ctx.send(
            "Faction already exists."
        )

        return

    factions[faction_name] = []

    save_json(
        FACTIONS_FILE,
        factions
    )

    embed = discord.Embed(
        title="🏴 FACTION CREATED",
        description=f"{faction_name} created successfully.",
        color=0x2ECC71
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def addtofaction(ctx, player_name, faction_name):

    if not any(
        role.id in ADMIN_ROLE_IDS
        for role in ctx.author.roles
    ):

        await ctx.send(
            "You do not have permission."
        )

        return

    if faction_name not in factions:

        await ctx.send(
            "Faction does not exist."
        )

        return

    for faction in factions:

        if player_name in factions[faction]:

            factions[faction].remove(player_name)

    factions[faction_name].append(player_name)

    save_json(
        FACTIONS_FILE,
        factions
    )

    embed = discord.Embed(
        title="⚔️ PLAYER ASSIGNED",
        description=(
            f"{player_name} joined {faction_name}"
        ),
        color=0x3498DB
    )

    await ctx.send(
        embed=style_embed(embed)
    )


@bot.command()
async def removefromfaction(ctx, player_name):

    if not any(
        role.id in ADMIN_ROLE_IDS
        for role in ctx.author.roles
    ):

        await ctx.send(
            "You do not have permission."
        )

        return

    removed = False

    for faction in factions:

        if player_name in factions[faction]:

            factions[faction].remove(player_name)

            removed = True

    save_json(
        FACTIONS_FILE,
        factions
    )

    if not removed:

        await ctx.send(
            "Player was not in a faction."
        )

        return

    embed = discord.Embed(
        title="❌ PLAYER REMOVED",
        description=(
            f"{player_name} removed from faction"
        ),
        color=0xE74C3C
    )

    await ctx.send(
        embed=style_embed(embed)
    )

# START
# =========================

bot.run(DISCORD_TOKEN)
