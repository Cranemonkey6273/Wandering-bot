import os
import re
import discord

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIR = "/dayzxb/config"

LOCAL_LOG_FILE = "live.ADM"

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= GLOBALS =================

processed_lines = set()
current_adm = None

# ================= FILTERS =================

IGNORE_PATTERNS = [
    "[CE]",
    "LootRespawner",
    "PRIDummy",
    "causing search overtime",
    "Ammo_40mm_Explosive",
    "ConstructionHelmet",
    "script",
    "crash",
    "weather",
    "storage",
    "economy",
    "infected"
]

def should_ignore(line):

    lower = line.lower()

    for pattern in IGNORE_PATTERNS:

        if pattern.lower() in lower:
            return True

    return False

# ================= HELPERS =================

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

def find_active_adm():

    global current_adm

    try:

        ftp = connect_ftp()

        ftp.cwd(SEARCH_DIR)

        files = ftp.nlst()

        adm_files = []

        for file in files:

            if file.endswith(".ADM"):

                adm_files.append(file)

                print(f"FOUND ADM: {file}")

        ftp.quit()

        if not adm_files:
            return None

        newest = sorted(adm_files)[-1]

        current_adm = f"{SEARCH_DIR}/{newest}"

        print(f"ACTIVE ADM: {current_adm}")

        return current_adm

    except Exception as e:

        print(f"ADM SEARCH ERROR: {e}")

        return None

def download_adm():

    try:

        active_adm = find_active_adm()

        if not active_adm:

            return False

        ftp = connect_ftp()

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {active_adm}",
                f.write
            )

        ftp.quit()

        print("ADM DOWNLOADED")

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")

        return False

# ================= READY =================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    adm_loop.start()

# ================= PARSER =================

async def parse_adm():

    if not os.path.exists(LOCAL_LOG_FILE):

        print("LOCAL ADM MISSING")

        return

    with open(
        LOCAL_LOG_FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        lines = f.readlines()

    print(f"ADM LINES READ: {len(lines)}")

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

        if should_ignore(line):
            continue

        lower = line.lower()

        # ================= BUILD EVENTS =================

        if (
            "built" in lower
            or "wall_base" in lower
            or "watchtower" in lower
            or "construction" in lower
            or "territory" in lower
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

        # ================= DEPLOY EVENTS =================

        elif (
            "placed" in lower
            or "deployed" in lower
            or "fencekit" in lower
            or "seachest" in lower
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

        # ================= RAID EVENTS =================

        elif (
            "destroyed" in lower
            or "breached" in lower
            or "raided" in lower
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

        # ================= KILL EVENTS =================

        elif "killed by player" in lower:

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

# ================= LOOP =================

@tasks.loop(seconds=60)
async def adm_loop():

    success = download_adm()

    if success:

        await parse_adm()

# ================= COMMANDS =================

@bot.command()
async def adm(ctx):

    await ctx.send(
        f"Current ADM:\n{current_adm}"
    )

# ================= START =================

bot.run(DISCORD_TOKEN)