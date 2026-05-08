import os
import re
import random
import asyncio
import discord
import berconpy

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

# ================= PLAYER DATABASE =================

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

# ================= LIVE RCON PARSER =================

async def process_line(line):

    if not line:
        return

    if should_ignore(line):
        return

    lower = line.lower()

    killfeed_channel = bot.get_channel(KILLFEED_CHANNEL_ID)
    raid_channel = bot.get_channel(RAID_CHANNEL_ID)
    build_channel = bot.get_channel(BUILD_CHANNEL_ID)
    deploy_channel = bot.get_channel(DEPLOY_CHANNEL_ID)
    connect_channel = bot.get_channel(CONNECT_CHANNEL_ID)

    print(f"RCON EVENT: {line}")

    # ================= CONNECTING =================

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
                    f"🛰️ {player_name} connecting"
                ),
                color=0x9C8A00
            )

            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Intelligence")

            await connect_channel.send(embed=embed)

    # ================= CONNECTED =================

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
                    f"☣️ {player_name} connected"
                ),
                color=0x4E7F3D
            )

            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Intelligence")

            await connect_channel.send(embed=embed)

    # ================= DISCONNECTED =================

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
                    f"❌ {player_name} disconnected"
                ),
                color=0x8E2E2E
            )

            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Intelligence")

            await connect_channel.send(embed=embed)

    # ================= BUILD =================

    elif any(x in lower for x in [
        "built",
        "wall_base",
        "watchtower",
        "territory",
        "fence",
        "gate"
    ]):

        if build_channel:

            embed = discord.Embed(
                description=(
                    f"🔨 Build Event\n\n{line[:3500]}"
                ),
                color=0x2ECC71
            )

            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Intelligence")

            await build_channel.send(embed=embed)

    # ================= DEPLOY =================

    elif any(x in lower for x in [
        "placed",
        "deployed",
        "seachest",
        "barrel"
    ]):

        if deploy_channel:

            embed = discord.Embed(
                description=(
                    f"📦 Deploy Event\n\n{line[:3500]}"
                ),
                color=0xF1C40F
            )

            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Intelligence")

            await deploy_channel.send(embed=embed)

    # ================= RAID =================

    elif any(x in lower for x in [
        "destroyed",
        "breached",
        "explosive",
        "raid"
    ]):

        if raid_channel:

            embed = discord.Embed(
                description=(
                    f"💥 Raid Alert\n\n{line[:3500]}"
                ),
                color=0xE74C3C
            )

            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Intelligence")

            await raid_channel.send(embed=embed)

    # ================= KILLS =================

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

            embed.set_thumbnail(url=BOT_IMAGE)
            embed.set_footer(text="Wandering Bot Intelligence")

            await killfeed_channel.send(embed=embed)

# ================= RCON LISTENER =================

async def rcon_loop():

    while True:

        try:

            print("CONNECTING TO RCON...")

            client = berconpy.Client()

            await client.connect(
                RCON_HOST,
                RCON_PORT,
                RCON_PASSWORD
            )

            print("RCON CONNECTED")

            while True:

                packets = await client.wait_for_packets()

                for packet in packets:

                    message = str(packet)

                    await process_line(message)

        except Exception as e:

            print(f"RCON ERROR: {e}")

            await asyncio.sleep(10)

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    if not world_events.is_running():
        world_events.start()

    if not dynamic_economy.is_running():
        dynamic_economy.start()

    if not territory_income.is_running():
        territory_income.start()

    if not ai_radio.is_running():
        ai_radio.start()

    bot.loop.create_task(
        rcon_loop()
    )

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

# ================= WORLD EVENTS =================

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

# ================= ECONOMY =================

@tasks.loop(minutes=60)
async def dynamic_economy():

    for item in SHOP_ITEMS:

        SHOP_ITEMS[item] += random.randint(-5, 20)

        if SHOP_ITEMS[item] < 5:
            SHOP_ITEMS[item] = 5

# ================= TERRITORY =================

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

# ================= AI RADIO =================

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

# ================= BALANCE =================

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

# ================= SWEARS =================

@bot.tree.command(
    name="swears",
    description="View your swear count"
)
async def swears(interaction: discord.Interaction):

    user_id = str(interaction.user.id)

    count = swear_tracker.get(
        user_id,
        {}
    ).get(
        "count",
        0
    )

    embed = discord.Embed(
        title="🤬 Swear Counter",
        description=f"You have sworn {count} times.",
        color=0xE74C3C
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await interaction.response.send_message(embed=embed)

# ================= SWEAR LB =================

@bot.tree.command(
    name="swearlb",
    description="Swear leaderboard"
)
async def swearlb(interaction: discord.Interaction):

    sorted_users = sorted(
        swear_tracker.items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )

    desc = ""

    for i, (_, data) in enumerate(
        sorted_users[:10],
        start=1
    ):

        desc += (
            f"{i}. "
            f"{data['name']} — "
            f"{data['count']} swears\n"
        )

    if not desc:
        desc = "No swears tracked yet."

    embed = discord.Embed(
        title="🏆 Swear Leaderboard",
        description=desc,
        color=0xF39C12
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await interaction.response.send_message(embed=embed)

# ================= START =================

bot.run(DISCORD_TOKEN)
