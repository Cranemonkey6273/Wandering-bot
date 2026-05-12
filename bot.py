import os
import re
import asyncio
import logging
import discord
import berconpy

from datetime import datetime, timezone
from discord.ext import commands, tasks
from ftplib import FTP_TLS

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

# ================= DISCORD =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= GLOBAL STATE =================

guild_channels = {}
channels_ready = True  # you said you’ll handle guild setup later

# ================= FTP CONFIG =================

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"
LOCAL_LOG_FILE = "live.ADM"

# ================= ADM STATE =================

last_position = 0

# ================= EVENT SYSTEM =================

EVENT_KEYWORDS = {
    "connect": ["is connected", "is connecting"],
    "disconnect": ["has been disconnected"],
    "kill": ["killed"],
    "build": ["placed", "built"]
}

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
            return False

        latest = sorted(adm_files)[-1]

        with open(LOCAL_LOG_FILE, "wb") as f:
            ftp.retrbinary(f"RETR {latest}", f.write)

        ftp.quit()

        print(f"[ADM] Downloaded: {latest}")
        return True

    except Exception as e:
        print(f"[ADM ERROR] {e}")
        return False

# ================= FEED SYSTEM =================

async def send_feed(guild, key, embed):

    try:
        channel = guild_channels.get(guild.id, {}).get(key)

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

# ================= EVENT DETECTOR =================

def detect_event(line):

    lower = line.lower()

    for event, keywords in EVENT_KEYWORDS.items():
        for k in keywords:
            if k in lower:
                return event

    return None

# ================= KILL PARSER =================

def parse_kill(line):

    match = re.search(r'"(.+?)".*killed.*"(.+?)"', line)

    if not match:
        return None

    return {
        "killer": match.group(1),
        "victim": match.group(2)
    }

# ================= EMBED BUILDER =================

def build_embed(title, description, color):

    return discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

# ================= EVENT ENGINE =================

async def process_line(line, guild):

    if is_noise(line):
        return

    event = detect_event(line)

    if not event:
        return

    # ================= CONNECT =================
    if event == "connect":

        embed = build_embed("Connect", line, 0x00ff00)
        await send_feed(guild, "connect", embed)
        return

    # ================= DISCONNECT =================
    if event == "disconnect":

        embed = build_embed("Disconnect", line, 0x888888)
        await send_feed(guild, "connect", embed)
        return

    # ================= KILL =================
    if event == "kill":

        data = parse_kill(line)

        if data:
            desc = f"**{data['killer']}** killed **{data['victim']}**"
        else:
            desc = line

        embed = build_embed("💀 Killfeed", desc, 0xff0000)
        await send_feed(guild, "kill", embed)
        return

    # ================= BUILD =================
    if event == "build":

        embed = build_embed("Build", line, 0x0099ff)
        await send_feed(guild, "build", embed)
        return

# ================= PARSER =================

async def parse_adm(guild):

    global last_position

    if not os.path.exists(LOCAL_LOG_FILE):
        return

    with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for line in lines:
        line = line.strip()

        if line:
            await process_line(line, guild)

# ================= ADM LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    for guild in bot.guilds:
        await download_adm()
        await parse_adm(guild)

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