import os
import re
import random
import asyncio
import discord

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks
from discord import app_commands
from supabase import create_client
from openai import AsyncOpenAI

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
DEPLOY_CHANNEL_ID = int(os.getenv("DEPLOY_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIRS = [
    "config",
    "/config",
    "dayzxb/config",
    "/dayzxb/config",
    "profiles",
    "/profiles"
]

LOCAL_LOG_FILE = "live.ADM"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

processed_lines = set()
MAX_PROCESSED_LINES = 2000

current_adm = None
current_adm_size = 0

online_players = set()

last_line_count = 0
last_growth_time = datetime.now(UTC)

growth_fail_count = 0

dead_adms = set()

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

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

def should_ignore(line):

    lower = line.lower()

    for pattern in IGNORE_PATTERNS:

        if pattern.lower() in lower:
            return True

    return False

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

def find_working_path(ftp):

    for path in SEARCH_DIRS:

        try:

            ftp.cwd(path)

            files = []

            ftp.retrlines(
                "NLST",
                files.append
            )

            adm_files = [
                f for f in files
                if f.endswith(".ADM")
            ]

            print(
                f"CHECKING PATH: {path} | "
                f"ADM FILES: {len(adm_files)}"
            )

            if adm_files:

                print(f"WORKING PATH FOUND: {path}")

                return path

        except Exception as e:

            print(f"PATH FAILED: {path} | {e}")

    return None

def find_active_adm():

    global current_adm
    global current_adm_size
    global last_line_count
    global last_growth_time
    global growth_fail_count
    global dead_adms

    try:

        ftp = connect_ftp()

        working_dir = find_working_path(ftp)

        if not working_dir:

            print("NO WORKING ADM DIRECTORY FOUND")

            ftp.quit()

            return None

        files = []

        ftp.retrlines(
            "NLST",
            files.append
        )

        adm_files = []

        for file in files:

            if not file.endswith(".ADM"):
                continue

            full_path = f"{working_dir}/{file}"

            if full_path in dead_adms:
                continue

            try:

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                if size < 1000:

                    print(
                        f"IGNORING SMALL ADM: "
                        f"{file} | SIZE: {size}"
                    )

                    continue

                match = re.search(
                    r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})",
                    file
                )

                if not match:
                    continue

                dt_str = (
                    match.group(1)
                    + " "
                    + match.group(2).replace("-", ":")
                )

                start_time = datetime.strptime(
                    dt_str,
                    "%Y-%m-%d %H:%M:%S"
                )

                adm_files.append({
                    "name": file,
                    "size": size,
                    "start": start_time
                })

                print(
                    f"FOUND ADM: {file} | "
                    f"SIZE: {size} | "
                    f"START: {start_time}"
                )

            except Exception as e:

                print(f"ADM PARSE ERROR: {e}")

        if not adm_files:

            ftp.quit()

            print("NO VALID ADM FILES FOUND")

            return None

        adm_files.sort(
            key=lambda x: x["start"],
            reverse=True
        )

        best_adm = adm_files[0]

        best_path = f"{working_dir}/{best_adm['name']}"
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

            print(f"INITIAL ADM: {current_adm}")

            ftp.quit()

            return current_adm

        current_file = None

        for adm in adm_files:

            full_path = f"{working_dir}/{adm['name']}"

            if full_path == current_adm:

                current_file = adm

                break

        if current_file:

            latest_size = current_file["size"]

            if latest_size > current_adm_size:

                print(f"ACTIVE ADM GROWING: {latest_size}")

                current_adm_size = latest_size

                last_growth_time = datetime.now(UTC)

                growth_fail_count = 0

            else:

                growth_fail_count += 1

                print(f"ADM SIZE STATIC: {latest_size}")

            try:

                temp_lines = []

                ftp.retrlines(
                    f"RETR {os.path.basename(current_adm)}",
                    temp_lines.append
                )

                recent_lines = temp_lines[-30:]

                recent_text = "\n".join(recent_lines)

                has_heartbeat = "#####" in recent_text

                disconnected_end = (
                    "has been disconnected"
                    in recent_text.lower()
                )

                terminated = (
                    "termination successfully completed"
                    in recent_text.lower()
                )

                if (
                    (disconnected_end or terminated)
                    and not has_heartbeat
                ):

                    print(
                        f"MARKING DEAD ADM: "
                        f"{current_adm}"
                    )

                    dead_adms.add(current_adm)

                    current_adm = None
                    current_adm_size = 0

                    growth_fail_count = 0
                    last_line_count = 0

                    processed_lines.clear()

                    ftp.quit()

                    return find_active_adm()

            except Exception as e:

                print(f"END CHECK ERROR: {e}")

        newest_start = best_adm["start"]

        current_start = current_file["start"]

        if newest_start > current_start:

            print(
                f"NEWER ADM DETECTED: "
                f"{best_path}"
            )

            current_adm = best_path
            current_adm_size = best_size

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

def download_adm():

    try:

        active_adm = find_active_adm()

        if not active_adm:
            return False

        ftp = connect_ftp()

        working_dir = os.path.dirname(active_adm)

        ftp.cwd(working_dir)

        ftp.voidcmd("TYPE I")

        filename = os.path.basename(active_adm)

        if os.path.exists(LOCAL_LOG_FILE):
            os.remove(LOCAL_LOG_FILE)

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {filename}",
                f.write,
                blocksize=1024
            )

        ftp.quit()

        size = os.path.getsize(LOCAL_LOG_FILE)

        print(f"ADM DOWNLOADED | SIZE: {size}")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False

@tasks.loop(seconds=30)
async def adm_loop():

    print("ADM LOOP RUNNING")

    try:

        success = await asyncio.to_thread(
            download_adm
        )

        print(f"DOWNLOAD RESULT: {success}")

        if success:

            print("STARTING PARSE")

        else:

            print("DOWNLOAD FAILED")

    except Exception as e:

        print(f"ADM LOOP ERROR: {e}")

@bot.event
async def on_ready():

    print("BOT READY EVENT")

    if not adm_loop.is_running():

        adm_loop.start()

    print(f"Logged in as {bot.user}")

bot.run(DISCORD_TOKEN)
