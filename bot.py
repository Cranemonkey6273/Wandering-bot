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

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= GLOBAL STATE =================

guild_channels = {}

# ================= ADM STATE =================

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
    lower = line.lower()
    return any(p in lower for p in IGNORE_PATTERNS)

# ================= FTP (UNCHANGED SYSTEM) =================

def connect_ftp(config):
    ftp = FTP_TLS()
    ftp.connect(config["ftp_host"], 21, timeout=60)
    ftp.login(config["ftp_user"], config["ftp_pass"])
    ftp.prot_p()
    return ftp

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

# ================= PARSERS =================

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

# ================= FEED =================

async def send(guild, key, em):

    ch = guild_channels.get(guild.id, {}).get(key)

    if ch:
        await ch.send(embed=em)

# ================= PLAYER STATS =================

def update_player_stats(guild_id, killer, victim):

    supabase.table("player_stats").upsert({
        "guild_id": str(guild_id),
        "player_name": killer,
        "kills": 1
    }, on_conflict=["guild_id", "player_name"]).execute()

    supabase.table("player_stats").upsert({
        "guild_id": str(guild_id),
        "player_name": victim,
        "deaths": 1
    }, on_conflict=["guild_id", "player_name"]).execute()

# ================= FACTIONS =================

def get_faction(guild_id, player):

    res = supabase.table("player_factions") \
        .select("*") \
        .eq("guild_id", str(guild_id)) \
        .eq("player_name", player) \
        .execute()

    return res.data[0]["faction_name"] if res.data else None

# ================= ADM DOWNLOAD (UNCHANGED LOGIC HOOK) =================

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

# ================= PARSER =================

async def process_line(line, guild):

    if is_noise(line):
        return

    event = detect_event(line)

    if not event:
        return

    # CONNECT
    if event == "connect":
        await send(guild, "connect", embed("Connect", line, 0x00ff00))
        return

    # DISCONNECT
    if event == "disconnect":
        await send(guild, "connect", embed("Disconnect", line, 0x888888))
        return

    # BUILD
    if event == "build":
        await send(guild, "build", embed("Build", line, 0x0099ff))
        return

    # KILL
    if event == "kill":

        parsed = parse_kill(line)

        if parsed:

            killer, victim, weapon, distance = parsed

            update_player_stats(guild.id, killer, victim)

            desc = f"💀 {killer} killed {victim}"

            if weapon:
                desc += f"\n🔫 {weapon}"

            if distance:
                desc += f"\n📏 {distance}m"

        else:
            desc = line

        await send(guild, "kill", embed("Killfeed", desc, 0xff0000))
        return

# ================= ADM LOOP =================

@tasks.loop(seconds=15)
async def adm_loop():

    for guild in bot.guilds:

        config = get_server_config(guild.id)

        if not config:
            continue

        success = download_adm(config)

        if success:

            if os.path.exists(LOCAL_LOG_FILE):

                with open(LOCAL_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                for line in lines:
                    await process_line(line.strip(), guild)

# ================= READY =================

@bot.event
async def on_ready():
    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()

# ================= START =================

bot.run(DISCORD_TOKEN)