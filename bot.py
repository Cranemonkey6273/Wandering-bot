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

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# ================= CHANNEL IDS =================

KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
BUILD_CHANNEL_ID = int(os.getenv("BUILD_CHANNEL_ID", 0))
CONNECT_CHANNEL_ID = int(os.getenv("CONNECT_CHANNEL_ID", 0))

# ================= GLOBAL STATE =================

channels_ready = False   # 🔥 NEW: setup gate

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

# ================= FTP CONNECT =================

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
            print("NO ADM FILES FOUND")
            return False

        latest = sorted(adm_files)[-1]

        print(f"[ADM SELECTED] {latest}")

        with open(LOCAL_LOG_FILE, "wb") as f:
            ftp.retrbinary(f"RETR {latest}", f.write)

        ftp.quit()
        return True

    except Exception as e:
        print(f"ADM ERROR: {e}")
        return False

# ================= SAFE DISCORD SEND (GATED) =================

async def send_embed(channel_id, embed):

    global channels_ready

    # 🔥 BLOCK FEEDS UNTIL SETUP IS DONE
    if not channels_ready:
        print("[FEED BLOCKED] Channels not ready yet")
        return

    try:
        print(f"[FEED DEBUG] channel_id: {channel_id}")

        if not channel_id or channel_id == 0:
            print("[FEED ERROR] Invalid channel ID")
            return

        channel = bot.get_channel(channel_id)

        if channel is None:
            channel = await bot.fetch_channel(channel_id)

        await channel.send(embed=embed)

        print("[FEED SUCCESS] Sent")

    except Exception as e:
        print(f"[FEED ERROR] {e}")

# ================= NOISE FILTER =================

def is_noise(line):

    lower = line.lower()

    noise = [
        "script",
        "spawnobject",
        "globalsinit",
        "onupdate",
        "virtual machine",
        "weapon.savecurrentfsmstate",
        "backlit effects",
        "module:",
        "onstoreload",
        "playerlist log",
        "log c:\\",
        "entity id:",
        "function:"
    ]

    return any(n in lower for n in noise)

# ================= EVENT ENGINE =================

async def process_line(line):

    if is_noise(line):
        return

    print(f"[PROCESS LINE] {line}")

    lower = line.lower()

    # ================= CONNECT =================
    if "is connecting" in lower or "is connected" in lower:
        print("[EVENT] CONNECT")

        embed = discord.Embed(
            title="Player Connect",
            description=line,
            color=0x00ff00
        )

        await send_embed(CONNECT_CHANNEL_ID, embed)
        return

    # ================= DISCONNECT =================
    if "has been disconnected" in lower or "disconnected" in lower:
        print("[EVENT] DISCONNECT")

        embed = discord.Embed(
            title="Player Disconnect",
            description=line,
            color=0x888888
        )

        await send_embed(CONNECT_CHANNEL_ID, embed)
        return

    # ================= KILL =================
    if "killed player" in lower or '" killed "' in lower:
        print("[EVENT] KILL")

        embed = discord.Embed(
            title="Killfeed",
            description=line,
            color=0xff0000
        )

        await send_embed(KILLFEED_CHANNEL_ID, embed)
        return

    # ================= BUILD =================
    if "placed" in lower or "built" in lower:
        print("[EVENT] BUILD")

        embed = discord.Embed(
            title="Build Event",
            description=line,
            color=0x0099ff
        )

        await send_embed(BUILD_CHANNEL_ID, embed)
        return

# ================= PARSER =================

async def parse_adm():

    try:

        if not os.path.exists(LOCAL_LOG_FILE):
            return

        with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if line:
                await process_line(line)

    except Exception as e:
        print(f"PARSER ERROR: {e}")

# ================= LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    try:
        success = download_adm()

        if success:
            print("ADM UPDATED")
            await parse_adm()

    except Exception as e:
        print(f"ADM LOOP ERROR: {e}")

# ================= READY =================

@bot.event
async def on_ready():

    global channels_ready

    print(f"LOGGED IN AS {bot.user}")

    # 🔥 THIS IS THE IMPORTANT PART
    # replace this later with your real setup system hook
    channels_ready = True
    print("CHANNEL SYSTEM READY (FEEDS UNLOCKED)")

    if not adm_loop.is_running():
        adm_loop.start()
        print("ADM LOOP STARTED")

# ================= START =================

if not DISCORD_TOKEN:
    raise ValueError("Missing DISCORD_TOKEN")

bot.run(DISCORD_TOKEN, reconnect=True)