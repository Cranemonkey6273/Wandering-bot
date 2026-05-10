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

BOT_IMAGE = (
    "https://media.discordapp.net/"
    "attachments/1499787777636831324/"
    "1501685742433206342/"
    "7A382429-B666-4A9F-B890-17C0F7981709.png"
)

# =========================
# SAVE STATE
# =========================

def save_state():

    try:

        with open(STATE_FILE, "w") as f:
            json.dump(adm_state, f)

    except Exception as error:

        print("STATE SAVE ERROR")
        print(error)


def load_state():

    global adm_state

    try:

        if os.path.exists(STATE_FILE):

            with open(STATE_FILE, "r") as f:

                adm_state = json.load(f)

            print("STATE LOADED")

    except Exception as error:

        print("STATE LOAD ERROR")
        print(error)

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

    save_state()

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

        # ================= CONNECT =================

        if (
            event_type == "connect"
            and connect_channel
        ):

            embed = discord.Embed(
                title="🟢 Survivor Connected",
                description=line,
                color=0x2ECC71
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= DISCONNECT =================

        elif (
            event_type == "disconnect"
            and connect_channel
        ):

            embed = discord.Embed(
                title="🔴 Survivor Disconnected",
                description=line,
                color=0xE74C3C
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await connect_channel.send(
                embed=style_embed(embed)
            )

        # ================= BUILD =================

        elif (
            event_type == "build"
            and build_channel
        ):

            embed = discord.Embed(
                title="🏗️ BUILD EVENT",
                description=line,
                color=0xF1C40F
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await build_channel.send(
                embed=style_embed(embed)
            )

        # ================= RAID =================

        elif (
            event_type == "raid"
            and raid_channel
        ):

            embed = discord.Embed(
                title="🚨 RAID EVENT",
                description=line,
                color=0xFF0000
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await raid_channel.send(
                embed=style_embed(embed)
            )

        # ================= KILLFEED =================

        elif (
            event_type == "kill"
            and killfeed_channel
        ):

            embed = discord.Embed(
                title="☠️ KILL EVENT",
                description=line,
                color=0x992D22
            )

            embed.set_thumbnail(
                url=BOT_IMAGE
            )

            await killfeed_channel.send(
                embed=style_embed(embed)
            )

# =========================
# LOOP
# =========================

@tasks.loop(minutes=3)
async def adm_loop():

    print("CHECKING ADM...")

    latest_log = await asyncio.to_thread(
        ping_latest_adm_log
    )

    if not latest_log:

        print("NO ADM FOUND")

        return

    modified_at = latest_log.get(
        "modified_at"
    )

    if (
        modified_at
        == adm_state.get("last_modified")
    ):

        print("ADM NOT MODIFIED")

        return

    print("NEW ADM UPDATE FOUND")

    download_success = await asyncio.to_thread(
        download_latest_adm,
        latest_log
    )

    if not download_success:

        return

    adm_state["last_modified"] = modified_at

    save_state()

    await parse_adm()

# =========================
# READY
# =========================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    load_state()

    try:

        adm_loop.start()

    except RuntimeError:
        pass

# =========================
# ONLINE COMMAND
# =========================

@bot.command()
async def online(ctx):

    if online_players:

        players = "\n".join(
            sorted(online_players)
        )

    else:

        players = "No players online."

    embed = discord.Embed(
        title="🟢 ONLINE PLAYERS",
        description=players,
        color=0x2ECC71
    )

    await ctx.send(
        embed=style_embed(embed)
    )

# =========================
# START
# =========================

bot.run(DISCORD_TOKEN)
