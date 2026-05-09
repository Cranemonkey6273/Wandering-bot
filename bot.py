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

adm_state = {
    "file": None,
    "last_line": 0,
    "last_text": "",
    "last_modified": ""
}

current_adm = None
current_adm_size = 0

online_players = set()
swear_tracker = {}
delivery_queue = []
adm_growth_tracker = {}

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


import re
from datetime import datetime


def extract_filename_datetime(filename):

    match = re.search(
        r'_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.ADM$',
        filename
    )

    if not match:
        return None

    try:

        iso = (
            f"{match.group(1)} "
            f"{match.group(2).replace('-', ':')}"
        )

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
                r'^DayZServer_[A-Z0-9]+_x64_'
                r'\d{4}-\d{2}-\d{2}_'
                r'\d{2}-\d{2}-\d{2}\.ADM$',
                file
            ):
                continue

            file_datetime = extract_filename_datetime(
                file
            )

            if not file_datetime:
                continue

            try:

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                temp_lines = []

                try:

                    ftp.retrlines(
                        f"RETR {file}",
                        temp_lines.append
                    )

                except Exception:
                    continue

                recent_lines = temp_lines[-100:]

                recent_text = "\n".join(
                    recent_lines
                )

                if (
                    "Termination successfully completed"
                    in recent_text
                ):
                    continue

                gameplay_found = False

                gameplay_patterns = [
                    "connecting",
                    "connected",
                    "killed",
                    "placed",
                    "packed",
                    "built",
                    "destroyed"
                ]

                for line in recent_lines:

                    lower = line.lower()

                    if any(
                        x in lower
                        for x in gameplay_patterns
                    ):
                        gameplay_found = True
                        break

                if not gameplay_found:
                    continue

                adm_candidates.append({
                    "name": file,
                    "datetime": file_datetime,
                    "size": size
                })

                print(
                    f"VALID ADM: {file} | "
                    f"{file_datetime} | "
                    f"SIZE: {size}"
                )

            except Exception as e:

                print(
                    f"FAILED ADM: {file} | {e}"
                )

        ftp.quit()

        if not adm_candidates:

            print("NO VALID ACTIVE ADM FOUND")
            return current_adm

        adm_candidates.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        best = adm_candidates[0]

        current_adm = (
            f"{SEARCH_DIR}/{best['name']}"
        )

        current_adm_size = best["size"]

        print(
            f"ACTIVE ADM: {current_adm}"
        )

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return current_adm

        active_candidates.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        best = active_candidates[0]

        new_path = (
            f"{SEARCH_DIR}/{best['name']}"
        )

        if current_adm != new_path:

            print(
                f"NEW ACTIVE ADM DETECTED: {new_path}"
            )

            processed_lines.clear()
            adm_state["last_line"] = 0

        current_adm = new_path
        current_adm_size = best["size"]

        print(
            f"ACTIVE ADM: {current_adm} | "
            f"SIZE: {current_adm_size} | "
            f"GROWTH: {best['growth']}"
        )

        ftp.quit()

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return current_adm


# ================= DOWNLOAD ADM =================


def download_adm():

    global adm_state

    try:

        active_adm = find_active_adm()

        if not active_adm:
            return False

        ftp = connect_ftp()

        filename = os.path.basename(active_adm)

        modified = ftp.sendcmd(
            f"MDTM {filename}"
        )

        timestamp = modified[4:].strip()

        if (
            adm_state["file"] == active_adm
            and adm_state["last_modified"] == timestamp
        ):

            ftp.quit()

            print("ADM UNCHANGED")

            return False

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {active_adm}",
                f.write
            )

        ftp.quit()

        adm_state["file"] = active_adm
        adm_state["last_modified"] = timestamp

        print("ADM UPDATED AND DOWNLOADED")

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

    start_index = adm_state.get(
        "last_line",
        0
    )

    last_text = adm_state.get(
        "last_text",
        ""
    )

    if last_text:

        found_index = None

        for i, line in enumerate(lines):

            if last_text in line:
                found_index = i

        if found_index is not None:
            start_index = found_index + 1

    new_lines = lines[start_index:]

    adm_state["last_line"] = len(lines)

    if lines:
        adm_state["last_text"] = lines[-1].strip()

    print(f"NEW ADM LINES: {len(new_lines)}")

    killfeed_channel = bot.get_channel(KILLFEED_CHANNEL_ID)
    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)

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

        if "connecting" in lower:

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

                await connect_channel.send(
                    embed=style_embed(embed)
                )

        elif "killed" in lower:

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

                await killfeed_channel.send(
                    embed=style_embed(embed)
                )


# ================= TASK LOOP =================


@tasks.loop(seconds=10)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

    if success:
        await parse_adm()


# ================= READY =================


@bot.event
async def on_ready():

    await bot.tree.sync()

    try:
        adm_loop.start()
    except RuntimeError:
        pass

    print(f"✅ Logged in as {bot.user}")


# ================= SHOP =================


@bot.tree.command(
    name="shop",
    description="View shop items"
)
async def shop(interaction: discord.Interaction):

    desc = ""

    for item, price in SHOP_ITEMS.items():
        desc += f"{item} — ${price}\n"

    embed = discord.Embed(
        title="🛒 Survivor Shop",
        description=desc,
        color=0x2ECC71
    )

    await interaction.response.send_message(
        embed=style_embed(embed)
    )


# ================= INVENTORY =================


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

    inventory_items = player.get(
        "inventory",
        []
    )

    if inventory_items:
        inventory_text = "\n".join(
            inventory_items
        )
    else:
        inventory_text = "Inventory empty."

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
