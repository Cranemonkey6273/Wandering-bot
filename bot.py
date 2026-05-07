import os
import re
import random
import discord

from ftplib import FTP_TLS
from datetime import datetime, UTC
from discord.ext import commands, tasks
from discord import app_commands

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

EVENT_CHANNEL_ID = int(os.getenv("EVENT_CHANNEL_ID", 0))
KILLFEED_CHANNEL_ID = int(os.getenv("KILLFEED_CHANNEL_ID", 0))
RAID_CHANNEL_ID = int(os.getenv("RAID_CHANNEL_ID", 0))

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIRECTORIES = [
    "/dayzxb",
    "/dayzxb/config",
    "/dayzxb/profiles",
    "/dayzxb/profile",
    "/dayzxb/logs",
    "/dayzxb/mpmissions"
]

LOCAL_LOG_FILE = "live.ADM"

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= GLOBALS =================

last_position = 0
current_log_file = None
online_players = set()

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

def extract_timestamp(filename):

    match = re.search(
        r'(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})',
        filename
    )

    if not match:
        return datetime.min

    return datetime.strptime(
        f"{match.group(1)} "
        f"{match.group(2)}:"
        f"{match.group(3)}:"
        f"{match.group(4)}",
        "%Y-%m-%d %H:%M:%S"
    )

def recursive_find_adms():

    adm_files = []

    try:

        ftp = connect_ftp()

        for directory in SEARCH_DIRECTORIES:

            try:

                ftp.cwd(directory)

                files = ftp.nlst()

                for file in files:

                    if file.endswith(".ADM"):

                        full_path = f"{directory}/{file}"

                        adm_files.append(full_path)

                        print(f"FOUND ADM: {full_path}")

            except Exception as e:

                print(f"SCAN FAILED: {directory} -> {e}")

        ftp.quit()

    except Exception as e:

        print(f"FTP ERROR: {e}")

    return adm_files

def get_latest_adm():

    adm_files = recursive_find_adms()

    if not adm_files:
        return None

    newest = max(
        adm_files,
        key=lambda x: extract_timestamp(x)
    )

    return newest

def download_latest_adm():

    global current_log_file
    global last_position

    try:

        newest_adm = get_latest_adm()

        if not newest_adm:

            print("NO ADM FILES FOUND")
            return False

        if newest_adm != current_log_file:

            current_log_file = newest_adm
            last_position = 0

            print(f"SWITCHED TO LIVE ADM: {newest_adm}")

        ftp = connect_ftp()

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {newest_adm}",
                f.write
            )

        ftp.quit()

        return True

    except Exception as e:

        print(f"DOWNLOAD ERROR: {e}")
        return False

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    adm_loop.start()

    print(f"Logged in as {bot.user}")

# ================= PARSER =================

async def parse_adm():

    global last_position

    if not os.path.exists(LOCAL_LOG_FILE):

        print("LOCAL ADM NOT FOUND")
        return

    with open(
        LOCAL_LOG_FILE,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:

        current_size = os.path.getsize(LOCAL_LOG_FILE)

        if current_size < last_position:
            last_position = 0

        f.seek(last_position)

        lines = f.readlines()

        last_position = f.tell()

    print(f"ADM LINES READ: {len(lines)}")

    killfeed_channel = bot.get_channel(
        KILLFEED_CHANNEL_ID
    )

    for line in lines:

        line = line.strip()

        # ================= CONNECTS =================

        if "is connected" in line:

            match = re.search(
                r'Player "([^"]+)"',
                line
            )

            if match:

                player = match.group(1)

                online_players.add(player)

                print(f"CONNECTED: {player}")

        # ================= DISCONNECTS =================

        if "has been disconnected" in line:

            match = re.search(
                r'Player "([^"]+)"',
                line
            )

            if match:

                player = match.group(1)

                online_players.discard(player)

                print(f"DISCONNECTED: {player}")

        # ================= BUILD EVENTS =================

        if (
            "built" in line.lower()
            or "construction" in line.lower()
            or "wall_base" in line.lower()
            or "watchtower" in line.lower()
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

# ================= TASK =================

@tasks.loop(seconds=30)
async def adm_loop():

    success = download_latest_adm()

    if success:

        await parse_adm()

# ================= COMMANDS =================

@bot.tree.command(
    name="admcheck",
    description="ADM status"
)
async def admcheck(interaction: discord.Interaction):

    exists = os.path.exists(LOCAL_LOG_FILE)

    if exists:

        size = os.path.getsize(LOCAL_LOG_FILE)

        await interaction.response.send_message(
            f"ACTIVE ADM:\n"
            f"{current_log_file}\n\n"
            f"SIZE: {size}"
        )

    else:

        await interaction.response.send_message(
            "NO LOCAL ADM FOUND"
        )

@bot.tree.command(
    name="online",
    description="Online players"
)
async def online(interaction: discord.Interaction):

    if not online_players:

        await interaction.response.send_message(
            "No online players tracked."
        )

        return

    await interaction.response.send_message(
        "\n".join(online_players)
    )

# ================= START =================

bot.run(DISCORD_TOKEN)