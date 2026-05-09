import os
import re
import asyncio
import logging
import discord
import berconpy

from flask import Flask
from threading import Thread
from ftplib import FTP_TLS
from datetime import datetime, UTC
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

SEARCH_PATHS = [
    ".",
    "config",
    "profiles",
    "logs"
]

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

    app.run(
        host="0.0.0.0",
        port=port
    )

# ================= OPENAI =================

client_ai = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ================= SUPABASE =================

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ================= GLOBALS =================

processed_lines = set()
MAX_PROCESSED_LINES = 5000

current_adm = None
last_position = 0

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

    embed.timestamp = datetime.now(UTC)
    embed.set_thumbnail(url=BOT_IMAGE)

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

    print("FTP CONNECTED")

    try:

        print(f"CURRENT DIR: {ftp.pwd()}")

        files = []

        ftp.retrlines("NLST", files.append)

        print("ROOT FILES/FOLDERS:")

        for f in files:
            print(f)

    except Exception as e:

        print(f"FTP DEBUG ERROR: {e}")

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

# ================= ADM =================

def reset_parser_state():

    global last_position
    global processed_lines

    last_position = 0
    processed_lines.clear()

    print("PARSER RESET")

def find_active_adm():

    global current_adm

    try:

        ftp = connect_ftp()

        adm_files = []

        for path in SEARCH_PATHS:

            try:

                print(f"CHECKING PATH: {path}")

                ftp.cwd(path)

                files = []

                ftp.retrlines("NLST", files.append)

                for file in files:

                    if not file.endswith(".ADM"):
                        continue

                    match = re.search(
                        r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})",
                        file
                    )

                    if not match:
                        continue

                    dt_str = (
                        match.group(1)
                        + " "
                        + match.group(2).replace("-", ":")
                    )

                    try:

                        file_dt = datetime.strptime(
                            dt_str,
                            "%Y-%m-%d %H:%M:%S"
                        )

                    except:
                        continue

                    adm_files.append({
                        "name": file,
                        "path": f"{path}/{file}",
                        "datetime": file_dt
                    })

                    print(f"FOUND ADM: {file}")

                ftp.cwd("/")

            except Exception as e:

                print(f"PATH FAILED: {path} | {e}")

        ftp.quit()

        if not adm_files:

            print("NO ADM FILES FOUND")

            return None

        adm_files.sort(
            key=lambda x: x["datetime"],
            reverse=True
        )

        newest = adm_files[0]

        newest_path = newest["path"]

        if newest_path != current_adm:

            print(f"SWITCHING ADM: {newest_path}")

            current_adm = newest_path

            reset_parser_state()

        return current_adm

    except Exception as e:

        print(f"ADM FINDER ERROR: {e}")

        return None

# ================= DOWNLOAD =================

def download_adm():

    try:

        active_adm = find_active_adm()

        if not active_adm:

            print("NO ACTIVE ADM")

            return False

        path_parts = active_adm.split("/")

        filename = path_parts[-1]

        folder = "/".join(path_parts[:-1])

        ftp = connect_ftp()

        ftp.cwd(folder)

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {filename}",
                f.write
            )

        ftp.quit()

        size = os.path.getsize(LOCAL_LOG_FILE)

        print(f"ADM DOWNLOADED | SIZE: {size}")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False

# ================= DISCORD =================

async def send_embed(channel_id, embed):

    try:

        if not channel_id:
            return

        channel = bot.get_channel(channel_id)

        if channel:
            await channel.send(embed=embed)

    except Exception as e:

        print(f"DISCORD SEND ERROR: {e}")

# ================= PARSER =================

async def process_line(line):

    if should_ignore(line):
        return

    if line in processed_lines:
        return

    processed_lines.add(line)

    if len(processed_lines) > MAX_PROCESSED_LINES:
        processed_lines.clear()

    print(f"PARSED: {line}")

    # ================= RESTART =================

    if "AdminLog started" in line:

        embed = Embed(
            title="Server Restart Detected",
            description="New ADM cycle started.",
            color=0x00ff88
        )

        await send_embed(
            EVENT_CHANNEL_ID,
            style_embed(embed)
        )

        return

    # ================= KILLS =================

    if " killed " in line:

        embed = Embed(
            title="Killfeed",
            description=f"```{line}```",
            color=0xff0000
        )

        await send_embed(
            KILLFEED_CHANNEL_ID,
            style_embed(embed)
        )

        return

    # ================= UNCON =================

    if "unconscious" in line:

        embed = Embed(
            title="Player Unconscious",
            description=f"```{line}```",
            color=0xffaa00
        )

        await send_embed(
            EVENT_CHANNEL_ID,
            style_embed(embed)
        )

        return

    # ================= HITS =================

    if "hit by" in line:

        embed = Embed(
            title="Combat Hit",
            description=f"```{line}```",
            color=0xff8800
        )

        await send_embed(
            EVENT_CHANNEL_ID,
            style_embed(embed)
        )

        return

    # ================= CONNECT =================

    if "is connected" in line:

        embed = Embed(
            title="Player Connected",
            description=f"```{line}```",
            color=0x00ff00
        )

        await send_embed(
            CONNECT_CHANNEL_ID,
            style_embed(embed)
        )

        return

    # ================= DISCONNECT =================

    if "has been disconnected" in line:

        embed = Embed(
            title="Player Disconnected",
            description=f"```{line}```",
            color=0x888888
        )

        await send_embed(
            CONNECT_CHANNEL_ID,
            style_embed(embed)
        )

        return

    # ================= BUILD =================

    if "placed" in line or "built" in line:

        embed = Embed(
            title="Build Event",
            description=f"```{line}```",
            color=0x0099ff
        )

        await send_embed(
            BUILD_CHANNEL_ID,
            style_embed(embed)
        )

async def parse_adm():

    global last_position

    try:

        if not os.path.exists(LOCAL_LOG_FILE):

            print("LOCAL ADM FILE MISSING")

            return

        with open(
            LOCAL_LOG_FILE,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:

            f.seek(last_position)

            lines = f.readlines()

            last_position = f.tell()

        print(f"ADM TOTAL LINES READ: {len(lines)}")

        for line in lines:

            line = line.strip()

            if not line:
                continue

            try:

                await process_line(line)

            except Exception as e:

                print(f"LINE PROCESS ERROR: {e}")

        print("PARSE COMPLETE")

    except Exception as e:

        print(f"PARSER ERROR: {e}")

# ================= TASKS =================

@tasks.loop(seconds=15)
async def adm_loop():

    try:

        print("ADM LOOP RUNNING")

        success = await asyncio.to_thread(
            download_adm
        )

        print(f"DOWNLOAD RESULT: {success}")

        if success:

            await parse_adm()

    except Exception as e:

        print(f"ADM LOOP ERROR: {e}")

# ================= COMMANDS =================

@bot.command()
async def ping(ctx):

    await ctx.send("Pong")

# ================= READY =================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():

        print("STARTING ADM LOOP")

        adm_loop.start()

    asyncio.create_task(
        rcon_loop()
    )

# ================= START =================

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN missing")

Thread(
    target=run_web,
    daemon=True
).start()

bot.run(
    DISCORD_TOKEN,
    reconnect=True
)