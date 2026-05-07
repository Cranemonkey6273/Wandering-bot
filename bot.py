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

    ftp.prot_p()

    return ftp

def find_active_adm():

    global current_adm

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = ftp.nlst()

        adm_files = []

        for file in files:

            if file.endswith(".ADM"):

                adm_files.append(file)

                print(f"FOUND ADM: {file}")

        ftp.quit()

        if not adm_files:
            return None

        newest = sorted(adm_files)[-1]

        current_adm = f"{SEARCH_DIR}/{newest}"

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

    world_events.start()
    adm_loop.start()
    dynamic_economy.start()
    territory_income.start()
    ai_radio.start()

    print(f"✅ Logged in as {bot.user}")

# ================= ADM PARSER =================

async def parse_adm():

    global processed_lines

    BOT_IMAGE = "https://cdn.discordapp.com/embed/avatars/0.png"

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

    killfeed_channel = bot.get_channel(
        KILLFEED_CHANNEL_ID
    )

    raid_channel = bot.get_channel(
        RAID_CHANNEL_ID
    )

    build_channel = bot.get_channel(
        BUILD_CHANNEL_ID
    )

    deploy_channel = bot.get_channel(
        DEPLOY_CHANNEL_ID
    )

    connect_channel = bot.get_channel(
        CONNECT_CHANNEL_ID
    )

    parsed_kills = 0
    parsed_builds = 0
    parsed_raids = 0
    parsed_deploys = 0
    parsed_connections = 0

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

        # ================= CONNECTING =================

        if "is connecting" in lower:

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match:

                player_name = player_match.group(1)

                if connect_channel:

                    embed = discord.Embed(
                        description=(
                            f"🛰️ {player_name} is connecting\n"
                            f"🕒 {line[:8]}"
                        ),
                        color=0x9C8A00
                    )

                    embed.set_thumbnail(url=BOT_IMAGE)

                    embed.set_footer(
                        text="Wandering Bot Intelligence"
                    )

                    await connect_channel.send(embed=embed)

        # ================= CONNECTED =================

        elif "is connected" in lower:

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match:

                player_name = player_match.group(1)

                online_players.add(player_name)

                parsed_connections += 1

                if connect_channel:

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

                    await connect_channel.send(embed=embed)

        # ================= DISCONNECTED =================

        elif "has been disconnected" in lower:

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match:

                player_name = player_match.group(1)

                online_players.discard(player_name)

                if connect_channel:

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

                    await connect_channel.send(embed=embed)

        # ================= BUILD EVENTS =================

        if any(x in lower for x in [
            "built",
            "wall_base",
            "watchtower",
            "construction",
            "territory"
        ]):

            parsed_builds += 1

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            build_match = re.search(
                r'Built\s+([A-Za-z0-9_]+)',
                line,
                re.IGNORECASE
            )

            player_name = "Unknown"
            build_item = "Structure"

            if player_match:
                player_name = player_match.group(1)

            if build_match:
                build_item = build_match.group(1)

            embed = discord.Embed(
                description=(
                    f"🔨 {player_name} built {build_item}\n"
                    f"🕒 {line[:8]}"
                ),
                color=0x4E7F3D
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Intelligence"
            )

            if build_channel:

                await build_channel.send(embed=embed)

        # ================= DEPLOY EVENTS =================

        elif any(x in lower for x in [
            "placed",
            "deployed",
            "fencekit",
            "seachest"
        ]):

            parsed_deploys += 1

            embed = discord.Embed(
                description=(
                    f"📦 Deploy Event\n"
                    f"🕒 {line[:8]}"
                ),
                color=0x9C8A00
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Intelligence"
            )

            if deploy_channel:

                await deploy_channel.send(embed=embed)

        # ================= RAID EVENTS =================

        elif any(x in lower for x in [
            "destroyed",
            "breached",
            "raided",
            "explosive"
        ]):

            parsed_raids += 1

            embed = discord.Embed(
                description=(
                    f"💥 Raid Alert\n"
                    f"🕒 {line[:8]}"
                ),
                color=0x8E2E2E
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            embed.set_footer(
                text="Wandering Bot Intelligence"
            )

            if raid_channel:

                await raid_channel.send(embed=embed)

        # ================= KILL EVENTS =================

        elif (
            "killed by player" in lower
            or "hit by player" in lower
            or "killed" in lower
        ):

            victim_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            killer_match = re.search(
                r'killed by Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if not killer_match:

                killer_match = re.search(
                    r'by Player\s+"([^"]+)"',
                    line,
                    re.IGNORECASE
                )

            if victim_match and killer_match:

                victim = victim_match.group(1)
                killer = killer_match.group(1)

                parsed_kills += 1

                reward = random.randint(100, 500)

                embed = discord.Embed(
                    description=(
                        f"☠️ {killer} killed {victim}\n"
                        f"💰 Reward: {reward}\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x8E2E2E
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                if killfeed_channel:

                    await killfeed_channel.send(embed=embed)

    print("===== ADM SUMMARY =====")

    print(f"Kills Parsed: {parsed_kills}")
    print(f"Builds Parsed: {parsed_builds}")
    print(f"Deploys Parsed: {parsed_deploys}")
    print(f"Raids Parsed: {parsed_raids}")
    print(f"Connections Parsed: {parsed_connections}")

    print("=======================")

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
        "💥 Heavy fighting near NWAF.",
        "🏴 Faction conflict escalating.",
        "📦 Supply crate detected."
    ]

    embed = discord.Embed(
        title="📡 World Event",
        description=random.choice(events),
        color=0x9B59B6
    )

    await channel.send(
        embed=style_embed(embed)
    )

@tasks.loop(minutes=60)
async def dynamic_economy():

    for item in SHOP_ITEMS:

        SHOP_ITEMS[item] += random.randint(-5, 20)

        if SHOP_ITEMS[item] < 5:
            SHOP_ITEMS[item] = 5

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

    await channel.send(
        embed=style_embed(embed)
    )

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
            f"Bounty: {player['bounty']}\n"
            f"Vehicles: {player['vehicles']}\n"
            f"Faction: {player['faction']}\n"
            f"Territory: {player['territory']}"
        ),
        color=0xFFD700
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

bot.run(DISCORD_TOKEN)