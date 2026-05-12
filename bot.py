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

# ================= DISCORD =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= GLOBALS =================

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

# ================= FEED SYSTEM =================

async def send_feed(guild, key, embed):

    if not channels_ready:
        return

    try:
        channel = guild_channels[guild.id].get(key)

        if channel:
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

# ================= 🧠 KILL PARSER (NEW INTELLIGENCE LAYER) =================

def parse_kill(line):

    match = re.search(r'"(.+?)".*killed.*"(.+?)"', line)

    if not match:
        return None

    return {
        "killer": match.group(1),
        "victim": match.group(2)
    }

# ================= EVENT ENGINE =================

async def process_line(line, guild):

    if is_noise(line):
        return

    lower = line.lower()

    # ================= CONNECT =================
    if "is connected" in lower or "is connecting" in lower:

        embed = discord.Embed(
            title="Connect",
            description=line,
            color=0x00ff00
        )

        await send_feed(guild, "connect", embed)
        return

    # ================= DISCONNECT =================
    if "has been disconnected" in lower:

        embed = discord.Embed(
            title="Disconnect",
            description=line,
            color=0x888888
        )

        await send_feed(guild, "connect", embed)
        return

    # ================= 💀 KILL (UPGRADED) =================
    if "killed" in lower:

        data = parse_kill(line)

        if data:

            embed = discord.Embed(
                title="💀 Killfeed",
                description=f"**{data['killer']}** killed **{data['victim']}**",
                color=0xff0000
            )

        else:

            embed = discord.Embed(
                title="💀 Killfeed",
                description=line,
                color=0xff0000
            )

        await send_feed(guild, "kill", embed)
        return

    # ================= BUILD =================
    if "placed" in lower or "built" in lower:

        embed = discord.Embed(
            title="Build Event",
            description=line,
            color=0x0099ff
        )

        await send_feed(guild, "build", embed)
        return

# ================= PARSER =================

async def parse_adm(guild):

    try:

        if not os.path.exists(LOCAL_LOG_FILE):
            return

        with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if line:
                await process_line(line, guild)

    except Exception as e:
        print(f"PARSER ERROR: {e}")

# ================= LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    for guild in bot.guilds:
        await process_guild_adm(guild)

# ================= READY =================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()

        print("ADM LOOP STARTED")

# ================= START =================

bot.run(DISCORD_TOKEN, reconnect=True)