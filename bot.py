import os
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

# ================= SHOPS =================

SHOP_ITEMS = {
    "water": 10,
    "beans": 15,
    "ammo": 50,
    "medkit": 100,
    "armor": 250,
    "rifle": 500
}

BLACKMARKET_ITEMS = {
    "nightvision": 2000,
    "explosives": 3000,
    "rare_rifle": 5000
}

# ================= AI =================

SYSTEM_PROMPT = '''
You are Wandering Bot.
You are a DayZ survival AI.
Speak naturally.
Keep responses immersive.
'''

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
            "scrap": 500,
            "bank": 0,
            "kills": 0,
            "deaths": 0,
            "faction": "",
            "territory": ""
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

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    random_world_events.start()

    print(f"â Logged in as {bot.user}")

# ================= BALANCE =================

@bot.tree.command(
    name="balance",
    description="Check balance"
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
            f"Faction: {player['faction']}"
        ),
        color=0xFFD700
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= SHOP =================

@bot.tree.command(
    name="shop",
    description="Trader shop"
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

# ================= BLACK MARKET =================

@bot.tree.command(
    name="blackmarket",
    description="Black market"
)
async def blackmarket(interaction: discord.Interaction):

    await interaction.response.defer()

    text = ""

    for item, price in BLACKMARKET_ITEMS.items():

        text += f"â ï¸ {item} â {price} pennies\n"

    embed = discord.Embed(
        title="â ï¸ Black Market",
        description=text,
        color=0x8E44AD
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

    # AUTO DELIVERY QUEUE

    supabase.table(
        "delivery_queue"
    ).insert({
        "discord_id": str(interaction.user.id),
        "username": interaction.user.name,
        "item": item,
        "status": "queued"
    }).execute()

    embed = discord.Embed(
        title="ð¦ Order Queued",
        description=(
            f"Item: {item}\n"
            f"Delivery status: queued"
        ),
        color=0x2ECC71
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= FACTIONS =================

@bot.tree.command(
    name="createfaction",
    description="Create faction"
)
@app_commands.describe(
    name="Faction name"
)
async def createfaction(interaction: discord.Interaction, name: str):

    await interaction.response.defer()

    supabase.table(
        "player_data"
    ).update({
        "faction": name
    }).eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    embed = discord.Embed(
        title="ð¡ï¸ Faction Created",
        description=f"You founded {name}",
        color=0x95A5A6
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= TERRITORY =================

@bot.tree.command(
    name="claimterritory",
    description="Claim territory"
)
@app_commands.describe(
    territory="Territory name"
)
async def claimterritory(
    interaction: discord.Interaction,
    territory: str
):

    await interaction.response.defer()

    supabase.table(
        "player_data"
    ).update({
        "territory": territory
    }).eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    embed = discord.Embed(
        title="ð´ Territory Claimed",
        description=f"Claimed territory: {territory}",
        color=0xE74C3C
    )

    await interaction.followup.send(
        embed=style_embed(embed)
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
        "Guglovo"
    ]

    location = random.choice(locations)

    embed = discord.Embed(
        title="âï¸ AIRDROP INCOMING",
        description=(
            f"Military supply drop detected near {location}."
        ),
        color=0x3498DB
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= RANDOM WORLD EVENTS =================

@tasks.loop(minutes=30)
async def random_world_events():

    channel = bot.get_channel(EVENT_CHANNEL_ID)

    if not channel:
        return

    events = [
        "â£ï¸ Toxic gas spreading near Tisy.",
        "ð Helicopter crash reported.",
        "ð» Trader convoy entering Chernarus.",
        "ð¥ Heavy gunfire heard near NWAF.",
        "ðª Military airdrop inbound."
    ]

    embed = discord.Embed(
        title="ð World Event",
        description=random.choice(events),
        color=0x9B59B6
    )

    await channel.send(
        embed=style_embed(embed)
    )

# ================= KILL REWARD SYSTEM =================

@bot.tree.command(
    name="simulatekill",
    description="Simulate kill reward"
)
@app_commands.describe(
    member="Killed player"
)
async def simulatekill(
    interaction: discord.Interaction,
    member: discord.Member
):

    await interaction.response.defer()

    reward = random.randint(100, 300)

    await add_money(
        str(interaction.user.id),
        reward
    )

    embed = discord.Embed(
        title="ð Kill Reward",
        description=(
            f"You eliminated {member.mention}\n"
            f"+{reward} pennies"
        ),
        color=0xC0392B
    )

    await interaction.followup.send(
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