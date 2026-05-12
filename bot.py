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

# ================= BOT =================

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

    return {"setup_state": "NOT_SETUP"}

# ================= FTP (ALPHA SYSTEM - UNCHANGED) =================

def connect_ftp(config):
    ftp = FTP_TLS()
    ftp.connect(config["ftp_host"], 21, timeout=60)
    ftp.login(config["ftp_user"], config["ftp_pass"])
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

async def create_channels(guild):

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

    return match.group(1), match.group(2)

# ================= FACTIONS =================

def get_faction(guild_id, player):

    res = supabase.table("player_factions") \
        .select("*") \
        .eq("guild_id", str(guild_id)) \
        .eq("player_name", player) \
        .execute()

    if res.data:
        return res.data[0]["faction_name"]

    return "None"

# ================= ZONES =================

ZONE_SIZE = 1000

def get_zone(line):

    match = re.search(r"pos=<([\d\.\-]+),\s*([\d\.\-]+)", line)

    if not match:
        return None

    x = float(match.group(1))
    y = float(match.group(2))

    return f"{int(x // ZONE_SIZE)}:{int(y // ZONE_SIZE)}"

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

# ================= FACTION + ZONE TRACKER =================

def update_zone_faction(guild_id, killer, victim, line):

    zone = get_zone(line)

    killer_faction = get_faction(guild_id, killer)

    if zone:

        supabase.table("zone_activity").upsert({
            "guild_id": str(guild_id),
            "zone": zone,
            "faction": killer_faction,
            "kills": 1
        }, on_conflict=["guild_id", "zone", "faction"]).execute()

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

            killer, victim = parsed

            update_zone_faction(guild.id, killer, victim, line)

            desc = f"💀 {killer} killed {victim}"

        else:
            desc = line

        await send(guild, "kill", embed("Killfeed", desc, 0xff0000))

# ================= ADM LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    for guild in bot.guilds:

        config = get_server_config(guild.id)

        if config.get("setup_state") != "ACTIVE":
            continue

        success = download_adm(config)

        if not success:
            continue

        try:
            with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    await process_line(line.strip(), guild)

        except Exception as e:
            print(f"[ADM READ ERROR] {e}")

# ================= SETUP =================

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx, ftp_host, ftp_user, ftp_pass):

    guild_id = str(ctx.guild.id)

    supabase.table("server_registry").upsert({
        "guild_id": guild_id,
        "ftp_host": ftp_host,
        "ftp_user": ftp_user,
        "ftp_pass": ftp_pass,
        "search_dir": "/dayzxb/config",
        "setup_state": "ACTIVE"
    }).execute()

    await create_channels(ctx.guild)

    await ctx.send("✅ Setup complete. Alpha system active with factions + zones.")

# ================= READY =================

@bot.event
async def on_ready():
    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()

# ================= RUN =================

bot.run(DISCORD_TOKEN)