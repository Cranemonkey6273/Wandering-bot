import os
import re
import asyncio
import logging
import discord
import berconpy
import json

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

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= WEBSITE =================

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Wandering Bot Omega Online</h1>"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ================= GLOBALS =================

processed_lines = set()
current_adm = None
current_adm_size = 0
last_position = 0
growth_fail_count = 0

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

# ================= GUILD SYSTEM =================

GUILD_FILE = "guilds.json"
guilds = {}

def load_guilds():
    global guilds
    if os.path.exists(GUILD_FILE):
        with open(GUILD_FILE, "r") as f:
            guilds = json.load(f)

def save_guilds():
    with open(GUILD_FILE, "w") as f:
        json.dump(guilds, f, indent=4)

def ensure_guild(gid):
    gid = str(gid)
    if gid not in guilds:
        guilds[gid] = {
            "killfeed": None,
            "event": None,
            "build": None,
            "connect": None
        }
        save_guilds()

# ================= HELPERS =================

def style_embed(embed):
    embed.timestamp = datetime.now(timezone.utc)
    embed.set_thumbnail(url=BOT_IMAGE)
    return embed

# ================= SAFE SEND =================

async def send_embed(channel_id, embed):

    try:
        print(f"[FEED DEBUG] channel_id = {channel_id}")

        if not channel_id or channel_id == 0:
            print("[FEED ERROR] Invalid channel ID")
            return

        channel = bot.get_channel(channel_id)

        if not channel:
            print("[FEED ERROR] Channel not found")
            return

        await channel.send(embed=embed)

        print("[FEED OK] Sent")

    except Exception as e:
        print(f"[FEED ERROR] {e}")

# ================= SETUP COMMAND =================

@bot.command()
async def setup(ctx):

    guild = ctx.guild
    gid = str(guild.id)

    ensure_guild(guild.id)

    channels = {
        "killfeed": "killfeed",
        "event": "events",
        "build": "builds",
        "connect": "connect"
    }

    for key, name in channels.items():

        existing = discord.utils.get(guild.text_channels, name=name)

        if not existing:
            ch = await guild.create_text_channel(name)
        else:
            ch = existing

        guilds[gid][key] = ch.id

    save_guilds()

    await ctx.send("Guild system ready")

# ================= ADM DOWNLOAD =================

def connect_ftp():
    ftp = FTP_TLS()
    ftp.connect(FTP_HOST, FTP_PORT, timeout=60)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.prot_p()
    return ftp

def download_adm():
    try:
        ftp = connect_ftp()
        ftp.cwd(SEARCH_DIR)

        files = []
        ftp.retrlines("NLST", files.append)

        if not files:
            return False

        latest = files[-1]

        with open(LOCAL_LOG_FILE, "wb") as f:
            ftp.retrbinary(f"RETR {latest}", f.write)

        ftp.quit()

        return True

    except Exception as e:
        print(f"ADM ERROR: {e}")
        return False

# ================= PARSER =================

async def process_line(line, guild):

    if "killed" in line:
        embed = Embed(title="Killfeed", description=line, color=0xff0000)
        await send_embed(guilds[str(guild.id)]["killfeed"], style_embed(embed))

    elif "is connected" in line:
        embed = Embed(title="Connect", description=line, color=0x00ff00)
        await send_embed(guilds[str(guild.id)]["connect"], style_embed(embed))

    elif "placed" in line or "built" in line:
        embed = Embed(title="Build", description=line, color=0x0099ff)
        await send_embed(guilds[str(guild.id)]["build"], style_embed(embed))

# ================= LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    try:
        if download_adm():

            guild = bot.guilds[0] if bot.guilds else None
            if not guild:
                return

            # fake line trigger placeholder (your real parser plugs here)
            await process_line("test event kill", guild)

    except Exception as e:
        print(f"ADM LOOP ERROR: {e}")

# ================= READY =================

@bot.event
async def on_ready():
    print(f"LOGGED IN AS {bot.user}")

    load_guilds()

    if not adm_loop.is_running():
        adm_loop.start()

# ================= START =================

if not DISCORD_TOKEN:
    raise ValueError("Missing token")

Thread(target=run_web, daemon=True).start()

bot.run(DISCORD_TOKEN, reconnect=True)