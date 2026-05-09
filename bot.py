import os
import re
import asyncio
import discord
import json
import requests

# FTP REMOVED - USING NITRADO API ONLY
from datetime import datetime, UTC
from discord.ext import commands, tasks
from supabase import create_client
from openai import AsyncOpenAI

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ================= CHANNEL IDS =================

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

# ================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"
LOCAL_LOG_FILE = "live.ADM"

# ================= NITRADO API =================

NITRADO_API_TOKEN = os.getenv("NITRADO_API_TOKEN")
NITRADO_SERVICE_ID = os.getenv("NITRADO_SERVICE_ID")
NITRADO_USER = os.getenv("NITRADO_USER")
NITRADO_PLATFORM = os.getenv("NITRADO_PLATFORM")

# ================= SAVE FILE =================

STATE_FILE = "adm_state.json"

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= OPENAI =================

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ================= SUPABASE =================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 10000

adm_state = {
    "file": None,
    "last_line": 0,
    "last_text": "",
    "last_modified": "",
    "last_logged_file": ""
}

LAST_CHANGE_TIME = datetime.now(UTC)
LIVE_MODE = False

current_adm = None
current_adm_size = 0

online_players = set()
player_sessions = {}
territory_heat = {}

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

IGNORE_PATTERNS = [
    "[CE]",
    "LootRespawner",
    "PRIDummy",
    "causing search overtime",
    "Ammo_40mm_Explosive",
    "ConstructionHelmet",
    "script",
    "crash",
    "weather",
    "storage",
    "economy",
    "infected"
]

# ================= STATE SAVE =================


def save_state():

    try:

        with open(STATE_FILE, "w") as f:
            json.dump(adm_state, f)

    except Exception as e:
        print(f"STATE SAVE ERROR: {e}")


def load_state():

    global adm_state

    try:

        if os.path.exists(STATE_FILE):

            with open(STATE_FILE, "r") as f:
                adm_state = json.load(f)

            print("STATE LOADED")

    except Exception as e:
        print(f"STATE LOAD ERROR: {e}")


# ================= HELPERS =================


def should_ignore(line):

    lower = line.lower()

    for pattern in IGNORE_PATTERNS:

        if pattern.lower() in lower:
            return True

    return False


def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    return embed


def nitrado_headers():

    return {
        "Authorization": f"Bearer {NITRADO_API_TOKEN}"
    }


def nitrado_file_list():

    url = (
        f"https://api.nitrado.net/services/"
        f"{NITRADO_SERVICE_ID}/gameservers/file_server/list"
    )

    response = requests.get(
        url,
        headers=nitrado_headers(),
        params={
            "dir": f"/games/{NITRADO_USER}/noftp/{NITRADO_PLATFORM}/config/",
            "search": "*DayZServer*"
        },
        timeout=30
    )

    if response.status_code != 200:

        print(f"NITRADO LIST ERROR: {response.status_code}")
        print(response.text)
        return []

    return response.json().get("data", {}).get("entries", [])


def nitrado_download_file(filepath):

    url = (
        f"https://api.nitrado.net/services/"
        f"{NITRADO_SERVICE_ID}/gameservers/file_server/download"
    )

    response = requests.get(
        url,
        headers=nitrado_headers(),
        params={"file": filepath},
        timeout=30
    )

    if response.status_code != 200:

        print(f"NITRADO DOWNLOAD ERROR: {response.status_code}")
        return False

    download_url = (
        response.json()
        .get("data", {})
        .get("token", {})
        .get("url")
    )

    if not download_url:
        return False

    file_response = requests.get(download_url, timeout=60)

    if file_response.status_code != 200:
        return False

    download_success = nitrado_download_file(active_adm)

        if not download_success:
            return False

        

        print(f"ADM UPDATED: {filename}")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False


# ================= ADM PARSER =================


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

    start_index = adm_state.get("last_line", 0)

    new_lines = lines[start_index:]

    adm_state["last_line"] = len(lines)

    save_state()

    print(f"NEW ADM LINES: {len(new_lines)}")

    for raw_line in new_lines:

        line = raw_line.strip()

        if not line:
            continue

        if should_ignore(line):
            continue

        event_type = classify_event(line)

        if not event_type:
            continue

        print(f"EVENT: {event_type} | {line}")


# ================= TASK LOOP =================


@tasks.loop(minutes=5)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

    if success:
        await parse_adm()


# ================= READY =================


@bot.event
async def on_ready():

    load_state()

    await bot.tree.sync()

    try:
        adm_loop.start()

    except RuntimeError:
        pass

    print(f"✅ Logged in as {bot.user}")


# ================= ONLINE =================


@bot.tree.command(
    name="online",
    description="View online players"
)
async def online(interaction: discord.Interaction):

    if online_players:

        players = "\n".join(
            f"• {x}"
            for x in sorted(online_players)
        )

    else:

        players = "No players online."

    embed = discord.Embed(
        title=f"🟢 Online Players ({len(online_players)})",
        description=players,
        color=0x2ECC71
    )

    await interaction.response.send_message(
        embed=style_embed(embed)
    )


# ================= START =================

bot.run(DISCORD_TOKEN)
