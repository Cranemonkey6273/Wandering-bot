import os
import re
import discord

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

REMOTE_LOG_FILE = "/dayzxb/config/server.log"
LOCAL_LOG_FILE = "server.log"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

processed_lines = set()
online_players = set()

def style_embed(embed):

    embed.timestamp = datetime.now(UTC)

    embed.set_footer(
        text="Wandering Bot"
    )

    return embed

def connect_ftp():

    ftp = FTP_TLS()

    ftp.connect(
        FTP_HOST,
        FTP_PORT,
        timeout=30
    )

    ftp.login(
        FTP_USER,
        FTP_PASS
    )

    ftp.prot_p()

    return ftp

def download_server_log():

    try:

        ftp = connect_ftp()

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {REMOTE_LOG_FILE}",
                f.write
            )

        ftp.quit()

        print("SERVER.LOG DOWNLOADED")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False

@bot.event
async def on_ready():

    adm_loop.start()

    print(f"Logged in as {bot.user}")

async def parse_server_log():

    if not os.path.exists(LOCAL_LOG_FILE):

        print("LOCAL SERVER.LOG MISSING")
        return

    with open(
        LOCAL_LOG_FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    print(f"SERVER.LOG READ: {len(lines)}")

    killfeed_channel = bot.get_channel(
        KILLFEED_CHANNEL_ID
    )

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            continue

        if line in processed_lines:
            continue

        processed_lines.add(line)

        if (
            "built" in line.lower()
            or "watchtower" in line.lower()
            or "wall_base" in line.lower()
            or "construction" in line.lower()
        ):

            embed = discord.Embed(
                title="ð¨ Build Event",
                description=line[:3500],
                color=0x2ECC71
            )

            if killfeed_channel:

                await killfeed_channel.send(
                    embed=style_embed(embed)
                )

                print("BUILD EVENT SENT")

        if (
            "placed" in line.lower()
            or "deployed" in line.lower()
        ):

            embed = discord.Embed(
                title="ð¦ Deploy Event",
                description=line[:3500],
                color=0x3498DB
            )

            if killfeed_channel:

                await killfeed_channel.send(
                    embed=style_embed(embed)
                )

                print("DEPLOY EVENT SENT")

        if (
            "destroyed" in line.lower()
            or "breached" in line.lower()
            or "explosive" in line.lower()
        ):

            embed = discord.Embed(
                title="ð´ Raid Event",
                description=line[:3500],
                color=0xE74C3C
            )

            if killfeed_channel:

                await killfeed_channel.send(
                    embed=style_embed(embed)
                )

                print("RAID EVENT SENT")

        if "killed by player" in line.lower():

            victim_match = re.search(
                r'Player "([^"]+)"',
                line
            )

            killer_match = re.search(
                r'killed by Player "([^"]+)"',
                line
            )

            if victim_match and killer_match:

                victim = victim_match.group(1)
                killer = killer_match.group(1)

                embed = discord.Embed(
                    title="â ï¸ PvP Kill",
                    description=(
                        f"Killer: {killer}\n"
                        f"Victim: {victim}"
                    ),
                    color=0xC0392B
                )

                if killfeed_channel:

                    await killfeed_channel.send(
                        embed=style_embed(embed)
                    )

                    print("KILL EVENT SENT")

@tasks.loop(seconds=60)
async def adm_loop():

    success = download_server_log()

    if success:

        await parse_server_log()

@bot.command()
async def online(ctx):

    if not online_players:

        await ctx.send(
            "No online players tracked."
        )

        return

    await ctx.send(
        "\n".join(online_players)
    )

@bot.command()
async def logcheck(ctx):

    await ctx.send(
        f"Reading:\n{REMOTE_LOG_FILE}"
    )

bot.run(DISCORD_TOKEN) 