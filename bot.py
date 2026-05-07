import os
import re
import asyncio
import random
import discord

from discord.ext import commands
from discord import app_commands
from ftplib import FTP_TLS
from datetime import datetime, UTC
from supabase import create_client
from openai import AsyncOpenAI

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

ADMIN_ROLE = "Admin"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

conversation_memory = {}

SHOP_ITEMS = {
    "water": 10,
    "beans": 15,
    "ammo": 50,
    "medkit": 75,
    "rifle": 300,
    "armor": 500
}

SYSTEM_PROMPT = """
You are Wandering Bot.
A survival AI for a hardcore DayZ server.
"""

def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    embed.set_footer(text="â£ï¸ Wandering Bot")
    return embed

async def ensure_player_exists(discord_id, username):

    existing = supabase.table("player_data").select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if not existing.data:

        supabase.table("player_data").insert({
            "discord_id": discord_id,
            "username": username,
            "scrap": 100,
            "bank": 0,
            "kills": 0,
            "deaths": 0,
            "daily_used": False
        }).execute()

async def add_money(discord_id, amount):

    player = supabase.table("player_data").select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if not player.data:
        return

    current = player.data[0]["scrap"]

    supabase.table("player_data").update({
        "scrap": current + amount
    }).eq(
        "discord_id",
        discord_id
    ).execute()

async def remove_money(discord_id, amount):

    player = supabase.table("player_data").select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    if not player.data:
        return False

    current = player.data[0]["scrap"]

    if current < amount:
        return False

    supabase.table("player_data").update({
        "scrap": current - amount
    }).eq(
        "discord_id",
        discord_id
    ).execute()

    return True

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(f"â Logged in as {bot.user}")

@bot.tree.command(name="balance", description="Check balance")
async def balance(interaction: discord.Interaction):

    await interaction.response.defer()

    discord_id = str(interaction.user.id)

    await ensure_player_exists(
        discord_id,
        interaction.user.name
    )

    player = supabase.table("player_data").select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    data = player.data[0]

    embed = discord.Embed(
        title="ðª Balance",
        description=(
            f"Pennies: {data['scrap']}\n"
            f"Bank: {data['bank']}\n"
            f"Kills: {data['kills']}\n"
            f"Deaths: {data['deaths']}"
        ),
        color=0xFFD700
    )

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="daily", description="Claim daily reward")
async def daily(interaction: discord.Interaction):

    await interaction.response.defer()

    reward = random.randint(50, 150)

    await ensure_player_exists(
        str(interaction.user.id),
        interaction.user.name
    )

    await add_money(str(interaction.user.id), reward)

    embed = discord.Embed(
        title="ð Daily Reward",
        description=f"You received {reward} pennies.",
        color=0x00FF00
    )

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="work", description="Work for pennies")
async def work(interaction: discord.Interaction):

    await interaction.response.defer()

    reward = random.randint(10, 60)

    await add_money(str(interaction.user.id), reward)

    jobs = [
        "guarded a military convoy",
        "cleaned infected blood",
        "salvaged a crashed heli",
        "worked for a trader"
    ]

    embed = discord.Embed(
        title="ð ï¸ Work Complete",
        description=(
            f"You {random.choice(jobs)}\n"
            f"Earned {reward} pennies."
        ),
        color=0x3498DB
    )

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="shop", description="Open trader shop")
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

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="buy", description="Buy an item")
@app_commands.describe(item="Item name")
async def buy(interaction: discord.Interaction, item: str):

    await interaction.response.defer()

    item = item.lower()

    if item not in SHOP_ITEMS:

        await interaction.followup.send(
            "â Item not found."
        )

        return

    price = SHOP_ITEMS[item]

    success = await remove_money(
        str(interaction.user.id),
        price
    )

    if not success:

        await interaction.followup.send(
            "â Not enough pennies."
        )

        return

    supabase.table("purchase_orders").insert({
        "discord_id": str(interaction.user.id),
        "username": interaction.user.name,
        "item": item,
        "price": price,
        "status": "pending"
    }).execute()

    embed = discord.Embed(
        title="â Purchase Complete",
        description=(
            f"You bought: {item}\n"
            f"Cost: {price} pennies"
        ),
        color=0x2ECC71
    )

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="leaderboard", description="Top richest players")
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

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="givecoins", description="Give coins")
@app_commands.describe(member="Member", amount="Amount")
async def givecoins(
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

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="pendingorders", description="View pending orders")
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
            f"{order['username']} â "
            f"{order['item']}\n"
        )

    embed = discord.Embed(
        title="ð¦ Pending Orders",
        description=text,
        color=0x95A5A6
    )

    await interaction.followup.send(embed=style_embed(embed))

@bot.tree.command(name="deliver", description="Deliver item")
@app_commands.describe(order_id="Order ID")
async def deliver(interaction: discord.Interaction, order_id: int):

    await interaction.response.defer()

    supabase.table("purchase_orders").update({
        "status": "delivered"
    }).eq(
        "id",
        order_id
    ).execute()

    await interaction.followup.send(
        f"â Order #{order_id} marked delivered."
    )

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
                max_tokens=150
            )

            reply = response.choices[0].message.content

            await message.reply(
                reply,
                mention_author=False
            )

bot.run(DISCORD_TOKEN)