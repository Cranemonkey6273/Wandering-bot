import os
import re
import asyncio
import logging
import discord
from ftplib import FTP_TLS
from datetime import datetime, timezone
from discord.ext import commands, tasks
from discord import app_commands

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

# ================= BOT =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= SUPABASE =================

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= STATE =================

guild_channels = {}
LOCAL_LOG_FILE = "live.ADM"

# ================= FILTER =================

IGNORE_PATTERNS = [
    "script",
    "spawnobject",
    "globalsinit",
    "weapon.savecurrentfsmstate",
    "playerlist log"
]

def is_noise(line):
    return any(x in line.lower() for x in IGNORE_PATTERNS)

# ================= CONFIG =================

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

# ================= FTP =================

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

# ================= CHANNELS =================

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

# ================= EVENTS =================

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

# ================= KILL PARSER =================

def parse_kill(line):

    match = re.search(r'"(.+?)".*killed.*"(.+?)"', line)
    if match:
        return match.group(1), match.group(2)

    return None

# ================= EMBED =================

def embed(title, desc, color):
    return discord.Embed(
        title=title,
        description=desc,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

# ================= SEND =================

async def send(guild, key, embed_msg):

    ch = guild_channels.get(guild.id, {}).get(key)

    if ch:
        await ch.send(embed=embed_msg)

# ================= PROCESS =================

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

# ================= SLASH SETUP =================

@bot.tree.command(name="setup", description="Link server to ADM system")
async def setup(
    interaction: discord.Interaction,
    ftp_host: str,
    ftp_user: str,
    ftp_pass: str
):

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

        await interaction.followup.send("✅ Setup complete. ADM active.")

    except Exception as e:
        await interaction.followup.send(f"❌ Setup failed: {e}")

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    print(f"LOGGED IN AS {bot.user}")

    if not adm_loop.is_running():
        adm_loop.start()

# ================= RUN =================

bot.run(DISCORD_TOKEN)