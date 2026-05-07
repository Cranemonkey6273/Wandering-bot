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

================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

================= CHANNEL IDS =================

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))

KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))

BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
DEPLOY_CHANNEL_ID = int(os.getenv("DEPLOY_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"

LOCAL_LOG_FILE = "live.ADM"

================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
command_prefix="!",
intents=intents
)

================= OPENAI =================

client = AsyncOpenAI(
api_key=OPENAI_API_KEY
)

================= SUPABASE =================

supabase = create_client(
SUPABASE_URL,
SUPABASE_KEY
)

================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 2000

current_adm = None
current_adm_size = 0

online_players = set()

TRACK LIVE ADM STATE

last_line_count = 0
last_growth_time = datetime.now(UTC)

TRACK STALE FILES

growth_fail_count = 0

================= SWEAR TRACKER =================

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

================= ECONOMY =================

SHOP_ITEMS = {
"water": 10,
"beans": 20,
"ammo": 50,
"medkit": 100,
"armor": 300,
"rifle": 600
}

================= FILTERS =================

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

================= BOT IMAGE =================

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

================= HELPERS =================

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
================= LIVE ADM FINDER =================

def find_active_adm():

global current_adm
global current_adm_size
global last_line_count
global last_growth_time
global growth_fail_count

try:

    ftp = connect_ftp()

    ftp.cwd(SEARCH_DIR)

    files = ftp.nlst()

    adm_files = []

    for file in files:

        if not file.endswith(".ADM"):
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
                f"SIZE: {size}"
            )

        except Exception as e:

            print(
                f"ADM PARSE ERROR: {e}"
            )

    ftp.quit()

    if not adm_files:
        return None

    # SORT NEWEST FIRST
    adm_files.sort(
        key=lambda x: x["datetime"],
        reverse=True
    )

    newest = adm_files[0]

    newest_adm = (
        f"{SEARCH_DIR}/{newest['name']}"
    )

    newest_size = newest["size"]

    # FIRST RUN
    if current_adm is None:

        current_adm = newest_adm
        current_adm_size = newest_size

        print(
            f"INITIAL ADM: {current_adm}"
        )

        return current_adm

    # FIND CURRENT FILE
    current_file = None

    for adm in adm_files:

        full_path = (
            f"{SEARCH_DIR}/{adm['name']}"
        )

        if full_path == current_adm:

            current_file = adm
            break

    # CURRENT FILE GROWING
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

            return current_adm

        else:

            growth_fail_count += 1

            print(
                f"ADM NOT GROWING | "
                f"FAIL COUNT: {growth_fail_count}"
            )

    # SEARCH FOR NEW GROWING FILE
    if growth_fail_count >= 3:

        print(
            "SEARCHING FOR NEW GROWING ADM..."
        )

        for adm in adm_files:

            possible_adm = (
                f"{SEARCH_DIR}/{adm['name']}"
            )

            possible_size = adm["size"]

            if possible_adm == current_adm:
                continue

            if possible_size < 500:
                continue

            print(
                f"SWITCHING TO NEW LIVE ADM: "
                f"{possible_adm}"
            )

            current_adm = possible_adm
            current_adm_size = possible_size

            growth_fail_count = 0
            last_line_count = 0

            processed_lines.clear()

            last_growth_time = datetime.now(UTC)

            return current_adm

    # FAILSAFE
    time_since_growth = (
        datetime.now(UTC)
        - last_growth_time
    ).total_seconds()

    if time_since_growth > 14400:

        print(
            "ADM DEAD OVER 4 HOURS "
            "- FORCING NEWEST FILE"
        )

        current_adm = newest_adm
        current_adm_size = newest_size

        growth_fail_count = 0
        last_line_count = 0

        processed_lines.clear()

        last_growth_time = datetime.now(UTC)

    print(f"ACTIVE ADM: {current_adm}")

    return current_adm

except Exception as e:

    print(f"ADM SEARCH ERROR: {e}")

    return None
================= DOWNLOAD ADM =================

def download_adm():

try:

    active_adm = find_active_adm()

    if not active_adm:
        return False

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
================= READY =================

@bot.event
async def on_ready():

await bot.tree.sync()

if not adm_loop.is_running():
    adm_loop.start()

print(f"✅ Logged in as {bot.user}")
================= SWEAR TRACKER =================

@bot.event
async def on_message(message):

if message.author.bot:
    return

lower = message.content.lower()

count = 0

for swear in SWEAR_WORDS:
    count += lower.count(swear)

if count > 0:

    user_id = str(message.author.id)

    if user_id not in swear_tracker:

        swear_tracker[user_id] = {
            "name": message.author.name,
            "count": 0
        }

    swear_tracker[user_id]["count"] += count

await bot.process_commands(message)
================= ADM PARSER =================

async def parse_adm():

global processed_lines
global last_line_count

if not os.path.exists(LOCAL_LOG_FILE):

    print("LOCAL ADM MISSING")
    return

try:

    with open(
        LOCAL_LOG_FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

except Exception as e:

    print(f"ADM READ ERROR: {e}")
    return

total_lines = len(lines)

print(f"ADM TOTAL LINES: {total_lines}")

new_lines = lines[last_line_count:]

print(
    f"NEW LINES FOUND: {len(new_lines)}"
)

last_line_count = total_lines

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

    if len(processed_lines) > MAX_PROCESSED_LINES:
        processed_lines.clear()

    if should_ignore(line):
        continue

    lower = line.lower()

    if (
        "is connecting" in lower
        or "connecting" in lower
    ):

        player_match = re.search(
            r'Player\s+"([^"]+)"',
            line,
            re.IGNORECASE
        )

        if player_match and connect_channel:

            player_name = player_match.group(1)

            embed = discord.Embed(
                description=(
                    f"🛰️ {player_name} connecting\n"
                    f"🕒 {line[:8]}"
                ),
                color=0x9C8A00
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Intelligence"
            )

            await connect_channel.send(
                embed=embed
            )

    elif (
        "is connected" in lower
        or "connected" in lower
    ):

        player_match = re.search(
            r'Player\s+"([^"]+)"',
            line,
            re.IGNORECASE
        )

        if player_match and connect_channel:

            player_name = player_match.group(1)

            online_players.add(player_name)

            embed = discord.Embed(
                description=(
                    f"☣️ {player_name} connected\n"
                    f"🕒 {line[:8]}"
                ),
                color=0x4E7F3D
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Intelligence"
            )

            await connect_channel.send(
                embed=embed
            )

    elif (
        "has been disconnected" in lower
        or "disconnected" in lower
    ):

        player_match = re.search(
            r'Player\s+"([^"]+)"',
            line,
            re.IGNORECASE
        )

        if player_match and connect_channel:

            player_name = player_match.group(1)

            online_players.discard(player_name)

            embed = discord.Embed(
                description=(
                    f"❌ {player_name} disconnected\n"
                    f"🕒 {line[:8]}"
                ),
                color=0x8E2E2E
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Intelligence"
            )

            await connect_channel.send(
                embed=embed
            )
================= TASKS =================

@tasks.loop(seconds=30)
async def adm_loop():

success = await asyncio.to_thread(
    download_adm
)

if success:
    await parse_adm()
================= START =================

bot.run(DISCORD_TOKEN)
