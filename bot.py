import os
import re
import random
import asyncio
import discord

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

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))

LOG_FILE = "server.ADM"

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

last_position = 0
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

# ================= HELPERS =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    embed.set_footer(
        text="Wandering Bot"
    )

    return embed

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

    print(f"â Logged in as {bot.user}")

# ================= ADM PARSER =================

async def parse_adm():

    global last_position

    if not os.path.exists(LOG_FILE):
        return

    with open(
        LOG_FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        f.seek(last_position)

        lines = f.readlines()

        last_position = f.tell()

    killfeed_channel = bot.get_channel(
        KILLFEED_CHANNEL_ID
    )

    raid_channel = bot.get_channel(
        RAID_CHANNEL_ID
    )

    for line in lines:

        line = line.strip()

        if "is connected" in line:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            if player_match:
                online_players.add(
                    player_match.group(1)
                )

        if "has been disconnected" in line:

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            if player_match:
                online_players.discard(
                    player_match.group(1)
                )

        if "killed by Player" in line:

            victim_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            killer_match = re.search(
                r'killed by Player "([^"]+)"',
                line
            )

            if victim_match and killer_match:

                victim = victim_match.group(1)
                killer = killer_match.group(1)

                reward = random.randint(100, 500)

                embed = discord.Embed(
                    title="â ï¸ PvP Kill",
                    description=(
                        f"Killer: {killer}\n"
                        f"Victim: {victim}\n"
                        f"Reward: {reward}"
                    ),
                    color=0xC0392B
                )

                if killfeed_channel:
                    await killfeed_channel.send(
                        embed=style_embed(embed)
                    )

        if (
            "destroyed" in line.lower()
            or "breached" in line.lower()
            or "explosive" in line.lower()
        ):

            embed = discord.Embed(
                title="ð´ RAID ALERT",
                description="Raid activity detected.",
                color=0xE74C3C
            )

            if raid_channel:
                await raid_channel.send(
                    embed=style_embed(embed)
                )

# ================= TASKS =================

@tasks.loop(seconds=30)
async def adm_loop():

    await parse_adm()

@tasks.loop(minutes=20)
async def world_events():

    channel = bot.get_channel(EVENT_CHANNEL_ID)

    if not channel:
        return

    events = [
        "ð Helicopter crash reported.",
        "â£ï¸ Toxic gas spreading.",
        "ð» Convoy entering Chernarus.",
        "ð¥ Heavy fighting near NWAF.",
        "ð´ Faction conflict escalating.",
        "ð¦ Supply crate detected."
    ]

    embed = discord.Embed(
        title="ð¡ World Event",
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
        "ð» Gunfire heard near Tisy.",
        "ð» Survivors spotted near Vybor.",
        "ð» Trader convoy requesting escort.",
        "ð» Black market trader active tonight.",
        "ð» Toxic storm approaching."
    ]

    embed = discord.Embed(
        title="ð» Radio Chatter",
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
        title="ð° Survivor Stats",
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

@bot.tree.command(
    name="shop",
    description="View shop"
)
async def shop(interaction: discord.Interaction):

    await interaction.response.defer()

    text = ""

    for item, price in SHOP_ITEMS.items():

        text += f"â¢ {item} â {price}\n"

    embed = discord.Embed(
        title="ð¦ Trader Shop",
        description=text,
        color=0xE67E22
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

@bot.tree.command(
    name="buy",
    description="Buy item"
)
@app_commands.describe(
    item="Item name"
)
async def buy(interaction: discord.Interaction, item: str):

    await interaction.response.defer()

    item = item.lower()

    if item not in SHOP_ITEMS:

        await interaction.followup.send(
            "â Item not found."
        )

        return

    player = await get_player(
        str(interaction.user.id)
    )

    if player["scrap"] < SHOP_ITEMS[item]:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    supabase.table(
        "delivery_queue"
    ).insert({
        "discord_id": str(interaction.user.id),
        "username": interaction.user.name,
        "item": item,
        "status": "queued"
    }).execute()

    embed = discord.Embed(
        title="â Order Created",
        description=f"{item} queued for delivery.",
        color=0x2ECC71
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

@bot.tree.command(
    name="inventory",
    description="View inventory"
)
async def inventory(interaction: discord.Interaction):

    await interaction.response.defer()

    results = supabase.table(
        "delivery_queue"
    ).select("*").eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    if not results.data:

        await interaction.followup.send(
            "Inventory empty."
        )

        return

    text = ""

    for item in results.data:

        text += (
            f"â¢ {item['item']} "
            f"({item['status']})\n"
        )

    embed = discord.Embed(
        title="ð Inventory",
        description=text,
        color=0x3498DB
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

@bot.tree.command(
    name="online",
    description="Online players"
)
async def online(interaction: discord.Interaction):

    await interaction.response.defer()

    if not online_players:

        await interaction.followup.send(
            "No online players tracked."
        )

        return

    players = "\n".join(online_players)

    embed = discord.Embed(
        title="ð¡ Online Survivors",
        description=players,
        color=0x2ECC71
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= START =================

bot.run(DISCORD_TOKEN)