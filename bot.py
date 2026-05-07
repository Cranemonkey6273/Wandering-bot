import os
import re
import random
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

SEARCH_DIRECTORIES = [
    "/dayzxb",
    "/dayzxb/config"
]

LOCAL_LOG_FILE = "active.ADM"

# ================= DISCORD =================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= GLOBALS =================

processed_lines = set()
current_log_file = None

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

def get_all_adms():

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

                        try:

                            size = ftp.size(file)

                        except:
                            size = 0

                        adm_files.append({
                            "path": full_path,
                            "size": size
                        })

                        print(
                            f"FOUND ADM: "
                            f"{full_path} "
                            f"SIZE={size}"
                        )

            except Exception as e:

                print(
                    f"SCAN FAILED: "
                    f"{directory} -> {e}"
                )

        ftp.quit()

    except Exception as e:

        print(f"FTP ERROR: {e}")

    return adm_files

def choose_active_adm():

    adms = get_all_adms()

    if not adms:
        return None

    # PICK BIGGEST FILE
    # ACTIVE FILE IS USUALLY GROWING/LARGEST

    biggest = max(
        adms,
        key=lambda x: x["size"]
    )

    print(
        f"ACTIVE ADM CHOSEN: "
        f"{biggest['path']} "
        f"SIZE={biggest['size']}"
    )

    return biggest["path"]

def download_active_adm():

    global current_log_file

    try:

        active_adm = choose_active_adm()

        if not active_adm:

            print("NO ACTIVE ADM FOUND")
            return False

        current_log_file = active_adm

        ftp = connect_ftp()

        with open(LOCAL_LOG_FILE, "wb") as f:

            ftp.retrbinary(
                f"RETR {active_adm}",
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

    adm_loop.start()

    print(f"Logged in as {bot.user}")

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

    print(f"FULL ADM READ: {len(lines)}")

    killfeed_channel = bot.get_channel(
        KILLFEED_CHANNEL_ID
    )

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            continue

        # ================= DUPLICATE CHECK =================

        if line in processed_lines:
            continue

        processed_lines.add(line)

        # ================= BUILD EVENTS =================

        if (
            "built" in line.lower()
            or "watchtower" in line.lower()
            or "wall_base" in line.lower()
            or "construction" in line.lower()
        ):

            embed = discord.Embed(
                title="Build Event",
                description=line[:3500],
                color=0x2ECC71
            )

            if killfeed_channel:

                await killfeed_channel.send(
                    embed=style_embed(embed)
                )

                print("BUILD EVENT SENT")

        # ================= KILLS =================

        if "killed by Player" in line:

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
                    title="PvP Kill",
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

    success = download_active_adm()

    if success:

        await parse_adm()

# ================= COMMAND =================

@bot.command()
async def adm(ctx):

    await ctx.send(
        f"ACTIVE ADM:\n{current_log_file}"
    )

# ================= START =================

bot.run(DISCORD_TOKEN)