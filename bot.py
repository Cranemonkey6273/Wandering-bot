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

# ================= GLOBALS =================

last_position = 0

# ================= IGNORE FILTER =================

IGNORE_PATTERNS = [
    "script",
    "spawnobject",
    "spawnobjects",
    "globalsinit",
    "onupdate",
    "virtual machine",
    "weapon.savecurrentfsmstate",
    "backlit effects",
    "module:",
    "onstoreload",
]

def should_ignore(line):
    lower = line.lower()
    return any(p in lower for p in IGNORE_PATTERNS)

# ================= FTP =================

def connect_ftp():
    ftp = FTP_TLS()
    ftp.connect(FTP_HOST, FTP_PORT, timeout=60)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.prot_p()
    return ftp

# ================= FIXED ADM DOWNLOAD =================

def download_adm():

    try:
        ftp = connect_ftp()
        ftp.cwd(SEARCH_DIR)

        files = []
        ftp.retrlines("NLST", files.append)

        # 🔥 ONLY VALID ADM FILES
        adm_files = [
            f for f in files
            if f.endswith(".ADM")
            and "script" not in f.lower()
            and "log" not in f.lower()
        ]

        if not adm_files:
            print("NO VALID ADM FILES FOUND")
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

# ================= SAFE DISCORD SEND =================

async def send_embed(channel_id, embed):

    try:
        print(f"[FEED DEBUG] channel_id: {channel_id}")

        if not channel_id or channel_id == 0:
            print("[FEED ERROR] Invalid channel ID")
            return

        channel = bot.get_channel(channel_id)

        if channel is None:
            print("[FEED ERROR] Channel not found")
            return

        await channel.send(embed=embed)

        print("[FEED SUCCESS] Sent")

    except Exception as e:
        print(f"[FEED EXCEPTION] {e}")

# ================= EVENT PROCESSING =================

async def process_line(line):

    if should_ignore(line):
        return

    print(f"[PROCESS LINE] {line}")

    lower = line.lower()

    # ================= KILL =================
    if "killed" in lower and "player" in lower:

        print("[EVENT] KILL")

        embed = discord.Embed(
            title="Killfeed",
            description=line,
            color=0xff0000
        )

        await send_embed(KILLFEED_CHANNEL_ID, embed)
        return

    # ================= CONNECT =================
    if "is connected" in lower:

        print("[EVENT] CONNECT")

        embed = discord.Embed(
            title="Player Connected",
            description=line,
            color=0x00ff00
        )

        await send_embed(CONNECT_CHANNEL_ID, embed)
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

    global last_position

    try:

        if not os.path.exists(LOCAL_LOG_FILE):
            return

        with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:

            f.seek(last_position)
            lines = f.readlines()
            last_position = f.tell()

        for line in lines:

            line = line.strip()

            if not line:
                continue

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

    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()
        print("ADM LOOP STARTED")

# ================= START =================

if not DISCORD_TOKEN:
    raise ValueError("Missing DISCORD_TOKEN")

bot.run(DISCORD_TOKEN, reconnect=True)