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

# PRIVATE ADMIN CHANNEL
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

# ENABLE MESSAGE CONTENT INTENT
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

                print(f"📄 Found ADM: {file}")

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

            print("❌ No ADM logs found")

            return False

        print(f"✅ Latest ADM log found: {log_path}")

        if current_log_file != log_path:

            print(f"🆕 New ADM detected: {log_path}")

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

    if os.path.exists(BOT_IMAGE):

        embed.set_thumbnail(
            url="attachment://wanderingbot.png"
        )

    return embed

# ================= SEND EMBED =================

async def send_embed(channel, embed):

    if not channel:

        print("❌ Channel not found")

        return

    try:

        if os.path.exists(BOT_IMAGE):

            file = discord.File(
                BOT_IMAGE,
                filename="wanderingbot.png"
            )

            await channel.send(
                embed=embed,
                file=file
            )

        else:

            await channel.send(embed=embed)

    except Exception as e:

        print(f"❌ SEND EMBED ERROR: {e}")

# ================= PARSE LOG =================

async def parse_new_lines():

    global last_size

    connection_channel = bot.get_channel(CONNECTION_CHANNEL_ID)

    admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)

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

            timestamp_match = re.match(
                r'(\d{2}:\d{2}:\d{2})',
                line
            )

            timestamp = (
                timestamp_match.group(1)
                if timestamp_match
                else "Unknown"
            )

            player_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            player = (
                player_match.group(1)
                if player_match
                else "Unknown"
            )

            pos_match = re.search(
                r'pos=<([\d.]+), ([\d.]+), ([\d.]+)>',
                line
            )

            location_display = "`Unknown`"

            if pos_match:

                x = round(float(pos_match.group(1)), 1)
                y = round(float(pos_match.group(2)), 1)

                location_display = f"`{x}, {y}`"

            # ================= PLAYER CONNECTING =================

            if " is connecting" in line:

                embed = discord.Embed(
                    color=0x8B8000
                )

                embed.description = (
                    f"📡 {player} is connecting\n"
                    f"🕒 {timestamp}"
                )

                embed = style_embed(embed)

                await send_embed(
                    connection_channel,
                    embed
                )

            # ================= PLAYER CONNECTED =================

            elif " is connected" in line:

                online_players.add(player)

                embed = discord.Embed(
                    color=0x556B2F
                )

                embed.description = (
                    f"☣ {player} connected\n"
                    f"🕒 {timestamp}"
                )

                embed = style_embed(embed)

                await send_embed(
                    connection_channel,
                    embed
                )

            # ================= PLAYER DISCONNECTED =================

            elif " has been disconnected" in line:

                online_players.discard(player)

                embed = discord.Embed(
                    color=0x8B2E2E
                )

                embed.description = (
                    f"☠ {player} disconnected\n"
                    f"📍 {location_display}\n"
                    f"🕒 {timestamp}"
                )

                embed = style_embed(embed)

                await send_embed(
                    admin_channel,
                    embed
                )

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
            model="gpt-4.1-mini",
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

# ================= SLASH COMMANDS =================

@bot.tree.command(
    name="online",
    description="Show online survivors"
)
async def online(
    interaction: discord.Interaction
):

    if not online_players:

        embed = discord.Embed(
            title="☣️ Online Survivors",
            description="No survivors currently online.",
            color=0x8B0000
        )

    else:

        player_list = "\n".join(
            [f"• {p}" for p in sorted(online_players)]
        )

        embed = discord.Embed(
            title="☣️ Online Survivors",
            description=player_list,
            color=0x556B2F
        )

    embed = style_embed(embed)

    await interaction.response.send_message(
        embed=embed
    )

# ================= PLAYER COUNT =================

@bot.tree.command(
    name="playercount",
    description="Show current online player count"
)
async def playercount(interaction: discord.Interaction):

    embed = discord.Embed(
        title="👥 Current Survivor Count",
        description=f"{len(online_players)} survivors online",
        color=0x3498db
    )

    embed = style_embed(embed)

    await interaction.response.send_message(embed=embed)

# ================= PING =================

@bot.tree.command(
    name="ping",
    description="Check bot latency"
)
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    embed = discord.Embed(
        title="🏓 Pong",
        description=f"Latency: {latency}ms",
        color=0x00ff00
    )

    embed = style_embed(embed)

    await interaction.response.send_message(embed=embed)

# ================= SERVER STATUS =================

@bot.tree.command(
    name="serverstatus",
    description="Check server tracker status"
)
async def serverstatus(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🖥️ Wandering Server Status",
        description=(
            "✅ FTP Connected\n"
            "✅ ADM Tracking Active\n"
            "✅ Slash Commands Online\n"
            "✅ AI Conversations Online\n"
            "✅ Log Monitoring Active"
        ),
        color=0x2ecc71
    )

    embed = style_embed(embed)

    await interaction.response.send_message(embed=embed)

# ================= HELP =================

@bot.tree.command(
    name="help",
    description="Show all commands"
)
async def helpcommand(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🤖 Wandering Bot Commands",
        description=(
            "/online\n"
            "/playercount\n"
            "/ping\n"
            "/serverstatus\n"
            "/shop\n"
            "/rules\n"
            "/restart\n"
            "/discord\n"
            "/map\n"
            "/help\n\n"
            "Mention the bot or start with 'wandering' to chat."
        ),
        color=0x9b59b6
    )

    embed = style_embed(embed)

    await interaction.response.send_message(embed=embed)

# ================= AI CHAT SYSTEM =================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    await bot.process_commands(message)

    should_reply = False

    # BOT MENTION
    if bot.user in message.mentions:
        should_reply = True

    # STARTS WITH wandering
    elif message.content.lower().startswith("wandering"):
        should_reply = True

    # RANDOM CHAT IN AI CHANNELS
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

    print("🚀 Wandering Bot Tracker Started")

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

    print("🌐 Slash commands synced")

    bot.loop.create_task(tracker_loop())

# ================= START =================

bot.run(DISCORD_TOKEN)