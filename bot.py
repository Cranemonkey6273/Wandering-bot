import os
import re
import asyncio
import random
import discord

from discord.ext import commands
from discord import app_commands
from datetime import datetime, UTC, timedelta
from supabase import create_client
from openai import AsyncOpenAI

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY
    )

# ================= MEMORY =================

conversation_memory = {}

# ================= SHOP =================

SHOP_ITEMS = {
    "water": 10,
    "beans": 15,
    "knife": 50,
    "ammo": 75,
    "medkit": 100,
    "armor": 250,
    "rifle": 500
}

BLACKMARKET_ITEMS = {
    "explosives": 1500,
    "nightvision": 2000,
    "rare_rifle": 3000
}

# ================= SYSTEM PROMPT =================

SYSTEM_PROMPT = """
You are Wandering Bot.

You are a hardcore DayZ AI.

Be immersive.
Be survival focused.
Be natural.
Keep responses fairly short.
"""

# ================= HELPERS =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    embed.set_footer(
        text="â£ï¸ Wandering Bot"
    )

    return embed

async def ensure_player(discord_id, username):

    existing = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if not existing.data:

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
            "last_daily": "",
            "last_work": ""
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

    new_total = player["scrap"] + amount

    supabase.table(
        "player_data"
    ).update({
        "scrap": new_total
    }).eq(
        "discord_id",
        discord_id
    ).execute()

async def remove_money(discord_id, amount):

    player = await get_player(discord_id)

    if not player:
        return False

    if player["scrap"] < amount:
        return False

    new_total = player["scrap"] - amount

    supabase.table(
        "player_data"
    ).update({
        "scrap": new_total
    }).eq(
        "discord_id",
        discord_id
    ).execute()

    return True

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

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

# ================= DAILY =================

@bot.tree.command(
    name="daily",
    description="Claim daily reward"
)
async def daily(interaction: discord.Interaction):

    await interaction.response.defer()

    await ensure_player(
        str(interaction.user.id),
        interaction.user.name
    )

    reward = random.randint(150, 400)

    await add_money(
        str(interaction.user.id),
        reward
    )

    embed = discord.Embed(
        title="ð Daily Reward",
        description=f"You earned {reward} pennies.",
        color=0x00FF00
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= WORK =================

@bot.tree.command(
    name="work",
    description="Work for money"
)
async def work(interaction: discord.Interaction):

    await interaction.response.defer()

    jobs = [
        "guarded a trader convoy",
        "cleared infected",
        "salvaged military loot",
        "protected survivors",
        "hunted wolves"
    ]

    reward = random.randint(50, 150)

    await add_money(
        str(interaction.user.id),
        reward
    )

    embed = discord.Embed(
        title="ð ï¸ Work Complete",
        description=(
            f"You {random.choice(jobs)}\n"
            f"+{reward} pennies"
        ),
        color=0x3498DB
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= ROB =================

@bot.tree.command(
    name="rob",
    description="Attempt robbery"
)
async def rob(interaction: discord.Interaction):

    await interaction.response.defer()

    success = random.randint(1, 100)

    if success <= 45:

        reward = random.randint(100, 500)

        await add_money(
            str(interaction.user.id),
            reward
        )

        text = f"ð° Robbery successful. +{reward} pennies"

    else:

        penalty = random.randint(50, 200)

        await remove_money(
            str(interaction.user.id),
            penalty
        )

        text = f"ð You got caught. -{penalty} pennies"

    embed = discord.Embed(
        title="ð« Robbery",
        description=text,
        color=0xE74C3C
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

# ================= BLACK MARKET =================

@bot.tree.command(
    name="blackmarket",
    description="View black market"
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

    success = await remove_money(
        str(interaction.user.id),
        price
    )

    if not success:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    supabase.table(
        "purchase_orders"
    ).insert({
        "discord_id": str(interaction.user.id),
        "username": interaction.user.name,
        "item": item,
        "price": price,
        "status": "pending"
    }).execute()

    embed = discord.Embed(
        title="â Purchase Complete",
        description=(
            f"Bought: {item}\n"
            f"Cost: {price} pennies"
        ),
        color=0x2ECC71
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= LEADERBOARD =================

@bot.tree.command(
    name="leaderboard",
    description="Top richest survivors"
)
async def leaderboard(interaction: discord.Interaction):

    await interaction.response.defer()

    results = supabase.table(
        "player_data"
    ).select("*").order(
        "scrap",
        desc=True
    ).limit(10).execute()

    text = ""

    for index, player in enumerate(results.data, start=1):

        text += (
            f"{index}. "
            f"{player['username']} â "
            f"{player['scrap']} pennies\n"
        )

    embed = discord.Embed(
        title="ð Richest Survivors",
        description=text,
        color=0xF1C40F
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= GIVE =================

@bot.tree.command(
    name="give",
    description="Give pennies"
)
@app_commands.describe(
    member="Member",
    amount="Amount"
)
async def give(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):

    await interaction.response.defer()

    if amount <= 0:

        await interaction.followup.send(
            "â Invalid amount."
        )

        return

    success = await remove_money(
        str(interaction.user.id),
        amount
    )

    if not success:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    await add_money(
        str(member.id),
        amount
    )

    embed = discord.Embed(
        title="ð¸ Transfer Complete",
        description=(
            f"{interaction.user.mention} sent "
            f"{amount} pennies to "
            f"{member.mention}"
        ),
        color=0x9B59B6
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= BANK DEPOSIT =================

@bot.tree.command(
    name="deposit",
    description="Deposit into bank"
)
@app_commands.describe(
    amount="Amount"
)
async def deposit(interaction: discord.Interaction, amount: int):

    await interaction.response.defer()

    player = await get_player(
        str(interaction.user.id)
    )

    if player["scrap"] < amount:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    supabase.table(
        "player_data"
    ).update({
        "scrap": player["scrap"] - amount,
        "bank": player["bank"] + amount
    }).eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    await interaction.followup.send(
        f"ð¦ Deposited {amount} pennies."
    )

# ================= WITHDRAW =================

@bot.tree.command(
    name="withdraw",
    description="Withdraw from bank"
)
@app_commands.describe(
    amount="Amount"
)
async def withdraw(interaction: discord.Interaction, amount: int):

    await interaction.response.defer()

    player = await get_player(
        str(interaction.user.id)
    )

    if player["bank"] < amount:

        await interaction.followup.send(
            "â Not enough bank funds."
        )

        return

    supabase.table(
        "player_data"
    ).update({
        "scrap": player["scrap"] + amount,
        "bank": player["bank"] - amount
    }).eq(
        "discord_id",
        str(interaction.user.id)
    ).execute()

    await interaction.followup.send(
        f"ð¦ Withdrew {amount} pennies."
    )

# ================= SLOT MACHINE =================

@bot.tree.command(
    name="slots",
    description="Play slots"
)
@app_commands.describe(
    bet="Bet amount"
)
async def slots(interaction: discord.Interaction, bet: int):

    await interaction.response.defer()

    success = await remove_money(
        str(interaction.user.id),
        bet
    )

    if not success:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    symbols = ["ð", "ð", "â¢ï¸", "ðª"]

    result = [
        random.choice(symbols),
        random.choice(symbols),
        random.choice(symbols)
    ]

    payout = 0

    if len(set(result)) == 1:
        payout = bet * 5

    elif result.count(result[0]) == 2:
        payout = bet * 2

    if payout > 0:

        await add_money(
            str(interaction.user.id),
            payout
        )

    embed = discord.Embed(
        title="ð° Slot Machine",
        description=(
            f"{' '.join(result)}\n\n"
            f"Payout: {payout}"
        ),
        color=0x1ABC9C
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
        description=f"You founded: {name}",
        color=0x95A5A6
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= PENDING ORDERS =================

@bot.tree.command(
    name="pendingorders",
    description="View pending orders"
)
async def pendingorders(interaction: discord.Interaction):

    await interaction.response.defer()

    results = supabase.table(
        "purchase_orders"
    ).select("*").eq(
        "status",
        "pending"
    ).execute()

    if not results.data:

        await interaction.followup.send(
            "No pending orders."
        )

        return

    text = ""

    for order in results.data:

        text += (
            f"#{order['id']} "
            f"{order['username']} â "
            f"{order['item']}\n"
        )

    embed = discord.Embed(
        title="ð¦ Pending Orders",
        description=text,
        color=0x95A5A6
    )

    await interaction.followup.send(
        embed=style_embed(embed)
    )

# ================= DELIVER =================

@bot.tree.command(
    name="deliver",
    description="Deliver order"
)
@app_commands.describe(
    order_id="Order ID"
)
async def deliver(interaction: discord.Interaction, order_id: int):

    await interaction.response.defer()

    supabase.table(
        "purchase_orders"
    ).update({
        "status": "delivered"
    }).eq(
        "id",
        order_id
    ).execute()

    await interaction.followup.send(
        f"â Order #{order_id} delivered."
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