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

# ================= FTP =================

def connect_ftp():
    ftp = FTP_TLS()
    ftp.connect(FTP_HOST, FTP_PORT, timeout=60)
    ftp.login(FTP_USER, FTP_PASS)
    ftp.prot_p()
    return ftp

# ================= DOWNLOAD ADM =================

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

# ================= PROCESS LINE =================

async def process_line(line):

    print(f"[PROCESS LINE] {line}")

    if "killed" in line:

        print("[EVENT] Kill detected")

        embed = discord.Embed(
            title="Killfeed",
            description=line,
            color=0xff0000
        )

        await send_embed(KILLFEED_CHANNEL_ID, embed)

    elif "is connected" in line:

        print("[EVENT] Connect detected")

        embed = discord.Embed(
            title="Player Connected",
            description=line,
            color=0x00ff00
        )

        await send_embed(CONNECT_CHANNEL_ID, embed)

    elif "placed" in line or "built" in line:

        print("[EVENT] Build detected")

        embed = discord.Embed(
            title="Build Event",
            description=line,
            color=0x0099ff
        )

        await send_embed(BUILD_CHANNEL_ID, embed)

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

# ================= ADM LOOP =================

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