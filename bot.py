import os
import re
import asyncio
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
from ftplib import FTP_TLS
from datetime import datetime, timezone

from supabase import create_client

# ===================== LOGGING =====================

logging.basicConfig(level=logging.INFO)

# ===================== ENV =====================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ===================== BOT =====================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===================== SUPABASE =====================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===================== STATE =====================

guild_channels = {}
LOCAL_ADM_FILE = "live.ADM"

# ===================== FILTER =====================

IGNORE_PATTERNS = [
    "script",
    "spawnobject",
    "globalsinit"
]

def is_noise(line):
    return any(p in line.lower() for p in IGNORE_PATTERNS)

# ===================== CONFIG =====================

def get_server_config(guild_id):

    try:
        res = supabase.table("server_registry") \
            .select("*") \
            .eq("guild_id", str(guild_id)) \
            .execute()

        if res.data:
            return res.data[0]

    except Exception as e:
        print(f"[CONFIG ERROR] {e}")

    return None

# ===================== FTP =====================

def download_adm(config):

    try:
        ftp = FTP_TLS()
        ftp.connect(config["ftp_host"], 21, timeout=60)
        ftp.login(config["ftp_user"], config["ftp_pass"])
        ftp.prot_p()

        ftp.cwd(config.get("search_dir", "/dayzxb/config"))

        files = []
        ftp.retrlines("NLST", files.append)

        adm_files = [f for f in files if f.endswith(".ADM")]

        if not adm_files:
            return False

        latest = sorted(adm_files)[-1]

        with open(LOCAL_ADM_FILE, "wb") as f:
            ftp.retrbinary(f"RETR {latest}", f.write)

        ftp.quit()
        return True

    except Exception as e:
        print(f"[ADM ERROR] {e}")
        return False

# ===================== CHANNELS =====================

async def create_channels(guild):

    guild_channels[guild.id] = {}

    required = {
        "kill": "killfeed",
        "connect": "connect",
        "build": "build-feed"
    }

    for key, name in required.items():

        channel = discord.utils.get(guild.text_channels, name=name)

        if not channel:
            channel = await guild.create_text_channel(name)

        guild_channels[guild.id][key] = channel

# ===================== EVENT DETECTION =====================

def detect_event(line):

    l = line.lower()

    if "killed" in l:
        return "kill"
    if "is connected" in l:
        return "connect"
    if "has been disconnected" in l:
        return "disconnect"
    if "placed" in l:
        return "build"

    return None

# ===================== PROCESS LINE =====================

async def process_line(line, guild):

    if not line or is_noise(line):
        return

    event = detect_event(line)

    if not event:
        return

    channels = guild_channels.get(guild.id, {})

    if event == "connect":
        ch = channels.get("connect")
        if ch:
            await ch.send(f"🟢 {line}")

    elif event == "disconnect":
        ch = channels.get("connect")
        if ch:
            await ch.send(f"🔴 {line}")

    elif event == "build":
        ch = channels.get("build")
        if ch:
            await ch.send(f"🏗️ {line}")

    elif event == "kill":
        ch = channels.get("kill")
        if ch:
            await ch.send(f"💀 {line}")

# ===================== ADM LOOP =====================

@tasks.loop(seconds=15)
async def adm_loop():

    for guild in bot.guilds:

        config = get_server_config(guild.id)

        if not config:
            continue

        if config.get("setup_state") != "ACTIVE":
            continue

        success = download_adm(config)

        if not success:
            continue

        try:
            with open(LOCAL_ADM_FILE, "r", encoding="utf-8", errors="ignore") as f:

                for line in f:
                    await process_line(line.strip(), guild)

        except Exception as e:
            print(f"[ADM READ ERROR] {e}")

# ===================== SLASH SETUP =====================

@bot.tree.command(name="setup", description="Link server to ADM system")
async def setup(interaction: discord.Interaction,
                ftp_host: str,
                ftp_user: str,
                ftp_pass: str):

    await interaction.response.send_message("⚙️ Setting up server...")

    guild_id = str(interaction.guild.id)

    try:

        supabase.table("server_registry").upsert({
            "guild_id": guild_id,
            "ftp_host": ftp_host,
            "ftp_user": ftp_user,
            "ftp_pass": ftp_pass,
            "search_dir": "/dayzxb/config",
            "setup_state": "ACTIVE"
        }).execute()

        await create_channels(interaction.guild)

        await interaction.followup.send("✅ Setup complete. ADM is now active.")

    except Exception as e:
        await interaction.followup.send(f"❌ Setup failed: {e}")

# ===================== READY =====================

@bot.event
async def on_ready():

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")

    except Exception as e:
        print(f"Sync error: {e}")

    print(f"Logged in as {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()

# ===================== RUN =====================

bot.run(DISCORD_TOKEN)