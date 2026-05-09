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
current_adm_size = 0

online_players = set()
swear_tracker = {}
delivery_queue = []

SHOP_ITEMS = {
    "water": 10,
    "beans": 20,
    "ammo": 50,
    "medkit": 100,
    "armor": 300,
    "rifle": 600
}

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "wanker",
    "bastard",
    "twat"
]

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


# ================= ACTIVE ADM FINDER =================


def find_active_adm():

    global current_adm
    global current_adm_size

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = ftp.nlst()

        candidates = []

        for file in files:

            if not file.endswith(".ADM"):
                continue

            try:

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                modified = ftp.sendcmd(
                    f"MDTM {file}"
                )

                timestamp = modified[4:].strip()

                if size < 500:
                    continue

                candidates.append({
                    "name": file,
                    "size": size,
                    "timestamp": timestamp
                })

                print(
                    f"FOUND ADM: {file} | "
                    f"SIZE: {size} | "
                    f"{timestamp}"
                )

            except Exception as e:

                print(
                    f"FAILED ADM: {file} | {e}"
                )

        if not candidates:

            ftp.quit()
            return None

        candidates.sort(
            key=lambda x: x["timestamp"],
            reverse=True
        )

        best = None

        for adm in candidates:

            filename = adm["name"]

            temp_lines = []

            try:

                ftp.retrlines(
                    f"RETR {filename}",
                    temp_lines.append
                )

                recent = "\n".join(
                    temp_lines[-50:]
                )

                if (
                    "Termination successfully completed"
                    in recent
                ):

                    continue

                if (
                    "AdminLog started on"
                    in recent
                    or len(temp_lines) > 100
                ):

                    best = adm
                    break

            except Exception as e:

                print(
                    f"READ CHECK FAILED: "
                    f"{filename} | {e}"
                )

        if not best:

            candidates.sort(
                key=lambda x: x["size"],
                reverse=True
            )

            best = candidates[0]

        new_path = (
            f"{SEARCH_DIR}/{best['name']}"
        )

        if current_adm != new_path:

            print(
                f"NEW ACTIVE ADM: {new_path}"
            )

            current_adm = new_path
            current_adm_size = best["size"]

            processed_lines.clear()

        print(
            f"ACTIVE ADM: {current_adm} | "
            f"SIZE: {current_adm_size}"
        )

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
            "killstreak": 0,
            "inventory": []
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
    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)
    build_channel = bot.get_channel(BUILD_CHANNEL_ID)
    deploy_channel = bot.get_channel(DEPLOY_CHANNEL_ID)
    raid_channel = bot.get_channel(RAID_CHANNEL_ID)

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

        if "connecting" in lower:

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match and connect_channel:

                player_name = player_match.group(1)

                embed = discord.Embed(
        title="📦 Purchase Successful",
        description=(
            f"Bought: {item}\n"
            f"Cost: ${cost}\n"
            f"Added to delivery queue"
        ),
        color=0x3498DB
    )

    await interaction.response.send_message(
        embed=style_embed(embed)
    )


@bot.tree.command(
    name="inventory",
    description="View inventory"
)
async def inventory(interaction: discord.Interaction):

    await ensure_player(
        str(interaction.user.id),
        interaction.user.name
    )

    player = await get_player(
        str(interaction.user.id)
    )

    inventory_items = player.get("inventory", [])

    if not inventory_items:
        inventory_text = "\n".join(inventory_items)

    embed = discord.Embed(
        title="🎒 Inventory",
        description=inventory_text,
        color=0x9B59B6
    )

    await interaction.response.send_message(
        embed=style_embed(embed)
    )


# ================= START =================

bot.run(DISCORD_TOKEN)
