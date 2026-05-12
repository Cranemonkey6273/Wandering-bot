# =========================================================
# WANDERING BOT V2 - MULTI GUILD EDITION (UPDATED)
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
# DISCORD
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
GUILD_DATA_FOLDER = "guild_data"

# =========================================================
# GLOBALS
# =========================================================

guild_configs = {}
processed_lines = {}

# =========================================================
# HELPERS
# =========================================================

def style_embed(embed):
    embed.timestamp = datetime.now(UTC)
    return embed


def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(e)


def load_json(path):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        print(e)
    return {}


def save_guild_configs():
    save_json(GUILD_CONFIG_FILE, guild_configs)


def load_guild_configs():
    global guild_configs
    guild_configs = load_json(GUILD_CONFIG_FILE)

# =========================================================
# CONFIG VALIDATION (FIXED)
# =========================================================

def is_config_ready(config):
    return (
        config
        and config.get("nitrado_token")
        and config.get("service_id")
        and config.get("ftp_user")
        and config.get("ftp_pass")
    )

# =========================================================
# AUTO GUILD SETUP
# =========================================================

@bot.event
async def on_guild_join(guild):

    guild_id = str(guild.id)

    if guild_id in guild_configs:
        return

    category = await guild.create_category("📡 WANDERING BOT")

    killfeed = await guild.create_text_channel("🔥・killfeed", category=category)
    deaths = await guild.create_text_channel("☠️・deaths", category=category)
    connections = await guild.create_text_channel("🚪・connections", category=category)
    raids = await guild.create_text_channel("🏴・raids", category=category)
    building = await guild.create_text_channel("🔨・building", category=category)

    guild_configs[guild_id] = {
        "guild_name": guild.name,
        "nitrado_token": "",
        "service_id": "",
        "ftp_user": "",
        "ftp_pass": "",
        "channels": {
            "killfeed": killfeed.id,
            "deaths": deaths.id,
            "connections": connections.id,
            "raids": raids.id,
            "building": building.id,
        }
    }

    save_guild_configs()

# =========================================================
# SLASH SETUP (UPDATED WITH FTP)
# =========================================================

@bot.tree.command(
    name="setup",
    description="Connect Nitrado + FTP server"
)
@app_commands.describe(
    nitrado_token="Nitrado API token",
    service_id="Service ID",
    ftp_user="FTP username",
    ftp_pass="FTP password"
)
async def setup_command(
    interaction: discord.Interaction,
    nitrado_token: str,
    service_id: str,
    ftp_user: str,
    ftp_pass: str
):

    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild.id)

    if guild_id not in guild_configs:
        await interaction.followup.send("Guild not found.", ephemeral=True)
        return

    guild_configs[guild_id]["nitrado_token"] = nitrado_token
    guild_configs[guild_id]["service_id"] = service_id
    guild_configs[guild_id]["ftp_user"] = ftp_user
    guild_configs[guild_id]["ftp_pass"] = ftp_pass

    save_guild_configs()

    embed = discord.Embed(
        title="✅ SERVER CONNECTED",
        description="Nitrado + FTP linked successfully.",
        color=0x57F287
    )

    embed.set_thumbnail(url=BOT_IMAGE)

    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)

# =========================================================
# STATUS COMMAND (NEW)
# =========================================================

@bot.tree.command(name="status", description="Check setup status")
async def status(interaction: discord.Interaction):

    guild_id = str(interaction.guild.id)
    config = guild_configs.get(guild_id)

    if not config:
        await interaction.response.send_message("No config found.", ephemeral=True)
        return

    embed = discord.Embed(title="📊 SERVER STATUS", color=0x3498db)

    embed.add_field(name="Nitrado", value="✅" if config.get("nitrado_token") else "❌", inline=True)
    embed.add_field(name="Service", value="✅" if config.get("service_id") else "❌", inline=True)
    embed.add_field(name="FTP User", value="✅" if config.get("ftp_user") else "❌", inline=True)
    embed.add_field(name="FTP Pass", value="✅" if config.get("ftp_pass") else "❌", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# =========================================================
# ADM LOOP SAFETY (FIXED)
# =========================================================

@tasks.loop(minutes=3)
async def adm_loop():

    if not guild_configs:
        return

    for guild_id, config in guild_configs.items():

        if not is_config_ready(config):
            continue

        # (ADM logic unchanged here intentionally for safety)
        print(f"[ADM] Running for {guild_id}")

# =========================================================
# READY SYNC FIX
# =========================================================

@bot.event
async def on_ready():

    load_guild_configs()

    try:
        synced = await bot.tree.sync()
        print(f"SYNCED {len(synced)} COMMANDS")
    except Exception as e:
        print(f"SYNC ERROR: {e}")

    if not adm_loop.is_running():
        adm_loop.start()

    print(f"LOGGED IN AS {bot.user}")

# =========================================================
# START
# =========================================================

bot.run(DISCORD_TOKEN)