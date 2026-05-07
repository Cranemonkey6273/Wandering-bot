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

# ================= FEED CHANNELS =================

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

# ================= FILE SETTINGS =================

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

# ================= AI MEMORY =================

conversation_memory = {}

MAX_MEMORY = 15

AI_CHANNELS = []

AI_COOLDOWN = {}

# ================= SUPABASE =================

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= SHOP ITEMS =================

SHOP_ITEMS = {
    "ak74": {
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
    "☣️ Pennies tax applied for foul language.",
    "💀 The wasteland heard that.",
    "🪙 Swear jar updated, survivor.",
    "📻 Easy on the radio chatter.",
    "☢️ Another swear detected. Pennies confiscated."
]

# ================= POSITION TRACKING =================

def load_last_position():

    if os.path.exists(POSITION_FILE):

        with open(POSITION_FILE, "r") as f:
            return int(f.read())

    return 0


def save_last_position(position):

    with open(POSITION_FILE, "w") as f:
        f.write(str(position))

# ================= GLOBAL TRACKING =================

last_size = load_last_position()

current_log_file = None

# ================= ONLINE PLAYER TRACKING =================

online_players = set()

# ================= AI SYSTEM PROMPT =================

SYSTEM_PROMPT = """
You are Wandering Bot.

You are a conversational AI for a hardcore DayZ Discord server.

Personality:
- casual
- immersive
- intelligent
- slightly sarcastic sometimes
- survival-focused
- natural sounding

Behavior:
- keep responses short unless needed
- adapt slightly to user slang/tone
- avoid repetitive responses
- speak naturally like a real survivor

You can:
- discuss DayZ
- answer server questions
- joke with players
- maintain conversations naturally

Never:
- spam
- write huge essays constantly
- pretend to be human
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

        print(f"❌ PLAYER CREATE ERROR: {e}")

# ================= SWEAR CHECK =================

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
                    f"🪙 -{penalty} Pennies\n"
                    f"🗣️ Word detected: `{swear}`"
                )

                break

    except Exception as e:

        print(f"❌ SWEAR JAR ERROR: {e}")

# ================= DATE EXTRACTION =================

def extract_date(file_name):

    match = re.search(
        r'(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})',
        file_name
    )

    if not match:
        return datetime.min

    return datetime.strptime(
        f"{match.group(1)} "
        f"{match.group(2)}:"
        f"{match.group(3)}:"
        f"{match.group(4)}",
        "%Y-%m-%d %H:%M:%S"
    )

# ================= FTP CONNECTION =================

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

# ================= FIND NEWEST ADM =================

def find_latest_adm():

    try:

        print(f"🔍 FTP Searching: {LOG_DIRECTORY}")

        ftp = connect_ftp()

        ftp.cwd(LOG_DIRECTORY)

        files = ftp.nlst()

        adm_files = []

        for file in files:

            if file.endswith(".ADM"):

                adm_files.append(file)

        ftp.quit()

        if not adm_files:
            return None

        newest_file = max(
            adm_files,
            key=lambda x: extract_date(x)
        )

        return f"{LOG_DIRECTORY}/{newest_file}"

    except Exception as e:

        print("❌ FTP SEARCH ERROR:", e)

        return None

# ================= DOWNLOAD LOG =================

def download_latest_log():

    global current_log_file
    global last_size

    try:

        log_path = find_latest_adm()

        if not log_path:
            return False

        if current_log_file != log_path:

            current_log_file = log_path

            last_size = 0

            save_last_position(0)

        ftp = connect_ftp()

        with open(LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {log_path}",
                f.write
            )

        ftp.quit()

        return True

    except Exception as e:

        print("❌ DOWNLOAD ERROR:", e)

        return False

# ================= EMBED STYLE =================

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    embed.set_footer(
        text="☣️ Wandering Bot Intelligence"
    )

    return embed

# ================= SEND EMBED =================

async def send_embed(channel, embed):

    if not channel:
        return

    try:

        await channel.send(embed=embed)

    except Exception as e:

        print(f"❌ SEND EMBED ERROR: {e}")

# ================= PARSE LOG =================

async def parse_new_lines():

    global last_size

    try:

        if not os.path.exists(LOG_FILE):
            return

        with open(
            LOG_FILE,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            f.seek(last_size)

            new_lines = f.readlines()

            last_size = f.tell()

            save_last_position(last_size)

        for line in new_lines:

            line = line.strip()

            if not line:
                continue

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            if " is connected" in line:

                online_players.add(player)

            elif " has been disconnected" in line:

                online_players.discard(player)

    except Exception as e:

        print("❌ PARSE ERROR:", e)

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

        conversation_memory[user_id] = memory

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

        return "The radio signal got lost somewhere in Chernarus."

# ================= BALANCE =================

@bot.tree.command(
    name="balance",
    description="Check your pennies balance"
)
async def balance(interaction: discord.Interaction):

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
            f"🤬 Total Swears: {data['total_swears']}\n"
            f"📻 Favorite Swear: {data['favorite_swear']}"
        ),
        color=0xFFD700
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= SHOP =================

@bot.tree.command(
    name="shop",
    description="View the trader shop"
)
async def shop(interaction: discord.Interaction):

    shop_text = ""

    for item_id, item in SHOP_ITEMS.items():

        shop_text += (
            f"• {item['name']} — "
            f"{item['price']} Pennies\n"
        )

    embed = discord.Embed(
        title="🛒 Wandering Trader",
        description=shop_text,
        color=0xFFD700
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= BUY =================

@bot.tree.command(
    name="buy",
    description="Buy an item from the shop"
)
@app_commands.describe(item="Item ID from the shop")
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

    item_data = SHOP_ITEMS[item]

    if data["scrap"] < item_data["price"]:

        await interaction.response.send_message(
            "❌ Not enough Pennies.",
            ephemeral=True
        )

        return

    new_balance = data["scrap"] - item_data["price"]

    supabase.table("player_data").update({
        "scrap": new_balance
    }).eq(
        "discord_id",
        discord_id
    ).execute()

    embed = discord.Embed(
        title="✅ Purchase Successful",
        description=(
            f"You bought:\n"
            f"🎒 {item_data['name']}\n\n"
            f"🪙 Remaining Pennies: {new_balance}"
        ),
        color=0x00FF00
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= DAILY =================

@bot.tree.command(
    name="daily",
    description="Claim your daily pennies"
)
async def daily(interaction: discord.Interaction):

    discord_id = str(interaction.user.id)

    await ensure_player_exists(
        discord_id,
        interaction.user.name
    )

    reward = random.randint(50, 150)

    player = supabase.table(
        "player_data"
    ).select("*").eq(
        "discord_id",
        discord_id
    ).execute()

    data = player.data[0]

    new_balance = data["scrap"] + reward

    supabase.table("player_data").update({
        "scrap": new_balance
    }).eq(
        "discord_id",
        discord_id
    ).execute()

    embed = discord.Embed(
        title="🎁 Daily Reward",
        description=(
            f"You found supplies in the wasteland.\n\n"
            f"🪙 +{reward} Pennies\n"
            f"💰 Balance: {new_balance}"
        ),
        color=0x00FF00
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= COINFLIP =================

@bot.tree.command(
    name="coinflip",
    description="Gamble your pennies"
)
@app_commands.describe(amount="Amount to gamble")
async def coinflip(
    interaction: discord.Interaction,
    amount: int
):

    if amount <= 0:

        await interaction.response.send_message(
            "❌ Invalid amount.",
            ephemeral=True
        )

        return

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

    if data["scrap"] < amount:

        await interaction.response.send_message(
            "❌ Not enough Pennies.",
            ephemeral=True
        )

        return

    win = random.choice([True, False])

    if win:

        new_balance = data["scrap"] + amount

        result = (
            f"🟢 You WON!\n"
            f"🪙 +{amount} Pennies"
        )

    else:

        new_balance = data["scrap"] - amount

        result = (
            f"🔴 You LOST!\n"
            f"🪙 -{amount} Pennies"
        )

    supabase.table("player_data").update({
        "scrap": new_balance
    }).eq(
        "discord_id",
        discord_id
    ).execute()

    embed = discord.Embed(
        title="🪙 Coinflip",
        description=(
            f"{result}\n\n"
            f"💰 Balance: {new_balance}"
        ),
        color=0xFFD700
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= SWEAR LEADERBOARD =================

@bot.tree.command(
    name="swearleaderboard",
    description="Show top swearers"
)
async def swearleaderboard(interaction: discord.Interaction):

    results = supabase.table(
        "player_data"
    ).select("*").order(
        "total_swears",
        desc=True
    ).limit(10).execute()

    leaderboard = ""

    for index, player in enumerate(results.data, start=1):

        leaderboard += (
            f"{index}. "
            f"{player['username']} — "
            f"{player['total_swears']} swears "
            f"({player['favorite_swear']})\n"
        )

    embed = discord.Embed(
        title="🤬 Swear Leaderboard",
        description=leaderboard,
        color=0x8B0000
    )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= AI CHAT SYSTEM =================

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

            await asyncio.sleep(
                random.uniform(1.0, 2.5)
            )

            response = await generate_ai_response(
                user_id,
                message.author.name,
                message.content
            )

        if len(response) > 1900:
            response = response[:1900]

        await message.reply(
            response,
            mention_author=False
        )

    except Exception as e:

        print(f"❌ AI CHAT ERROR: {e}")

# ================= LOOP =================

async def tracker_loop():

    await bot.wait_until_ready()

    while not bot.is_closed():

        success = download_latest_log()

        if success:

            await parse_new_lines()

        await asyncio.sleep(30)

# ================= EVENTS =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(f"✅ Logged in as {bot.user}")

    bot.loop.create_task(tracker_loop())

# ================= START =================

bot.run(DISCORD_TOKEN)