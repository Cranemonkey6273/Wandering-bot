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
from supabase import create_client

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= GLOBAL STATE =================

guild_channels = {}
channels_ready = False

# ================= FTP =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"
LOCAL_LOG_FILE = "live.ADM"

# ================= CONNECT FTP =================

def connect_ftp():
    ftp = FTP_TLS()
    ftp.connect(FTP_HOST, FTP_PORT, timeout=60)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.prot_p()
    return ftp

# ================= ADM DOWNLOAD =================

def download_adm():
    try:
        ftp = connect_ftp()
        ftp.cwd(SEARCH_DIR)

        files = []
        ftp.retrlines("NLST", files.append)

        adm_files = [f for f in files if f.endswith(".ADM")]

        if not adm_files:
            return False

        latest = sorted(adm_files)[-1]

        with open(LOCAL_LOG_FILE, "wb") as f:
            ftp.retrbinary(f"RETR {latest}", f.write)

        ftp.quit()
        return True

    except Exception as e:
        print(f"ADM ERROR: {e}")
        return False

# ================= DB SAVE =================

async def save_channel(guild_id, key, channel_id):

    try:
        supabase.table("guild_channels").upsert({
            "guild_id": str(guild_id),
            "channel_key": key,
            "channel_id": str(channel_id)
        }).execute()

    except Exception as e:
        print(f"[DB SAVE ERROR] {e}")

# ================= DB LOAD =================

async def load_guild_channels():

    global guild_channels

    try:
        res = supabase.table("guild_channels").select("*").execute()

        for row in res.data:

            gid = int(row["guild_id"])
            key = row["channel_key"]
            cid = int(row["channel_id"])

            if gid not in guild_channels:
                guild_channels[gid] = {}

            guild_channels[gid][key] = await bot.fetch_channel(cid)

        print("[DB LOAD] Channels restored")

    except Exception as e:
        print(f"[DB LOAD ERROR] {e}")

# ================= SETUP SYSTEM =================

async def setup_guild_channels():

    global channels_ready

    for guild in bot.guilds:

        print(f"[SETUP] {guild.name}")

        if guild.id not in guild_channels:
            guild_channels[guild.id] = {}

        for key in ["kill", "connect", "build"]:

            channel = discord.utils.get(guild.text_channels, name=key)

            if not channel:
                channel = await guild.create_text_channel(key)

            guild_channels[guild.id][key] = channel

            await save_channel(guild.id, key, channel.id)

    channels_ready = True
    print("[SETUP COMPLETE] Persistent system ready")

# ================= SAFE FEED =================

async def send_feed(guild, key, embed):

    if not channels_ready:
        print("[FEED BLOCKED] Setup not ready")
        return

    try:
        channel = guild_channels[guild.id].get(key)

        if not channel:
            print(f"[FEED ERROR] Missing {key}")
            return

        await channel.send(embed=embed)

    except Exception as e:
        print(f"[FEED ERROR] {e}")

# ================= NOISE FILTER =================

def is_noise(line):

    lower = line.lower()

    return any(x in lower for x in [
        "script",
        "spawnobject",
        "globalsinit",
        "virtual machine",
        "weapon.savecurrentfsmstate",
        "module:",
        "playerlist log"
    ])

# ================= EVENT ENGINE =================

async def process_line(line):

    if is_noise(line):
        return

    lower = line.lower()
    guild = bot.guilds[0]

    # CONNECT
    if "is connecting" in lower or "is connected" in lower:

        embed = discord.Embed(
            title="Connect",
            description=line,
            color=0x00ff00
        )

        await send_feed(guild, "connect", embed)
        return

    # DISCONNECT
    if "has been disconnected" in lower:

        embed = discord.Embed(
            title="Disconnect",
            description=line,
            color=0x888888
        )

        await send_feed(guild, "connect", embed)
        return

    # KILL
    if "killed player" in lower:

        embed = discord.Embed(
            title="Killfeed",
            description=line,
            color=0xff0000
        )

        await send_feed(guild, "kill", embed)
        return

    # BUILD
    if "placed" in lower or "built" in lower:

        embed = discord.Embed(
            title="Build",
            description=line,
            color=0x0099ff
        )

        await send_feed(guild, "build", embed)
        return

# ================= PARSER =================

async def parse_adm():

    if not os.path.exists(LOCAL_LOG_FILE):
        return

    with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()
        if line:
            await process_line(line)

# ================= LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    success = download_adm()

    if success:
        print("ADM UPDATED")
        await parse_adm()

# ================= READY =================

@bot.event
async def on_ready():

    global channels_ready

    print(f"LOGGED IN AS {bot.user}")

    await load_guild_channels()
    await setup_guild_channels()

    if not adm_loop.is_running():
        adm_loop.start()

    print("SYSTEM FULLY ONLINE")

# ================= START =================

if not DISCORD_TOKEN:
    raise ValueError("Missing DISCORD_TOKEN")

bot.run(DISCORD_TOKEN, reconnect=True)