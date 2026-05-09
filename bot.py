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
                    description=f"🛰️ {player_name} connecting",
                    color=0x9C8A00
                )

                await connect_channel.send(embed=embed)

        elif "connected" in lower:

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match and connect_channel:

                player_name = player_match.group(1)

                online_players.add(player_name)

                embed = discord.Embed(
                    description=f"☣️ {player_name} connected",
                    color=0x4E7F3D
                )

                await connect_channel.send(embed=embed)

        elif any(x in lower for x in [
            "built",
            "watchtower",
            "fence",
            "gate"
        ]):

            if build_channel:

                embed = discord.Embed(
                    description=f"🔨 Build Event\n{line[:120]}",
                    color=0x2ECC71
                )

                await build_channel.send(embed=embed)

        elif any(x in lower for x in [
            "placed",
            "deployed",
            "barrel",
            "seachest"
        ]):

            if deploy_channel:

                embed = discord.Embed(
                    description=f"📦 Deploy Event\n{line[:120]}",
                    color=0xF1C40F
                )

                await deploy_channel.send(embed=embed)

        elif any(x in lower for x in [
            "destroyed",
            "breached",
            "raid"
        ]):

            if raid_channel:

                embed = discord.Embed(
                    description=f"💥 Raid Alert\n{line[:120]}",
                    color=0xE74C3C
                )

                await raid_channel.send(embed=embed)

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

                reward = random.randint(100, 500)

                embed = discord.Embed(
                    description=(
                        f"☠️ {killer} killed {victim}\n"
                        f"💰 Reward: {reward}"
                    ),
                    color=0xC0392B
                )

                await killfeed_channel.send(embed=embed)


# ================= TASKS =================


@tasks.loop(seconds=5)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

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
        "💥 Heavy fighting near NWAF.",
        "🏴 Faction conflict escalating.",
        "📦 Supply crate detected."
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
        "📻 Trader convoy requesting escort.",
        "📻 Black market trader active tonight.",
        "📻 Toxic storm approaching."
    ]

    embed = discord.Embed(
        title="📻 Radio Chatter",
        description=random.choice(chatter),
        color=0x3498DB
    )

    await channel.send(embed=style_embed(embed))


@tasks.loop(hours=2)
async def territory_income():

    results = supabase.table(
        "player_data"
    ).select("*").neq(
        "territory",
        ""
    ).execute()

    for player in results.data:

        income = random.randint(100, 300)

        supabase.table(
            "player_data"
        ).update({
            "scrap": player["scrap"] + income
        }).eq(
            "discord_id",
            player["discord_id"]
        ).execute()


# ================= READY =================


@bot.event
async def on_ready():

    try:

        synced = await bot.tree.sync()

        print(f"SYNCED {len(synced)} COMMANDS")

    except Exception as e:

        print(f"COMMAND SYNC ERROR: {e}")

    if not adm_loop.is_running():
        adm_loop.start()

    if not world_events.is_running():
        world_events.start()

    if not territory_income.is_running():
        territory_income.start()

    if not ai_radio.is_running():
        ai_radio.start()

    print(f"✅ Logged in as {bot.user}")


# ================= COMMANDS =================


@bot.tree.command(
    name="balance",
    description="View stats"
)
async def balance(interaction: discord.Interaction):

    await interaction.response.defer()

    await ensure_player(
        str(interaction.user.id),
        interaction.user.name
    )

    player = await get_player(
        str(interaction.user.id)
    )

    embed = discord.Embed(
        title="💰 Survivor Stats",
        description=(
            f"Pennies: {player['scrap']}\n"
            f"Level: {player['level']}\n"
            f"XP: {player['xp']}\n"
            f"Kills: {player['kills']}\n"
            f"Deaths: {player['deaths']}\n"
            f"Faction: {player['faction']}\n"
            f"Territory: {player['territory']}"
        ),
        color=0xFFD700
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )


# ================= DELIVERY SYSTEM =================

DELIVERY_FILE = "deliveries.json"


async def queue_delivery(player_name, item_name):

    import json

    delivery = {
        "player": player_name,
        "item": item_name,
        "time": str(datetime.now(UTC))
    }

    delivery_queue.append(delivery)

    try:

        with open(DELIVERY_FILE, "w") as f:
            json.dump(delivery_queue, f, indent=4)

    except Exception as e:

        print(f"DELIVERY WRITE ERROR: {e}")


# ================= SHOP COMMANDS =================


@bot.tree.command(
    name="shop",
    description="View the shop"
)
async def shop(interaction: discord.Interaction):

    desc = ""

    for item, price in SHOP_ITEMS.items():
        desc += f"{item} — ${price}\n
"

    embed = discord.Embed(
        title="🛒 Survivor Shop",
        description=desc,
        color=0x2ECC71
    )

    await interaction.response.send_message(
        embed=style_embed(embed)
    )


@bot.tree.command(
    name="buy",
    description="Buy an item"
)
@app_commands.describe(item="Item name")
async def buy(
    interaction: discord.Interaction,
    item: str
):

    item = item.lower()

    if item not in SHOP_ITEMS:

        await interaction.response.send_message(
            "❌ Item not found.",
            ephemeral=True
        )

        return

    await ensure_player(
        str(interaction.user.id),
        interaction.user.name
    )

    player = await get_player(
        str(interaction.user.id)
    )

    cost = SHOP_ITEMS[item]

    if player["scrap"] < cost:

        await interaction.response.send_message(
            "❌ Not enough scrap.",
            ephemeral=True
        )

        return

    inventory = player.get("inventory", [])

    inventory.append(item)

    supabase.table(
        "player_data"
    ).update({
        "scrap": player["scrap"] - cost,
        "inventory": inventory
    }).eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    await queue_delivery(
        interaction.user.name,
        item
    )

    embed = discord.Embed(
        title="📦 Purchase Successful",
        description=(
            f"Bought: {item}
"
            f"Cost: ${cost}
"
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
        inventory_text = "Empty"
    else:
        inventory_text = "
".join(inventory_items)

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
