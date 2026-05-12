import os
import asyncio
import logging
import discord
from discord.ext import commands, tasks
from ftplib import FTP_TLS
from supabase import create_client

# ================= LOGGING =================

logging.basicConfig(level=logging.INFO)

# ================= BOT =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= SUPABASE =================

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# ================= REGISTRY =================

guild_channels = {}
channels_ready = False

# ================= SERVER REGISTRY =================

def get_server_config(guild_id):

    res = supabase.table("server_registry") \
        .select("*") \
        .eq("guild_id", str(guild_id)) \
        .eq("is_active", True) \
        .execute()

    if not res.data:
        return None

    return res.data[0]

# ================= NITRADO LINK COMMAND =================

@bot.command()
async def linkserver(ctx, name: str, host: str, user: str, password: str):

    supabase.table("server_registry").upsert({
        "guild_id": str(ctx.guild.id),
        "server_name": name,
        "ftp_host": host,
        "ftp_user": user,
        "ftp_pass": password,
        "search_dir": "/dayzxb/config",
        "is_active": True
    }).execute()

    await ctx.send("✅ Nitrado server linked successfully")

# ================= FTP CONNECT =================

def connect_ftp(config):

    ftp = FTP_TLS()
    ftp.connect(config["ftp_host"], 21, timeout=60)
    ftp.login(config["ftp_user"], config["ftp_pass"])
    ftp.prot_p()

    return ftp

# ================= ADM DOWNLOAD PER GUILD =================

async def process_guild_adm(guild):

    config = get_server_config(guild.id)

    if not config:
        print(f"[{guild.name}] No server linked")
        return

    try:
        ftp = connect_ftp(config)
        ftp.cwd(config["search_dir"])

        files = []
        ftp.retrlines("NLST", files.append)

        adm_files = [f for f in files if f.endswith(".ADM")]

        if not adm_files:
            return

        latest = sorted(adm_files)[-1]

        with open("live.ADM", "wb") as f:
            ftp.retrbinary(f"RETR {latest}", f.write)

        ftp.quit()

        print(f"[{guild.name}] ADM UPDATED")

        await parse_adm(guild)

    except Exception as e:
        print(f"[{guild.name}] ADM ERROR: {e}")

# ================= FEED SYSTEM =================

async def send_feed(guild, channel_key, embed):

    if not channels_ready:
        return

    try:
        channel = guild_channels[guild.id].get(channel_key)

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

# ================= EVENT ENGINE =================

async def process_line(line, guild):

    if is_noise(line):
        return

    lower = line.lower()

    # CONNECT
    if "is connected" in lower or "is connecting" in lower:

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

async def parse_adm(guild):

    try:

        if not os.path.exists("live.ADM"):
            return

        with open("live.ADM", "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if line:
                await process_line(line, guild)

    except Exception as e:
        print(f"PARSER ERROR: {e}")

# ================= LOOP =================

@tasks.loop(seconds=20)
async def adm_loop():

    for guild in bot.guilds:
        await process_guild_adm(guild)

# ================= SETUP SYSTEM =================

async def setup_guild_channels():

    global channels_ready

    for guild in bot.guilds:

        guild_channels[guild.id] = {}

        for key in ["kill", "connect", "build"]:

            existing = discord.utils.get(guild.text_channels, name=key)

            if not existing:
                channel = await guild.create_text_channel(key)
            else:
                channel = existing

            guild_channels[guild.id][key] = channel

    channels_ready = True
    print("[SETUP COMPLETE] Guild channels ready")

# ================= READY =================

@bot.event
async def on_ready():

    print(f"LOGGED IN AS {bot.user}")

    await setup_guild_channels()

    if not adm_loop.is_running():
        adm_loop.start()

        print("ADM LOOP STARTED")

# ================= START =================

bot.run(DISCORD_TOKEN, reconnect=True)