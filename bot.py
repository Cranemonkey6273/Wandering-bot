import os
import re
import asyncio
import discord
import json

from ftplib import FTP_TLS
from datetime import datetime, UTC, timedelta
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
player_hits = {}
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
        r'_(\\d{4}-\\d{2}-\\d{2})_(\\d{2}-\\d{2}-\\d{2})\\.ADM$',
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
                r'^DayZServer_[A-Z0-9]+_x64_\\d{4}-\\d{2}-\\d{2}_\\d{2}-\\d{2}-\\d{2}\\.ADM$',
                file
            ):
                continue

            file_datetime = extract_filename_datetime(file)

            if not file_datetime:
                continue

            try:

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                if size <= 0:
                    continue

                temp_lines = []

                try:

                    ftp.retrlines(
                        f"RETR {file}",
                        temp_lines.append
                    )

                except Exception:
                    continue

                if not temp_lines:
                    continue

                recent_lines = temp_lines[-150:]

                recent_text = "\\n".join(recent_lines).lower()

                if (
                    "termination successfully completed"
                    in recent_text
                ):
                    continue

                gameplay_patterns = [
                    "connecting",
                    "connected",
                    "disconnected",
                    "killed",
                    "placed",
                    "packed",
                    "built",
                    "mounted",
                    "folded",
                    "hit by",
                    "unconscious",
                    "bled out",
                    "regained consciousness"
                ]

                gameplay_found = any(
                    x in recent_text
                    for x in gameplay_patterns
                )

                if not gameplay_found:
                    continue

                adm_candidates.append({
                    "name": file,
                    "datetime": file_datetime,
                    "size": size
                })

            except Exception as e:

                print(f"FAILED ADM: {file} | {e}")

        ftp.quit()

        if not adm_candidates:

            print("NO VALID ACTIVE ADM FOUND")

            return current_adm

        adm_candidates.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        best = adm_candidates[0]

        newest_adm = (
            f"{SEARCH_DIR}/{best['name']}"
        )

        newest_datetime = best["datetime"]

        if current_adm is None:

            current_adm = newest_adm
            current_adm_size = best["size"]

            adm_state["last_logged_file"] = current_adm

            save_state()

            print(f"INITIAL ACTIVE ADM: {current_adm}")

            return current_adm

        current_filename = os.path.basename(current_adm)

        current_datetime = extract_filename_datetime(
            current_filename
        )

        if (
            current_datetime is None
            or newest_datetime > current_datetime
        ):

            print(f"NEWER ADM DETECTED | SWITCHING -> {newest_adm}")

            current_adm = newest_adm
            current_adm_size = best["size"]

            adm_state["last_line"] = 0
            adm_state["last_text"] = ""
            adm_state["file"] = None
            adm_state["last_modified"] = ""
            adm_state["last_logged_file"] = current_adm

            save_state()

            return current_adm

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return current_adm


# ================= START =================

bot.run(DISCORD_TOKEN)
