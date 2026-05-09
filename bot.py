import os
import re
import asyncio
import discord
import json
import requests

from ftplib import FTP_TLS
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


def connect_ftp():

    ftp = FTP_TLS()

    ftp.connect(
        FTP_HOST,
        FTP_PORT,
        timeout=30
    )

    ftp.login(
        FTP_USER,
        FTP_PASS
    )

    try:
        ftp.prot_p()

    except Exception as e:
        print(f"FTP TLS WARNING: {e}")

    ftp.set_pasv(True)

    return ftp


# ================= EVENT CLASSIFIER =================


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
        "hit by" in lower
        or "hit player" in lower
    ):
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

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = ftp.nlst()

        adm_candidates = []

        for file in files:

            if not re.match(
                r'^DayZServer_[A-Z0-9]+_x64_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.ADM$',
                file
            ):
                continue

            file_datetime = extract_filename_datetime(file)

            if not file_datetime:
                continue

            ftp.voidcmd("TYPE I")

            size = ftp.size(file)

            adm_candidates.append({
                "name": file,
                "datetime": file_datetime,
                "size": size
            })

        ftp.quit()

        if not adm_candidates:
            return current_adm

        adm_candidates.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        best = adm_candidates[0]

        newest_adm = (
            f"{SEARCH_DIR}/{best['name']}"
        )

        if current_adm != newest_adm:

            current_adm = newest_adm
            current_adm_size = best["size"]

            adm_state["last_line"] = 0
            adm_state["last_text"] = ""

            save_state()

            print(f"ACTIVE ADM: {current_adm}")

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return current_adm


# ================= DOWNLOAD ADM =================


def download_adm():

    global current_adm_size

    try:

        active_adm = find_active_adm()

        if not active_adm:
            return False

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        filename = os.path.basename(active_adm)

        ftp.voidcmd("TYPE I")

        current_size = ftp.size(filename)

        if current_size <= current_adm_size:

            ftp.quit()
            return False

        current_adm_size = current_size

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {filename}",
                f.write
            )

        ftp.quit()

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
