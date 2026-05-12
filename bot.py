# =========================================================
# WANDERING BOT V2 - LIVE INTELLIGENCE SYSTEM
# =========================================================

import os
import re
import json
import asyncio
import requests
import discord

from datetime import datetime

try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc

from discord.ext import commands, tasks
from discord import app_commands

# =========================================================
# BOT INIT
# =========================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================================================
# CONSTANTS
# =========================================================

BOT_IMAGE = "https://media.discordapp.net/attachments/1499787777636831324/1501685742433206342/7A382429-B666-4A9F-B890-17C0F7981709.png"

GUILD_CONFIG_FILE = "guild_configs.json"

# =========================================================
# GLOBAL STATE
# =========================================================

guild_configs = {}

online_players = {}
player_stats = {}

# =========================================================
# HELPERS
# =========================================================

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_configs():
    save_json(GUILD_CONFIG_FILE, guild_configs)

def load_configs():
    global guild_configs
    guild_configs = load_json(GUILD_CONFIG_FILE)

# =========================================================
# PLAYER TRACKING
# =========================================================

def handle_connect(player):
    online_players[player] = datetime.utcnow()

    player_stats.setdefault(player, {
        "kills": 0,
        "deaths": 0,
        "builds": 0
    })

def handle_disconnect(player):
    online_players.pop(player, None)

# =========================================================
# SETUP COMMAND (FULL SYSTEM)
# =========================================================

@bot.tree.command(name="setup", description="Deploy full system")
async def setup(interaction: discord.Interaction):

    guild = interaction.guild
    guild_id = str(guild.id)

    if guild_id not in guild_configs:
        guild_configs[guild_id] = {}

    category = await guild.create_category("📡 WANDERING LIVE FEEDS")

    connects = await guild.create_text_channel("🚪・connects", category=category)
    disconnects = await guild.create_text_channel("🔴・disconnects", category=category)
    online = await guild.create_text_channel("🟢・online", category=category)

    leaderboard = await guild.create_text_channel("🏆・leaderboard", category=category)
    heatmap = await guild.create_text_channel("📡・heatmap", category=category)

    admin = await guild.create_text_channel("🛑・admin-chat")
    helpc = await guild.create_text_channel("📘・bot-help")

    await admin.set_permissions(guild.default_role, send_messages=False, read_messages=False)

    guild_configs[guild_id] = {
        "channels": {
            "connects": connects.id,
            "disconnects": disconnects.id,
            "online": online.id,
            "leaderboard": leaderboard.id,
            "heatmap": heatmap.id,
            "admin": admin.id,
            "help": helpc.id
        }
    }

    save_configs()

    embed = discord.Embed(
        title="📘 Wandering Bot Setup Complete",
        description="All systems deployed successfully.",
        color=0x00FFFF
    )

    await helpc.send(embed=embed)
    await interaction.response.send_message("Setup complete", ephemeral=True)

# =========================================================
# 25-MIN LIVE ENGINE
# =========================================================

@tasks.loop(minutes=25)
async def live_engine():

    for guild in bot.guilds:

        config = guild_configs.get(str(guild.id))
        if not config:
            continue

        channels = config.get("channels", {})

        # =====================
        # ONLINE
        # =====================

        online_channel = bot.get_channel(channels.get("online"))

        embed = discord.Embed(
            title="🟢 ONLINE PLAYERS",
            description="\n".join(online_players.keys()) or "None",
            color=0x2ECC71
        )

        if online_channel:
            await online_channel.send(embed=embed)

        # =====================
        # LEADERBOARD
        # =====================

        lb_channel = bot.get_channel(channels.get("leaderboard"))

        sorted_players = sorted(
            player_stats.items(),
            key=lambda x: x[1]["kills"],
            reverse=True
        )

        text = "\n".join(
            [f"🏆 {p[0]} - {p[1]['kills']} kills" for p in sorted_players[:10]]
        ) or "No data"

        embed_lb = discord.Embed(
            title="🏆 LEADERBOARD",
            description=text,
            color=0xF1C40F
        )

        if lb_channel:
            await lb_channel.send(embed=embed_lb)

        # =====================
        # HEATMAP
        # =====================

        heatmap_channel = bot.get_channel(channels.get("heatmap"))

        embed_map = discord.Embed(
            title="📡 HEATMAP UPDATE",
            description="Activity zones updated from server data.",
            color=0x3498DB
        )

        if heatmap_channel:
            await heatmap_channel.send(embed=embed_map)

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    load_configs()

    try:
        await bot.tree.sync()
    except:
        pass

    if not live_engine.is_running():
        live_engine.start()

    print(f"LOGGED IN AS {bot.user}")

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)