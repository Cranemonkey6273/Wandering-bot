import os
import re
import asyncio
import discord
import json
import requests

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

# ================= NITRADO =================

NITRADO_API_TOKEN = os.getenv("NITRADO_API_TOKEN")
NITRADO_SERVICE_ID = os.getenv("NITRADO_SERVICE_ID")

# ================= SEARCH PATHS =================

SEARCH_DIRS = [
    "/dayzxb/config",
    "/dayzxb_missions",
    "/config",
    "/profiles",
    "/logs",
    "/adm",
    "/mpmissions",
    "/games/dayzxb/config"
]

LOCAL_LOG_FILE = "live.ADM"

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

# ================= FILE LIST =================

def nitrado_file_list():

    url = (
        f"https://api.nitrado.net/services/"
        f"{NITRADO_SERVICE_ID}/gameservers/file_server/list"
    )

    print(f"URL: {url}")
    print(f"TOKEN EXISTS: {bool(NITRADO_API_TOKEN)}")
    print(f"SERVICE ID: {NITRADO_SERVICE_ID}")

    for search_dir in SEARCH_DIRS:

        try:

            print(f"TRYING DIR: {search_dir}")

            response = requests.get(
                url,
                headers=nitrado_headers(),
                params={"dir": search_dir},
                timeout=30
            )

            print(f"STATUS: {response.status_code}")
            print(f"BODY: {response.text}")

            if response.status_code != 200:
                continue

            data = response.json()

            entries = (
                data.get("data", {})
                .get("entries", [])
            )

            if entries:

                print(f"WORKING DIR: {search_dir}")

                return entries, search_dir

        except Exception as e:

            print(f"DIR ERROR: {search_dir} | {e}")

    return [], None

# ================= DOWNLOAD FILE =================

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
        print(response.text)

        return False

    download_url = (
        response.json()
        .get("data", {})
        .get("token", {})
        .get("url")
    )

    if not download_url:

        print("NO DOWNLOAD URL")
        return False

    file_response = requests.get(download_url, timeout=60)

    if file_response.status_code != 200:

        print("DOWNLOAD FAILED")
        return False

    with open(LOCAL_LOG_FILE, "wb") as f:
        f.write(file_response.content)

    print("ADM DOWNLOADED")

    return True

# ================= EVENT CLASSIFIER =================

def classify_event(line):

    lower = line.lower()

    if "disconnected" in lower:
        return "disconnect"

    if "connecting" in lower or "connected" in lower:
        return "connect"

    if "killed" in lower:
        return "kill"

    if "hit by" in lower or "hit player" in lower:
        return "hit"

    if (
        "placed" in lower
        or "packed" in lower
        or "built" in lower
        or "mounted" in lower
        or "folded" in lower
    ):
        return "build"

    if (
        "unconscious" in lower
        or "regained consciousness" in lower
        or "bled out" in lower
    ):
        return "combat"

    if (
        "destroyed" in lower
        or "dismantled" in lower
        or "breached" in lower
        or "explosive" in lower
    ):
        return "raid"

    return None

# ================= ACTIVE ADM FINDER =================

def extract_filename_datetime(filename):

    match = re.search(
        r'_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$',
        filename
    )

    if not match:
        return None

    iso = (
        f"{match.group(1)} "
        f"{match.group(2).replace('-', ':')}"
    )

    try:

        return datetime.strptime(
            iso,
            "%Y-%m-%d %H:%M:%S"
        )

    except Exception:
        return None


def find_active_adm():

    global current_adm
    global current_adm_size

    try:

        entries, working_dir = nitrado_file_list()

        if not entries:

            print("NO VALID DIRECTORIES FOUND")
            return False

        adm_files = []

        for entry in entries:

            name = entry.get("name", "")

            if not name.endswith(".ADM"):
                continue

            size = int(entry.get("size", 0))

            full_path = f"{working_dir}/{name}"

            adm_files.append({
                "name": name,
                "path": full_path,
                "size": size,
                "dt": extract_filename_datetime(name)
            })

        if not adm_files:

            print("NO ADM FILES FOUND")
            return False

        adm_files.sort(
            key=lambda x: (
                x["dt"] or datetime.min,
                x["size"]
            ),
            reverse=True
        )

        active = adm_files[0]

        current_adm = active["path"]

        if active["size"] <= current_adm_size:

            print("ADM NOT GROWING")
            return False

        current_adm_size = active["size"]

        success = nitrado_download_file(current_adm)

        if not success:

            print("ADM DOWNLOAD FAILED")
            return False

        print(f"ACTIVE ADM: {active['name']}")
        print(f"ADM SIZE: {active['size']}")

        return True

    except Exception as e:

        print(f"ACTIVE ADM ERROR: {e}")
        return False

# ================= ADM MONITOR =================

@tasks.loop(seconds=30)
async def monitor_adm():

    print("CHECKING ADM...")

    success = find_active_adm()

    if success:

        print("ADM UPDATED")

    else:

        print("NO NEW ADM DATA")

# ================= READY =================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    try:

        synced = await bot.tree.sync()

        print(f"SYNCED {len(synced)} COMMANDS")

    except Exception as e:

        print(f"COMMAND SYNC ERROR: {e}")

    if not monitor_adm.is_running():
        monitor_adm.start()

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

load_state()

bot.run(DISCORD_TOKEN)