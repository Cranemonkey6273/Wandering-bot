import os
import re
import asyncio
import logging
import discord
import berconpy

from flask import Flask
from threading import Thread
from ftplib import FTP_TLS
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord import Embed
from supabase import create_client
from openai import AsyncOpenAI

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

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

# ================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"
LOCAL_LOG_FILE = "live.ADM"

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

# ================= WEBSITE =================

app = Flask(__name__)

@app.route("/")
def home():
    return """
    <html>
    <head>
    <title>Wandering Bot Omega</title>
    </head>
    <body style="background:#111;color:#00ff88;font-family:Arial;text-align:center;padding-top:100px;">
    <h1>Wandering Bot Omega Online</h1>
    <p>Killfeed Active</p>
    <p>ADM Tracking Operational</p>
    </body>
    </html>
    """

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ================= OPENAI =================

client_ai = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ================= SUPABASE =================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 5000

current_adm = None
current_adm_size = 0

last_position = 0
growth_fail_count = 0

MIN_ADM_SIZE = 500
MAX_FAILS_BEFORE_SWITCH = 8

online_players = set()

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

# ================= FILTERS =================

IGNORE_PATTERNS = [
    "[CE]",
    "LootRespawner",
    "PRIDummy",
    "script",
    "weather",
    "economy"
]

# ================= HELPERS =================

def should_ignore(line):
    lower = line.lower()
    for pattern in IGNORE_PATTERNS:
        if pattern.lower() in lower:
            return True
    return False


def style_embed(embed):
    embed.timestamp = datetime.now(timezone.utc)
    embed.set_thumbnail(url=BOT_IMAGE)
    return embed


def connect_ftp():
    ftp = FTP_TLS()
    ftp.connect(FTP_HOST, FTP_PORT, timeout=60)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.prot_p()
    return ftp

# ================= RCON =================

async def rcon_loop():
    while True:
        try:
            print("CONNECTING TO RCON...")

            async with berconpy.ArmaClient().connect(
                RCON_HOST,
                RCON_PORT,
                RCON_PASSWORD
            ) as client:

                print("RCON CONNECTED")

                while True:
                    try:
                        players = await client.command("players")
                        print(players)
                    except Exception as e:
                        print(f"RCON COMMAND ERROR: {e}")

                    await asyncio.sleep(30)

        except Exception as e:
            print(f"RCON ERROR: {e}")
            await asyncio.sleep(15)

# ================= ADM FINDER =================

def find_active_adm():
    global current_adm, current_adm_size, growth_fail_count

    try:
        ftp = connect_ftp()
        ftp.cwd(SEARCH_DIR)

        files = []
        ftp.retrlines("NLST", files.append)

        adm_files = []

        for file in files:
            if not file.endswith(".ADM"):
                continue

            match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})", file)

            if not match:
                continue

            dt_str = match.group(1) + " " + match.group(2).replace("-", ":")

            file_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

            ftp.voidcmd("TYPE I")
            size = ftp.size(file)

            adm_files.append({
                "name": file,
                "path": f"{SEARCH_DIR}/{file}",
                "datetime": file_dt,
                "size": size
            })

        ftp.quit()

        if not adm_files:
            return None

        adm_files.sort(key=lambda x: x["datetime"], reverse=True)
        newest = adm_files[0]

        current_adm = newest["path"]
        current_adm_size = newest["size"]

        return current_adm

    except Exception as e:
        print(f"ADM FINDER ERROR: {e}")
        return current_adm

# ================= DOWNLOAD =================

def download_adm():
    try:
        active_adm = find_active_adm()
        if not active_adm:
            return False

        ftp = connect_ftp()
        ftp.cwd(SEARCH_DIR)

        filename = os.path.basename(active_adm)

        with open(LOCAL_LOG_FILE, "wb") as f:
            ftp.retrbinary(f"RETR {filename}", f.write)

        ftp.quit()

        print(f"ADM DOWNLOADED: {filename}")
        return True

    except Exception as e:
        print(f"DOWNLOAD ERROR: {e}")
        return False

# ================= PARSER =================

def reset_parser_state():
    global last_position, processed_lines
    last_position = 0
    processed_lines.clear()

# ================= DISCORD SEND =================

async def send_embed(channel_id, embed):
    try:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
    except Exception as e:
        print(f"DISCORD SEND ERROR: {e}")

# ================= ADM LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():
    try:
        success = await asyncio.to_thread(download_adm)
        if success:
            print("ADM UPDATED")
    except Exception as e:
        print(f"ADM LOOP ERROR: {e}")

# ================= READY =================

@bot.event
async def on_ready():
    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()

    asyncio.create_task(rcon_loop())

# ================= START =================

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN missing")

Thread(target=run_web, daemon=True).start()

bot.run(DISCORD_TOKEN, reconnect=True)