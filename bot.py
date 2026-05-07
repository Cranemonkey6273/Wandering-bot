import os
import re
import random
import discord

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
MAX_PROCESSED_LINES = 2000

current_adm = None
online_players = set()

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


# ================= FIXED ADM FINDER =================

def find_active_adm():

    global current_adm

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        # IMPORTANT FIX
        # Force binary mode so SIZE works
        ftp.voidcmd("TYPE I")

        files = ftp.nlst()

        adm_files = []

        for file in files:

            if file.endswith(".ADM"):

                try:

                    modified = ftp.sendcmd(f"MDTM {file}")

                    size = ftp.size(file)

                    adm_files.append({
                        "name": file,
                        "size": size,
                        "modified": modified
                    })

                    print(
                        f"FOUND ADM: {file} | "
                        f"SIZE: {size} | "
                        f"{modified}"
                    )

                except Exception as e:

                    print(f"FILE CHECK ERROR: {e}")

        if not adm_files:

            ftp.quit()
            return None

        # Sort newest first
        adm_files.sort(
            key=lambda x: x["modified"],
            reverse=True
        )

        print("=== RECENT ADM FILES ===")

        for adm in adm_files[:10]:

            print(
                f"{adm['name']} | "
                f"SIZE: {adm['size']} | "
                f"{adm['modified']}"
            )

        # IMPORTANT FIX
        # Ignore tiny restart logs

        valid_logs = [
            adm for adm in adm_files
            if adm["size"] > 50000
        ]

        # fallback if none exist
        if not valid_logs:
            valid_logs = adm_files

        # choose newest valid log
        best_adm = valid_logs[0]

        current_adm = (
            f"{SEARCH_DIR}/{best_adm['name']}"
        )

        print(
            f"ACTIVE ADM: {current_adm} | "
            f"SIZE: {best_adm['size']}"
        )

        ftp.quit()

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return None


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

        # IMPORTANT FIX
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


async def ensure_player(discord_id, username):

    result = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if not result.data:

        supabase.table(
            "player_data"
        ).insert({
            "discord_id": discord_id,
            "username": username,
            "scrap": 1000,
            "bank": 0,
            "kills": 0,
            "deaths": 0,
            "xp": 0,
            "level": 1,
            "bounty": 0,
            "vehicles": 0,
            "faction": "",
            "territory": "",
            "heat": 0,
            "killstreak": 0
        }).execute()


async def get_player(discord_id):

    result = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if result.data:
        return result.data[0]

    return None


# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    # ONLY start ADM loop for now
    if not adm_loop.is_running():
        adm_loop.start()

    print(f"✅ Logged in as {bot.user}")


# ================= SWEAR TRACKER =================

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


# ================= ADM PARSER =================

async def parse_adm():

    global processed_lines

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

    print(f"ADM LINES READ: {len(lines)}")

    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)

    for raw_line in lines:

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
                embed.set_footer(text="Wandering Bot Intelligence")

                await connect_channel.send(embed=embed)

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
                embed.set_footer(text="Wandering Bot Intelligence")

                await connect_channel.send(embed=embed)

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
                embed.set_footer(text="Wandering Bot Intelligence")

                await connect_channel.send(embed=embed)


# ================= TASKS =================

@tasks.loop(seconds=30)
async def adm_loop():

    success = download_adm()

    if success:
        await parse_adm()


# ================= START =================

bot.run(DISCORD_TOKEN)
