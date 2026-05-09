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
MAX_PROCESSED_LINES = 5000

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


def should_ignore(line):

    lower = line.lower()

    for pattern in IGNORE_PATTERNS:

        if pattern.lower() in lower:
            return True

    return False


# ================= HELPERS =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    return embed


BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"


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


# ================= LIVE ADM FINDER =================

def find_active_adm():

    global current_adm

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = ftp.nlst()

        adm_files = []

        for file in files:

            if file.endswith(".ADM"):

                try:

                    modified = ftp.sendcmd(f"MDTM {file}")

                    timestamp = modified[4:].strip()

                    adm_files.append((file, timestamp))

                    print(f"FOUND ADM: {file} | {timestamp}")

                except Exception as e:

                    print(f"FAILED MDTM: {file} | {e}")

        if not adm_files:

            ftp.quit()

            return None

        adm_files.sort(
            key=lambda x: x[1],
            reverse=True
        )

        newest_file = adm_files[0][0]

        new_path = f"{SEARCH_DIR}/{newest_file}"

        if current_adm != new_path:

            print(f"NEWER ADM DETECTED: {new_path}")

            current_adm = new_path

        print(f"ACTIVE ADM: {current_adm}")

        ftp.quit()

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

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {active_adm}",
                f.write
            )

        ftp.quit()

        print("ADM DOWNLOADED")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False


# ================= PLAYER DATA =================

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

    killfeed_channel = bot.get_channel(KILLFEED_CHANNEL_ID)
    raid_channel = bot.get_channel(RAID_CHANNEL_ID)
    build_channel = bot.get_channel(BUILD_CHANNEL_ID)
    deploy_channel = bot.get_channel(DEPLOY_CHANNEL_ID)
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

                embed = discord.Embed(
                    description=(
                        f"☣️ {player_name} connected\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x4E7F3D
                )

                await connect_channel.send(embed=embed)

        elif (
            "killed by player" in lower
            or "killed" in lower
        ):

            victim_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            killer_match = re.search(
                r'by Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if (
                victim_match
                and killer_match
                and killfeed_channel
            ):

                victim = victim_match.group(1)
                killer = killer_match.group(1)

                embed = discord.Embed(
                    description=(
                        f"☠️ {killer} killed {victim}\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0xC0392B
                )

                await killfeed_channel.send(embed=embed)


# ================= TASKS =================

@tasks.loop(seconds=60)
async def adm_loop():

    success = download_adm()

    if success:
        await parse_adm()


@tasks.loop(minutes=20)
async def world_events():

    channel = bot.get_channel(EVENT_CHANNEL_ID)

    if not channel:
        return

    events = [
        "🚁 Helicopter crash reported.",
        "☣️ Toxic gas spreading.",
        "📻 Convoy entering Chernarus.",
        "💥 Heavy fighting near NWAF."
    ]

    embed = discord.Embed(
        title="📡 World Event",
        description=random.choice(events),
        color=0x9B59B6
    )

    await channel.send(embed=style_embed(embed))


@tasks.loop(minutes=25)
async def ai_radio():

    channel = bot.get_channel(EVENT_CHANNEL_ID)

    if not channel:
        return

    chatter = [
        "📻 Gunfire heard near Tisy.",
        "📻 Survivors spotted near Vybor.",
        "📻 Trader convoy requesting escort."
    ]

    embed = discord.Embed(
        title="📻 Radio Chatter",
        description=random.choice(chatter),
        color=0x3498DB
    )

    await channel.send(embed=style_embed(embed))


# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    world_events.start()
    adm_loop.start()
    ai_radio.start()

    print(f"✅ Logged in as {bot.user}")


# ================= START =================

bot.run(DISCORD_TOKEN)
