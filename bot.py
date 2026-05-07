import os
import re
import asyncio
import random
import discord

from discord.ext import commands
from ftplib import FTP_TLS
from datetime import datetime, UTC
from supabase import create_client
from openai import AsyncOpenAI

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CONNECTION_CHANNEL_ID = int(os.getenv("CONNECTION_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
DEPLOY_CHANNEL_ID = int(os.getenv("DEPLOY_CHANNEL_ID", 0))
PACKING_CHANNEL_ID = int(os.getenv("PACKING_CHANNEL_ID", 0))
DAMAGE_CHANNEL_ID = int(os.getenv("DAMAGE_CHANNEL_ID", 0))

ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID", 0))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

LOG_FILE = "server.ADM"
POSITION_FILE = "last_position.txt"
LOG_DIRECTORY = "/dayzxb/config"

BOT_IMAGE = "wanderingbot.png"

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

# ================= MEMORY =================

conversation_memory = {}
MAX_MEMORY = 15
AI_CHANNELS = []
AI_COOLDOWN = {}

# ================= SUPABASE =================

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= SWEAR SYSTEM =================

SWEAR_WORDS = {
    "fuck": 2,
    "shit": 1,
    "bitch": 2,
    "cunt": 5,
    "bastard": 2,
    "wanker": 2,
    "twat": 2,
    "prick": 2
}

FUNNY_SWEAR_MESSAGES = [
    "â£ï¸ Pennies tax applied for foul language.",
    "ð The wasteland heard that.",
    "ðª Swear jar updated, survivor.",
    "ð» Easy on the radio chatter.",
    "â¢ï¸ Another swear detected. Pennies confiscated."
]

# ================= SHOP =================

SHOP_ITEMS = {
    "ak74": {
        "name": "AK-74",
        "price": 500
    },
    "medical": {
        "name": "Medical Kit",
        "price": 150
    },
    "food": {
        "name": "Food Bundle",
        "price": 75
    },
    "backpack": {
        "name": "Tactical Backpack",
        "price": 300
    },
    "gasmask": {
        "name": "Gas Mask",
        "price": 250
    }
}

# ================= POSITION TRACKING =================

def load_last_position():

    if os.path.exists(POSITION_FILE):

        with open(POSITION_FILE, "r") as f:
            return int(f.read())

    return 0


def save_last_position(position):

    with open(POSITION_FILE, "w") as f:
        f.write(str(position))


last_size = load_last_position()
current_log_file = None
online_players = set()

# ================= AI PROMPT =================

SYSTEM_PROMPT = """
You are Wandering Bot.

You are a conversational AI for a hardcore DayZ Discord server.

Keep replies natural, immersive, short, and survival themed.
"""

# ================= PLAYER DATA =================

async def ensure_player_exists(discord_id, username):

    try:

        existing = supabase.table("player_data").select("*").eq(
            "discord_id",
            discord_id
        ).execute()

        if not existing.data:

            supabase.table("player_data").insert({
                "discord_id": discord_id,
                "username": username,
                "scrap": 100,
                "total_swears": 0,
                "favorite_swear": "",
                "favorite_swear_count": 0
            }).execute()

    except Exception as e:

        print(f"â PLAYER CREATE ERROR: {e}")

# ================= EMBED STYLE =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    embed.set_footer(
        text="â£ï¸ Wandering Bot Intelligence"
    )

    if os.path.exists(BOT_IMAGE):
        file = discord.File(BOT_IMAGE, filename="wanderingbot.png")
        embed.set_thumbnail(url="attachment://wanderingbot.png")
        return embed, file

    return embed, None

# ================= AI RESPONSE =================

async def generate_ai_response(user_id, username, message_content):

    try:

        if user_id not in conversation_memory:
            conversation_memory[user_id] = []

        memory = conversation_memory[user_id]

        memory.append({
            "role": "user",
            "content": f"{username}: {message_content}"
        })

        memory = memory[-MAX_MEMORY:]

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        messages.extend(memory)

        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.8,
            max_tokens=250
        )

        ai_reply = response.choices[0].message.content

        memory.append({
            "role": "assistant",
            "content": ai_reply
        })

        conversation_memory[user_id] = memory[-MAX_MEMORY:]

        return ai_reply

    except Exception as e:

        print(f"â OPENAI ERROR: {e}")

        return "ð» Radio interference detected."

# ================= SWEAR JAR =================

async def process_swear_jar(message):

    try:

        content = message.content.lower()

        for swear, penalty in SWEAR_WORDS.items():

            if swear in content:

                await ensure_player_exists(
                    str(message.author.id),
                    message.author.name
                )

                player = supabase.table(
                    "player_data"
                ).select("*").eq(
                    "discord_id",
                    str(message.author.id)
                ).execute()

                if not player.data:
                    return

                data = player.data[0]

                new_scrap = max(
                    0,
                    data["scrap"] - penalty
                )

                total_swears = data["total_swears"] + 1

                favorite_word = data["favorite_swear"]
                favorite_count = data["favorite_swear_count"]

                if favorite_word == swear:
                    favorite_count += 1

                else:
                    favorite_word = swear
                    favorite_count = 1

                supabase.table("player_data").update({
                    "scrap": new_scrap,
                    "total_swears": total_swears,
                    "favorite_swear": favorite_word,
                    "favorite_swear_count": favorite_count
                }).eq(
                    "discord_id",
                    str(message.author.id)
                ).execute()

                funny_message = random.choice(
                    FUNNY_SWEAR_MESSAGES
                )

                await message.channel.send(
                    f"{funny_message}\n"
                    f"ðª -{penalty} Pennies"
                )

                break

    except Exception as e:

        print(f"â SWEAR JAR ERROR: {e}")

# ================= BALANCE =================

@bot.tree.command(
    name="balance",
    description="Check your pennies"
)
async def balance(interaction: discord.Interaction):

    try:

        discord_id = str(interaction.user.id)

        await ensure_player_exists(
            discord_id,
            interaction.user.name
        )

        player = supabase.table(
            "player_data"
        ).select("*").eq(
            "discord_id",
            discord_id
        ).execute()

        data = player.data[0]

        embed = discord.Embed(
            title="ðª Pennies Balance",
            description=(
                f"ðª Pennies: {data['scrap']}\n"
                f"ð¤¬ Total Swears: {data['total_swears']}\n"
                f"ð» Favorite Swear: {data['favorite_swear']}"
            ),
            color=0xFFD700
        )

        embed, file = style_embed(embed)

        if file:
            await interaction.response.send_message(
                embed=embed,
                file=file
            )
        else:
            await interaction.response.send_message(
                embed=embed
            )

    except Exception as e:

        print(f"â BALANCE ERROR: {e}")

# ================= SHOP =================

@bot.tree.command(
    name="shop",
    description="View the trader shop"
)
async def shop(interaction: discord.Interaction):

    try:

        description = ""

        for item_id, item in SHOP_ITEMS.items():

            description += (
                f"ð¹ {item['name']} â "
                f"{item['price']} Pennies\n"
            )

        embed = discord.Embed(
            title="ð Wandering Trader",
            description=description,
            color=0xFFD700
        )

        embed, file = style_embed(embed)

        if file:
            await interaction.response.send_message(
                embed=embed,
                file=file
            )
        else:
            await interaction.response.send_message(
                embed=embed
            )

    except Exception as e:

        print(f"â SHOP ERROR: {e}")

# ================= BUY =================

@bot.tree.command(
    name="buy",
    description="Buy an item"
)
async def buy(
    interaction: discord.Interaction,
    item: str
):

    try:

        item = item.lower()

        if item not in SHOP_ITEMS:

            await interaction.response.send_message(
                "â Item not found.",
                ephemeral=True
            )

            return

        await ensure_player_exists(
            str(interaction.user.id),
            interaction.user.name
        )

        player = supabase.table(
            "player_data"
        ).select("*").eq(
            "discord_id",
            str(interaction.user.id)
        ).execute()

        data = player.data[0]

        price = SHOP_ITEMS[item]["price"]

        if data["scrap"] < price:

            await interaction.response.send_message(
                "â Not enough Pennies.",
                ephemeral=True
            )

            return

        new_balance = data["scrap"] - price

        supabase.table("player_data").update({
            "scrap": new_balance
        }).eq(
            "discord_id",
            str(interaction.user.id)
        ).execute()

        supabase.table("purchase_orders").insert({
            "discord_id": str(interaction.user.id),
            "username": interaction.user.name,
            "item_name": SHOP_ITEMS[item]["name"],
            "item_price": price,
            "delivered": False
        }).execute()

        embed = discord.Embed(
            title="â Purchase Successful",
            description=(
                f"Bought: {SHOP_ITEMS[item]['name']}\n"
                f"ðª Balance: {new_balance}"
            ),
            color=0x00FF00
        )

        embed, file = style_embed(embed)

        if file:
            await interaction.response.send_message(
                embed=embed,
                file=file
            )
        else:
            await interaction.response.send_message(
                embed=embed
            )

    except Exception as e:

        print(f"â BUY ERROR: {e}")

# ================= PENDING ORDERS =================

@bot.tree.command(
    name="pendingorders",
    description="View pending orders"
)
async def pendingorders(interaction: discord.Interaction):

    await interaction.response.defer()

    try:

        if interaction.channel.id != ADMIN_CHANNEL_ID:

            await interaction.followup.send(
                "â Admin only.",
                ephemeral=True
            )

            return

        results = supabase.table(
            "purchase_orders"
        ).select("*").eq(
            "delivered",
            False
        ).execute()

        if not results.data:

            await interaction.followup.send(
                "â No pending orders."
            )

            return

        description = ""

        for order in results.data:

            description += (
                f"ð {order['id']} | "
                f"{order['username']} | "
                f"{order['item_name']}\n"
            )

        embed = discord.Embed(
            title="ð¦ Pending Orders",
            description=description,
            color=0xFFA500
        )

        embed, file = style_embed(embed)

        if file:
            await interaction.followup.send(
                embed=embed,
                file=file
            )
        else:
            await interaction.followup.send(
                embed=embed
            )

    except Exception as e:

        print(f"â PENDING ORDERS ERROR: {e}")

# ================= GIVE COINS =================

@bot.tree.command(
    name="givecoins",
    description="Admin give pennies"
)
async def givecoins(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):

    try:

        if interaction.channel.id != ADMIN_CHANNEL_ID:

            await interaction.response.send_message(
                "â Admin only.",
                ephemeral=True
            )

            return

        await ensure_player_exists(
            str(member.id),
            member.name
        )

        player = supabase.table(
            "player_data"
        ).select("*").eq(
            "discord_id",
            str(member.id)
        ).execute()

        data = player.data[0]

        new_balance = data["scrap"] + amount

        supabase.table("player_data").update({
            "scrap": new_balance
        }).eq(
            "discord_id",
            str(member.id)
        ).execute()

        await interaction.response.send_message(
            f"â Added ðª {amount} to {member.mention}"
        )

    except Exception as e:

        print(f"â GIVECOINS ERROR: {e}")

# ================= AI CHAT =================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    await process_swear_jar(message)

    await bot.process_commands(message)

    should_reply = False

    if bot.user in message.mentions:
        should_reply = True

    elif message.content.lower().startswith("wandering"):
        should_reply = True

    elif message.channel.id in AI_CHANNELS:

        chance = random.randint(1, 100)

        if chance <= 15:
            should_reply = True

    if not should_reply:
        return

    user_id = str(message.author.id)

    now = asyncio.get_event_loop().time()

    if user_id in AI_COOLDOWN:

        if now - AI_COOLDOWN[user_id] < 8:
            return

    AI_COOLDOWN[user_id] = now

    try:

        async with message.channel.typing():

            response = await generate_ai_response(
                user_id,
                message.author.name,
                message.content
            )

        await message.reply(
            response,
            mention_author=False
        )

    except Exception as e:

        print(f"â AI CHAT ERROR: {e}")

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(f"â Logged in as {bot.user}")

# ================= START =================

bot.run(DISCORD_TOKEN)