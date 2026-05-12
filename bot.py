import os
import re
import asyncio
import logging
import discord
from ftplib import FTP_TLS
from datetime import datetime, timezone
from discord.ext import commands, tasks

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

# ================= DISCORD =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ================= SUPABASE =================

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= GLOBAL STATE =================

guild_channels = {}

LOCAL_LOG_FILE = "live.ADM"

# ================= FILTERS =================

IGNORE_PATTERNS = [
    "script",
    "spawnobject",
    "globalsinit",
    "virtual machine",
    "weapon.savecurrentfsmstate",
    "playerlist log"
]

def is_noise(line):
    return any(p in line.lower() for p in IGNORE_PATTERNS)

# ================= SERVER CONFIG =================

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

    return {
        "guild_id": str(guild_id),
        "nitrado_user": None,
        "service_id": None,
        "api_token": None,
        "search_dir": "/dayzxb/config",
        "setup_state": "NOT_SETUP"
    }

# ================= FTP (UNCHANGED ADM SYSTEM) =================

def connect_ftp(config):
    ftp = FTP_TLS()
    ftp.connect(config.get("ftp_host", ""), 21, timeout=60)
    ftp.login(config.get("ftp_user", ""), config.get("ftp_pass", ""))
    ftp.prot_p()
    return ftp

def download_adm(config):

    try:
        ftp = connect_ftp(config)
        ftp.cwd(config.get("search_dir", "/dayzxb/config"))

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
        print(f"[ADM ERROR] {e}")
        return False

# ================= CHANNEL SETUP =================

async def ensure_channels(guild):

    guild_channels[guild.id] = {}

    defaults = {
        "kill": "killfeed",
        "connect": "player-events",
        "build": "build-feed"
    }

    for key, name in defaults.items():

        channel = discord.utils.get(guild.text_channels, name=name)

        if not channel:
            channel = await guild.create_text_channel(name)

        guild_channels[guild.id][key] = channel

# ================= EVENT DETECTION =================

def detect_event(line):

    l = line.lower()

    if "killed" in l:
        return "kill"
    if "is connected" in l:
        return "connect"
    if "has been disconnected" in l:
        return "disconnect"
    if "placed" in l or "built" in l:
        return "build"

    return None

# ================= KILL PARSER =================

def parse_kill(line):

    match = re.search(r'"(.+?)".*killed.*"(.+?)"', line)
    if not match:
        return None

    killer = match.group(1)
    victim = match.group(2)

    weapon = None
    distance = None

    w = re.search(r"with\s(\w+)", line)
    if w:
        weapon = w.group(1)

    d = re.search(r"(\d+)\s?m", line)
    if d:
        distance = int(d.group(1))

    return killer, victim, weapon, distance

# ================= EMBEDS =================

def embed(title, desc, color):
    return discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

# ================= SEND =================

async def send(guild, key, em):

    ch = guild_channels.get(guild.id, {}).get(key)

    if ch:
        await ch.send(embed=em)

# ================= PROCESS LINE =================

async def process_line(line, guild):

    if is_noise(line):
        return

    event = detect_event(line)

    if not event:
        return

    if event == "connect":
        await send(guild, "connect", embed("Connect", line, 0x00ff00))
        return

    if event == "disconnect":
        await send(guild, "connect", embed("Disconnect", line, 0x888888))
        return

    if event == "build":
        await send(guild, "build", embed("Build", line, 0x0099ff))
        return

    if event == "kill":

        parsed = parse_kill(line)

        if parsed:

            killer, victim, weapon, distance = parsed

            desc = f"💀 {killer} killed {victim}"

            if weapon:
                desc += f"\n🔫 {weapon}"

            if distance:
                desc += f"\n📏 {distance}m"

        else:
            desc = line

        await send(guild, "kill", embed("Killfeed", desc, 0xff0000))

# ================= ADM LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    for guild in bot.guilds:

        config = get_server_config(guild.id)

        # ONLY RUN IF FULLY SETUP
        if config.get("setup_state") != "ACTIVE":
            continue

        success = download_adm(config)

        if not success:
            continue

        try:
            with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for line in lines:
                await process_line(line.strip(), guild)

        except Exception as e:
            print(f"[ADM READ ERROR] {e}")

# ================= SETUP COMMAND =================

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx, nitrado_user, service_id, api_token):

    guild_id = str(ctx.guild.id)

    try:

        supabase.table("server_registry").upsert({
            "guild_id": guild_id,
            "nitrado_user": nitrado_user,
            "service_id": service_id,
            "api_token": api_token,
            "search_dir": "/dayzxb/config",
            "setup_state": "ACTIVE"
        }).execute()

        await ensure_channels(ctx.guild)

        await ctx.send("✅ Setup complete. Server is now ACTIVE.")

    except Exception as e:
        await ctx.send(f"❌ Setup failed: {e}")

# ================= READY =================

@bot.event
async def on_ready():
    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()

# ================= START =================

bot.run(DISCORD_TOKEN)