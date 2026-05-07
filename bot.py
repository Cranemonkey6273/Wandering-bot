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

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

CONNECTION_CHANNEL_ID = int(os.getenv("CONNECTION_CHANNEL_ID", 0))
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

# ================= AI =================

conversation_memory = {}
MAX_MEMORY = 15
AI_CHANNELS = []
AI_COOLDOWN = {}

SYSTEM_PROMPT = """
You are Wandering Bot.

You are a conversational AI for a hardcore DayZ Discord server.

Be immersive, casual, funny, survival-focused, and natural.
Keep replies short unless needed.
"""

# ================= SHOP =================

SHOP_ITEMS = {
    "ak": {
        "name": "AK-74",
        "price": 500
    },
    "medkit": {
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
    "☣️ Pennies tax applied.",
    "💀 The wasteland heard that.",
    "🪙 Swear jar updated.",
    "📻 Easy on the radio chatter.",
]

# ================= TRACKING =================

online_players = set()

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

# ================= EMBEDS =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    embed.set_footer(
        text="☣️ Wandering Bot Intelligence"
    )

    return embed

# ================= PLAYER DATA =================

async def ensure_player_exists(
    discord_id,
    username
):

    try:

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
                "scrap": 100,
                "total_swears": 0,
                "favorite_swear": "",
                "favorite_swear_count": 0
            }).execute()

    except Exception as e:

        print(f"❌ PLAYER ERROR: {e}")

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

                new_balance = max(
                    0,
                    data["scrap"] - penalty
                )

                total_swears = data["total_swears"] + 1

                favorite_word = swear
                favorite_count = 1

                if data["favorite_swear"] == swear:

                    favorite_count = (
                        data["favorite_swear_count"] + 1
                    )

                supabase.table(
                    "player_data"
                ).update({
                    "scrap": new_balance,
                    "total_swears": total_swears,
                    "favorite_swear": favorite_word,
                    "favorite_swear_count": favorite_count
                }).eq(
                    "discord_id",
                    str(message.author.id)
                ).execute()

                msg = random.choice(
                    FUNNY_SWEAR_MESSAGES
                )

                await message.channel.send(
                    f"{msg}\n"
                    f"🪙 -{penalty} Pennies"
                )

                break

    except Exception as e:

        print(f"❌ SWEAR ERROR: {e}")

# ================= AI RESPONSE =================

async def generate_ai_response(
    user_id,
    username,
    message_content
):

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

        print(f"❌ OPENAI ERROR: {e}")

        return "📻 Static on the frequency..."

# ================= BALANCE =================

@bot.tree.command(
    name="balance",
    description="Check your Pennies"
)
async def balance(interaction: discord.Interaction):

    await interaction.response.defer()

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
        title="🪙 Pennies Balance",
        description=(
            f"🪙 Pennies: {data['scrap']}\n"
            f"🤬 Total Swears: {data['total_swears']}"
        ),
        color=0xFFD700
    )

    embed = style_embed(embed)

    await interaction.followup.send(
        embed=embed
    )

# ================= SHOP =================

@bot.tree.command(
    name="shop",
    description="View the trader"
)
async def shop(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🛒 Wandering Trader",
        description=(
            "🔫 AK-74 — 500\n"
            "🩹 Medical Kit — 150\n"
            "🥫 Food Bundle — 75\n"
            "🎒 Tactical Backpack — 300\n"
            "☢️ Gas Mask — 250"
        ),
        color=0xFFD700
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= BUY =================

@bot.tree.command(
    name="buy",
    description="Buy an item"
)
@app_commands.describe(
    item="Item ID"
)
async def buy(
    interaction: discord.Interaction,
    item: str
):

    await interaction.response.defer()

    item = item.lower()

    if item not in SHOP_ITEMS:

        await interaction.followup.send(
            "❌ Item not found."
        )

        return

    shop_item = SHOP_ITEMS[item]

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

    if data["scrap"] < shop_item["price"]:

        await interaction.followup.send(
            "❌ Not enough Pennies."
        )

        return

    new_balance = (
        data["scrap"] - shop_item["price"]
    )

    supabase.table(
        "player_data"
    ).update({
        "scrap": new_balance
    }).eq(
        "discord_id",
        discord_id
    ).execute()

    supabase.table(
        "purchase_orders"
    ).insert({
        "discord_id": discord_id,
        "username": interaction.user.name,
        "item_name": shop_item["name"],
        "item_price": shop_item["price"]
    }).execute()

    embed = discord.Embed(
        title="✅ Purchase Successful",
        description=(
            f"Bought: {shop_item['name']}\n"
            f"🪙 Balance: {new_balance}"
        ),
        color=0x00FF00
    )

    embed = style_embed(embed)

    await interaction.followup.send(
        embed=embed
    )

# ================= GIVE COINS =================

@bot.tree.command(
    name="givecoins",
    description="Give Pennies"
)
@app_commands.describe(
    member="Player",
    amount="Amount"
)
async def givecoins(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):

    await interaction.response.defer()

    if interaction.channel.id != ADMIN_CHANNEL_ID:

        await interaction.followup.send(
            "❌ Admin only."
        )

        return

    discord_id = str(member.id)

    await ensure_player_exists(
        discord_id,
        member.name
    )

    player = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    data = player.data[0]

    new_balance = data["scrap"] + amount

    supabase.table(
        "player_data"
    ).update({
        "scrap": new_balance
    }).eq(
        "discord_id",
        discord_id
    ).execute()

    await interaction.followup.send(
        f"✅ Added 🪙 {amount} to {member.mention}"
    )

# ================= PAY =================

@bot.tree.command(
    name="pay",
    description="Pay another player"
)
@app_commands.describe(
    member="Player",
    amount="Amount"
)
async def pay(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):

    await interaction.response.defer()

    sender_id = str(interaction.user.id)
    receiver_id = str(member.id)

    await ensure_player_exists(
        sender_id,
        interaction.user.name
    )

    await ensure_player_exists(
        receiver_id,
        member.name
    )

    sender = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        sender_id
    ).execute()

    receiver = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        receiver_id
    ).execute()

    sender_data = sender.data[0]
    receiver_data = receiver.data[0]

    if sender_data["scrap"] < amount:

        await interaction.followup.send(
            "❌ Not enough Pennies."
        )

        return

    supabase.table(
        "player_data"
    ).update({
        "scrap": sender_data["scrap"] - amount
    }).eq(
        "discord_id",
        sender_id
    ).execute()

    supabase.table(
        "player_data"
    ).update({
        "scrap": receiver_data["scrap"] + amount
    }).eq(
        "discord_id",
        receiver_id
    ).execute()

    await interaction.followup.send(
        f"💸 Paid 🪙 {amount} to {member.mention}"
    )

# ================= PENDING ORDERS =================

@bot.tree.command(
    name="pendingorders",
    description="View pending orders"
)
async def pendingorders(interaction: discord.Interaction):

    if interaction.channel.id != ADMIN_CHANNEL_ID:

        await interaction.response.send_message(
            "❌ Admin only."
        )

        return

    orders = supabase.table(
        "purchase_orders"
    ).select("*").eq(
        "delivered",
        False
    ).execute()

    if not orders.data:

        await interaction.response.send_message(
            "✅ No pending orders."
        )

        return

    desc = ""

    for order in orders.data:

        desc += (
            f"🆔 {order['id']} | "
            f"{order['username']} | "
            f"{order['item_name']}\n"
        )

    embed = discord.Embed(
        title="📦 Pending Orders",
        description=desc,
        color=0xFFA500
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= DELIVER =================

@bot.tree.command(
    name="deliver",
    description="Mark delivered"
)
@app_commands.describe(
    order_id="Order ID"
)
async def deliver(
    interaction: discord.Interaction,
    order_id: int
):

    if interaction.channel.id != ADMIN_CHANNEL_ID:

        await interaction.response.send_message(
            "❌ Admin only."
        )

        return

    supabase.table(
        "purchase_orders"
    ).update({
        "delivered": True
    }).eq(
        "id",
        order_id
    ).execute()

    await interaction.response.send_message(
        f"✅ Order #{order_id} delivered."
    )

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

    elif message.content.lower().startswith(
        "wandering"
    ):
        should_reply = True

    if not should_reply:
        return

    user_id = str(message.author.id)

    now = asyncio.get_event_loop().time()

    if user_id in AI_COOLDOWN:

        if now - AI_COOLDOWN[user_id] < 8:
            return

    AI_COOLDOWN[user_id] = now

    async with message.channel.typing():

        await asyncio.sleep(
            random.uniform(1.0, 2.0)
        )

        response = await generate_ai_response(
            user_id,
            message.author.name,
            message.content
        )

    await message.reply(
        response,
        mention_author=False
    )

# ================= FTP =================

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

def find_latest_adm():

    try:

        ftp = connect_ftp()

        ftp.cwd(LOG_DIRECTORY)

        files = ftp.nlst()

        adm_files = [
            f for f in files
            if f.endswith(".ADM")
        ]

        ftp.quit()

        if not adm_files:
            return None

        return (
            f"{LOG_DIRECTORY}/"
            f"{sorted(adm_files)[-1]}"
        )

    except Exception as e:

        print(f"❌ FTP ERROR: {e}")

        return None

async def tracker_loop():

    await bot.wait_until_ready()

    while not bot.is_closed():

        try:

            find_latest_adm()

        except Exception as e:

            print(f"❌ TRACKER ERROR: {e}")

        await asyncio.sleep(30)

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(f"✅ Logged in as {bot.user}")

    bot.loop.create_task(
        tracker_loop()
    )

# ================= START =================

bot.run(DISCORD_TOKEN)