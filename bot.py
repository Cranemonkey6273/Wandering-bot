import os
import discord

from ftplib import FTP_TLS
from discord.ext import commands, tasks

# ================= CONFIG =================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PORT = int(os.getenv("FTP_PORT", 21))

SEARCH_DIRECTORIES = [
    "/",
    "/dayzxb",
    "/dayzxb/config",
    "/dayzxb/profile",
    "/dayzxb/profiles",
    "/dayzxb/logs",
    "/dayzxb/mpmissions"
]

LOG_EXTENSIONS = [
    ".ADM",
    ".log",
    ".LOG",
    ".txt"
]

# ================= DISCORD =================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ================= FTP =================

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

# ================= DISCOVERY =================

def discover_logs():

    discovered = []

    try:

        ftp = connect_ftp()

        for directory in SEARCH_DIRECTORIES:

            try:

                ftp.cwd(directory)

                files = ftp.nlst()

                print(f"SCANNING: {directory}")

                for file in files:

                    lower = file.lower()

                    if any(
                        lower.endswith(ext.lower())
                        for ext in LOG_EXTENSIONS
                    ):

                        full_path = f"{directory}/{file}"

                        discovered.append(full_path)

                        print(f"FOUND LOG: {full_path}")

            except Exception as e:

                print(
                    f"SCAN FAILED: "
                    f"{directory} -> {e}"
                )

        ftp.quit()

    except Exception as e:

        print(f"FTP ERROR: {e}")

    return discovered

# ================= READY =================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

    log_discovery.start()

# ================= TASK =================

@tasks.loop(hours=12)
async def log_discovery():

    results = discover_logs()

    print("=" * 50)
    print("LOG DISCOVERY COMPLETE")
    print("=" * 50)

    for result in results:

        print(result)

    print("=" * 50)

# ================= COMMAND =================

@bot.command()
async def logs(ctx):

    await ctx.send(
        "Check container logs for FTP discovery results."
    )

# ================= START =================

bot.run(DISCORD_TOKEN)