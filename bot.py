import os
import re
import random
import asyncio
import logging
import discord
import berconpy

from flask import Flask
from threading import Thread

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks
from discord import app_commands
from supabase import create_client
from openai import AsyncOpenAI

# ================= LOGGING =================

logging.getLogger("discord").setLevel(logging.ERROR)

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

RCON_HOST = os.getenv(
    "RCON_HOST",
    "95.156.224.60"
)

RCON_PORT = int(
    os.getenv("RCON_PORT", 14503)
)

RCON_PASSWORD = os.getenv(
    "RCON_PASSWORD",
    "WanderingBot2026"
)

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
            <title>Wandering Bot</title>

            <style>

                body {
                    background-color: #0f0f0f;
                    color: #00ff88;
                    font-family: Arial;
                    text-align: center;
                    padding-top: 100px;
                }

                h1 {
                    font-size: 60px;
                }

                p {
                    font-size: 24px;
                }

            </style>

        </head>

        <body>

            <h1>Wandering Bot Online</h1>

            <p>DayZ Killfeed Active</p>

            <p>Server Systems Operational</p>

        </body>

    </html>
    """

def run_web():

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
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

processed_lines = set()
MAX_PROCESSED_LINES = 5000

current_adm = None
current_adm_size = 0

online_players = set()

last_line_count = 0
last_growth_time = datetime.now(UTC)

growth_fail_count = 0

dead_adms = set()

rcon_task = None

# ================= SWEAR TRACKER =================

SWEAR_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "cunt",
    "wanker",
    "bastard",
    "twat"
]

swear_tracker = {}

# ================= ECONOMY =================

SHOP_ITEMS = {
    "water": 10,
    "beans": 20,
    "ammo": 50,
    "medkit": 100,
    "armor": 300,
    "rifle": 600
}

# ================= FILTERS =================

IGNORE_PATTERNS = [
    "[CE]",
    "LootRespawner",
    "PRIDummy",
    "causing search overtime",
    "Ammo_40mm_Explosive",
    "ConstructionHelmet",
    "script",
    "crash",
    "weather",
    "storage",
    "economy",
    "infected"
]

# ================= BOT IMAGE =================

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

# ================= HELPERS =================

def should_ignore(line):

    lower = line.lower()

    for pattern in IGNORE_PATTERNS:

        if pattern.lower() in lower:
            return True

    return False


def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    return embed


def connect_ftp():

    ftp = FTP_TLS()

    ftp.connect(
        FTP_HOST,
        FTP_PORT,
        timeout=60
    )

    ftp.login(
        FTP_USER,
        FTP_PASS
    )

    ftp.prot_p()

    return ftp


# ================= RCON LOOP =================

async def rcon_loop():

    while True:

        try:

            print("CONNECTING TO RCON...")

            async with berconpy.ArmaClient().connect(
                RCON_HOST,
                RCON_PORT,
                RCON_PASSWORD
            ) as client:

                print("✅ RCON CONNECTED")

                while True:

                    players = await client.command(
                        "players"
                    )

                    print(
                        f"RCON PLAYERS:\n{players}"
                    )

                    await asyncio.sleep(30)

        except Exception as e:

            print(f"RCON ERROR: {e}")

            await asyncio.sleep(10)

# ================= LIVE ADM FINDER =================

def find_active_adm():

    global current_adm
    global current_adm_size
    global last_line_count
    global last_growth_time
    global growth_fail_count
    global dead_adms

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = []

        ftp.retrlines(
            "NLST",
            files.append
        )

        files = sorted(files)

        adm_files = []

        for file in files:

            if not file.endswith(".ADM"):
                continue

            full_path = f"{SEARCH_DIR}/{file}"

            if full_path in dead_adms:
                continue

            match = re.search(
                r"(\\d{4}-\\d{2}-\\d{2})_(\\d{2}-\\d{2}-\\d{2})",
                file
            )

            if not match:
                continue

            try:

                dt_str = (
                    match.group(1)
                    + " "
                    + match.group(2).replace("-", ":")
                )

                file_dt = datetime.strptime(
                    dt_str,
                    "%Y-%m-%d %H:%M:%S"
                )

                ftp.voidcmd("TYPE I")

                size = ftp.size(file)

                adm_files.append({
                    "name": file,
                    "datetime": file_dt,
                    "size": size
                })

            except Exception:
                pass

        if not adm_files:

            ftp.quit()
            return None

        adm_files.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        best_adm = adm_files[0]

        best_path = (
            f"{SEARCH_DIR}/{best_adm['name']}"
        )

        current_adm = best_path

        ftp.quit()

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return None

# ================= DOWNLOAD ADM =================

def download_adm():

    try:

        active_adm = find_active_adm()

        if not active_adm:
            return False

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        ftp.voidcmd("TYPE I")

        filename = os.path.basename(
            active_adm
        )

        if os.path.exists(LOCAL_LOG_FILE):
            os.remove(LOCAL_LOG_FILE)

        with open(
            LOCAL_LOG_FILE,
            "wb"
        ) as f:

            ftp.retrbinary(
                f"RETR {filename}",
                f.write,
                blocksize=1024
            )

        ftp.quit()

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False

# ================= READY =================

@bot.event
async def on_ready():

    global rcon_task

    try:

        await bot.tree.sync()

    except Exception as e:

        print(f"COMMAND SYNC ERROR: {e}")

    if not adm_loop.is_running():

        adm_loop.start()

    if rcon_task is None or rcon_task.done():

        rcon_task = asyncio.create_task(
            rcon_loop()
        )

    print(f"✅ Logged in as {bot.user}")

# ================= TASKS =================

@tasks.loop(seconds=30)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

    print(f"DOWNLOAD RESULT: {success}")

# ================= START =================

if not DISCORD_TOKEN:

    raise ValueError(
        "DISCORD_TOKEN missing"
    )

Thread(
    target=run_web,
    daemon=True
).start()

bot.run(
    DISCORD_TOKEN,
    reconnect=True
)