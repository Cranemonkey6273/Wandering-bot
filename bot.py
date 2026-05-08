import os
import re
import random
import asyncio
import discord
import berconpy

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks
from discord import app_commands
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
DEPLOY_CHANNEL_ID = int(os.getenv("DEPLOY_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

# ================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"

LOCAL_LOG_FILE = "live.ADM"

# ================= RCON =================

RCON_HOST = os.getenv("RCON_HOST")
RCON_PORT = int(os.getenv("RCON_PORT", 2302))
RCON_PASSWORD = os.getenv("RCON_PASSWORD")

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= OPENAI =================

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY
)

# ================= SUPABASE =================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 5000

current_adm = None
current_adm_size = 0

online_players = set()

last_line_count = 0
last_growth_time = datetime.now(UTC)

growth_fail_count = 0

dead_adms = set()

# ================= SWEAR TRACKER =================

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "wanker",
    "bastard",
    "twat"
]

swear_tracker = {}

# ================= ECONOMY =================

SHOP_ITEMS = {
    "water": 10,
    "beans": 20,
    "ammo": 50,
    "medkit": 100,
    "armor": 300,
    "rifle": 600
}

# ================= FILTERS =================

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

# ================= BOT IMAGE =================

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

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
        timeout=60
    )

    ftp.login(
        FTP_USER,
        FTP_PASS
    )

    ftp.prot_p()

    return ftp


# ================= RCON LOOP =================

async def rcon_loop():

    while True:

        try:

            print("CONNECTING TO RCON...")

            rcon = berconpy.Client()

            await rcon.connect(
                RCON_HOST,
                RCON_PORT,
                RCON_PASSWORD
            )

            print("RCON CONNECTED")

            while True:

                response = await rcon.command(
                    "players"
                )

                print(
                    f"RCON PLAYERS:\n{response}"
                )

                await asyncio.sleep(30)

        except Exception as e:

            print(f"RCON ERROR: {e}")

            await asyncio.sleep(10)


# ================= LIVE ADM FINDER =================

def find_active_adm():

    global current_adm
    global current_adm_size
    global last_line_count
    global last_growth_time
    global growth_fail_count
    global dead_adms

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = []

        ftp.retrlines(
            "NLST",
            files.append
        )

        files = sorted(files)

        adm_files = []

        for file in files:

            if not file.endswith(".ADM"):
                continue

            full_path = f"{SEARCH_DIR}/{file}"

            if full_path in dead_adms:
                continue

            match = re.search(
                r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})",
                file
            )

            if not match:
                continue

            try:

                dt_str = (
                    match.group(1)
                    + " "
                    + match.group(2).replace("-", ":")
                )

                file_dt = datetime.strptime(
                    dt_str,
                    "%Y-%m-%d %H:%M:%S"
                )

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                adm_files.append({
                    "name": file,
                    "datetime": file_dt,
                    "size": size
                })

                print(
                    f"FOUND ADM: {file} | "
                    f"SIZE: {size} | "
                    f"START: {file_dt}"
                )

            except Exception as e:

                print(
                    f"ADM PARSE ERROR: {e}"
                )

        if not adm_files:

            ftp.quit()

            print("NO VALID ADM FILES FOUND")

            return None

        adm_files.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        best_adm = adm_files[0]

        best_path = (
            f"{SEARCH_DIR}/{best_adm['name']}"
        )

        best_size = best_adm["size"]

        print(
            f"BEST ADM CANDIDATE: "
            f"{best_path} | SIZE: {best_size}"
        )

        if current_adm is None:

            current_adm = best_path
            current_adm_size = best_size

            growth_fail_count = 0
            last_line_count = 0

            processed_lines.clear()

            last_growth_time = datetime.now(UTC)

            print(
                f"INITIAL ADM: {current_adm}"
            )

            ftp.quit()

            return current_adm

        current_file = None

        for adm in adm_files:

            full_path = (
                f"{SEARCH_DIR}/{adm['name']}"
            )

            if full_path == current_adm:

                current_file = adm
                break

        if current_file:

            latest_size = current_file["size"]

            if latest_size > current_adm_size:

                print(
                    f"ACTIVE ADM GROWING: "
                    f"{latest_size}"
                )

                current_adm_size = latest_size

                last_growth_time = datetime.now(UTC)

                growth_fail_count = 0

                ftp.quit()

                return current_adm

            else:

                growth_fail_count += 1

                print(
                    f"ADM NOT GROWING | "
                    f"FAIL COUNT: {growth_fail_count}"
                )

                print(
                    f"ADM SIZE STATIC: {latest_size}"
                )

        if growth_fail_count >= 3:

            print(
                "CURRENT ADM DEAD - SEARCHING NEW FILE"
            )

            for adm in adm_files:

                possible_path = (
                    f"{SEARCH_DIR}/{adm['name']}"
                )

                if possible_path == current_adm:
                    continue

                if (
                    current_file
                    and adm["datetime"]
                    <= current_file["datetime"]
                ):
                    continue

                print(
                    f"SWITCHING TO NEW ADM: "
                    f"{possible_path}"
                )

                current_adm = possible_path
                current_adm_size = adm["size"]

                growth_fail_count = 0
                last_line_count = 0

                processed_lines.clear()

                last_growth_time = datetime.now(UTC)

                ftp.quit()

                return current_adm

        ftp.quit()

        print(f"ACTIVE ADM: {current_adm}")

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return None


# ================= DOWNLOAD ADM =================

def download_adm():

    try:

        active_adm = find_active_adm()

        if not active_adm:
            return False

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        ftp.voidcmd("TYPE I")

        filename = os.path.basename(
            active_adm
        )

        if os.path.exists(LOCAL_LOG_FILE):
            os.remove(LOCAL_LOG_FILE)

        with open(
            LOCAL_LOG_FILE,
            "wb"
        ) as f:

            ftp.retrbinary(
                f"RETR {filename}",
                f.write,
                blocksize=1024
            )

        ftp.quit()

        size = os.path.getsize(
            LOCAL_LOG_FILE
        )

        print(
            f"ADM DOWNLOADED | SIZE: {size}"
        )

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False


# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    if not adm_loop.is_running():
        adm_loop.start()

    asyncio.create_task(rcon_loop())

    print(f"✅ Logged in as {bot.user}")


# ================= TASKS =================

@tasks.loop(seconds=30)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

    print(f"DOWNLOAD RESULT: {success}")


# ================= START =================

bot.run(DISCORD_TOKEN)
