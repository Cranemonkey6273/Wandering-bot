import os
import re
import random
import asyncio
import discord

from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, UTC
from supabase import create_client
from openai import AsyncOpenAI

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))

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

# ================= ECONOMY =================

SHOP_ITEMS = {
    "water": 10,
    "beans": 20,
    "ammo": 50,
    "medkit": 100,
    "armor": 300,
    "rifle": 600
}

BLACKMARKET_ITEMS = {
    "nightvision": 2000,
    "explosives": 3000,
    "rare_rifle": 5000
}

# ================= AI =================

SYSTEM_PROMPT = '''
You are Wandering Bot.
A hardcore DayZ survival AI.
Stay immersive and natural.
'''

# ================= GLOBALS =================

last_position = 0

# ================= HELPERS =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    embed.set_footer(
        text="â£ï¸ Wandering Bot"
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
            "bounty": 0,
            "faction": "",
            "territory": "",
            "vehicles": 0
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

async def add_money(discord_id, amount):

    player = await get_player(discord_id)

    if not player:
        return

    supabase.table(
        "player_data"
    ).update({
        "scrap": player["scrap"] + amount
    }).eq(
        "discord_id",
        discord_id
    ).execute()

# ================= REAL ADM PARSER =================

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

    for line in lines:

        line = line.strip()

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
                    title="ð PvP Kill Detected",
                    description=(
                        f"ð« Killer: {killer}\n"
                        f"â ï¸ Victim: {victim}\n"
                        f"ðª Reward: {reward}"
                    ),
                    color=0xC0392B
                )

                if killfeed_channel:

                    await killfeed_channel.send(
                        embed=style_embed(embed)
                    )

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    world_events.start()

    adm_loop.start()

    print(f"â Logged in as {bot.user}")

# ================= ADM LOOP =================

@tasks.loop(seconds=30)
async def adm_loop():

    await parse_adm()

# ================= BALANCE =================

@bot.tree.command(
    name="balance",
    description="View survivor stats"
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
        title="ðª Survivor Balance",
        description=(
            f"Pennies: {player['scrap']}\n"
            f"Bank: {player['bank']}\n"
            f"Kills: {player['kills']}\n"
            f"Deaths: {player['deaths']}\n"
            f"Bounty: {player['bounty']}\n"
            f"Faction: {player['faction']}\n"
            f"Territory: {player['territory']}\n"
            f"Vehicles: {player['vehicles']}"
        ),
        color=0xFFD700
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= SHOP =================

@bot.tree.command(
    name="shop",
    description="View trader shop"
)
async def shop(interaction: discord.Interaction):

    await interaction.response.defer()

    text = ""

    for item, price in SHOP_ITEMS.items():

        text += f"â¢ {item} â {price} pennies\n"

    embed = discord.Embed(
        title="ð Trader Shop",
        description=text,
        color=0xE67E22
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= BUY =================

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

    if item in SHOP_ITEMS:
        price = SHOP_ITEMS[item]

    elif item in BLACKMARKET_ITEMS:
        price = BLACKMARKET_ITEMS[item]

    else:

        await interaction.followup.send(
            "â Item not found."
        )

        return

    player = await get_player(
        str(interaction.user.id)
    )

    if player["scrap"] < price:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    supabase.table(
        "player_data"
    ).update({
        "scrap": player["scrap"] - price
    }).eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    supabase.table(
        "delivery_queue"
    ).insert({
        "discord_id": str(interaction.user.id),
        "username": interaction.user.name,
        "item": item,
        "status": "queued"
    }).execute()

    embed = discord.Embed(
        title="ð¦ Delivery Queued",
        description=f"{item} queued for delivery.",
        color=0x2ECC71
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= INVENTORY =================

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
            "ð¦ Inventory empty."
        )

        return

    text = ""

    for item in results.data:

        text += (
            f"â¢ {item['item']} "
            f"({item['status']})\n"
        )

    embed = discord.Embed(
        title="ð Inventory",
        description=text,
        color=0x3498DB
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= VEHICLES =================

@bot.tree.command(
    name="buyvehicle",
    description="Buy vehicle"
)
@app_commands.describe(
    vehicle="Vehicle name"
)
async def buyvehicle(
    interaction: discord.Interaction,
    vehicle: str
):

    await interaction.response.defer()

    cost = 5000

    player = await get_player(
        str(interaction.user.id)
    )

    if player["scrap"] < cost:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    supabase.table(
        "player_data"
    ).update({
        "scrap": player["scrap"] - cost,
        "vehicles": player["vehicles"] + 1
    }).eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    embed = discord.Embed(
        title="ð Vehicle Purchased",
        description=f"Purchased: {vehicle}",
        color=0x1ABC9C
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= BOUNTIES =================

@bot.tree.command(
    name="setbounty",
    description="Place bounty"
)
@app_commands.describe(
    member="Target player",
    amount="Bounty amount"
)
async def setbounty(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):

    await interaction.response.defer()

    target = await get_player(
        str(member.id)
    )

    if not target:

        await interaction.followup.send(
            "â Player not found."
        )

        return

    supabase.table(
        "player_data"
    ).update({
        "bounty": target["bounty"] + amount
    }).eq(
        "discord_id",
        str(member.id)
    ).execute()

    await interaction.followup.send(
        f"ð¯ Bounty placed on {member.mention}"
    )

# ================= AIRDROP =================

@bot.tree.command(
    name="airdrop",
    description="Trigger airdrop"
)
async def airdrop(interaction: discord.Interaction):

    await interaction.response.defer()

    locations = [
        "NWAF",
        "Tisy",
        "Cherno",
        "Vybor",
        "Severograd"
    ]

    location = random.choice(locations)

    embed = discord.Embed(
        title="âï¸ AIRDROP DETECTED",
        description=f"Military airdrop near {location}",
        color=0x3498DB
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= WORLD EVENTS =================

@tasks.loop(minutes=20)
async def world_events():

    channel = bot.get_channel(EVENT_CHANNEL_ID)

    if not channel:
        return

    events = [
        "â£ï¸ Toxic gas spreading near Tisy.",
        "ð Helicopter crash reported near Vybor.",
        "ð¥ Heavy gunfire heard near NWAF.",
        "ð» Trader convoy entering Chernarus.",
        "ðª Military airdrop spotted.",
        "ð´ Faction war escalating near Cherno."
    ]

    embed = discord.Embed(
        title="ð Dynamic World Event",
        description=random.choice(events),
        color=0x9B59B6
    )

    await channel.send(
        embed=style_embed(embed)
    )

# ================= AI CHAT =================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if bot.user in message.mentions:

        async with message.channel.typing():

            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": message.content
                    }
                ],
                max_tokens=200
            )

            reply = response.choices[0].message.content

            await message.reply(
                reply,
                mention_author=False
            )

# ================= START =================

bot.run(DISCORD_TOKEN)