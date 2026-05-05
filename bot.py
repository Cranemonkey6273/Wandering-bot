import discord
import os
import time
import threading
import asyncio

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1501126258140909580

# Auto-detect latest ADM log
def get_log_file():
    files = [f for f in os.listdir() if f.endswith(".ADM")]
    return sorted(files)[-1] if files else None

LOG_FILE = get_log_file()

intents = discord.Intents.default()
client = discord.Client(intents=intents)

print("FILES:", os.listdir())
print("USING LOG:", LOG_FILE)

# ===== EVENT DETECTION =====
def detect_event(line):
    l = line.lower()

    # 💀 death
    if "died" in l:
        return "death"

    # ☠️ suicide
    if "suicide" in l:
        return "suicide"

    # 🧍 unconscious
    if "unconscious" in l:
        return "uncon"

    # 💓 regained consciousness
    if "consciousness" in l:
        return "wake"

    # 🧟 zombie hit
    if "infected" in l or "zombie" in l:
        return "zombie"

    # 🐻 animal hit
    if any(a in l for a in ["bear", "wolf", "animal"]):
        return "animal"

    # 🔫 player vs player
    if "hit by player" in l or "killed by player" in l:
        return "pvp"

    # 👊 damage
    if any(w in l for w in ["damage", "hit", "bleed", "fall"]):
        return "damage"

    # 🧱 build
    if any(w in l for w in ["placed", "built", "constructed"]):
        return "build"

    return None


# ===== SEND EMBEDS =====
async def send_event(title, color, line, emoji):
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found")
        return

    player = "Unknown"
    try:
        parts = line.split('"')
        if len(parts) >= 2:
            player = parts[1]
    except:
        pass

    embed = discord.Embed(
        title=f"{emoji} {title}",
        description=f"**{player}**",
        color=color
    )

    embed.add_field(
        name="📋 Details",
        value=f"```{line[:200]}```",
        inline=False
    )

    embed.set_footer(text="Wandering Survival System")

    await channel.send(embed=embed)


# ===== LOG TRACKER =====
def track_logs():
    global LOG_FILE

    print("TRACKER STARTED")

    while not LOG_FILE:
        print("Waiting for log file...")
        time.sleep(2)
        LOG_FILE = get_log_file()

    print("Log file found:", LOG_FILE)

    try:
        with open(LOG_FILE, "r") as f:
            f.seek(0, 2)

            while True:
                line = f.readline()

                if not line:
                    time.sleep(0.5)
                    continue

                line = line.strip()
                print("RAW:", line)

                event = detect_event(line)

                if not event:
                    continue

                # ===== ROUTING =====
                if event == "death":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Player Died", 0xff0000, line, "💀"),
                        client.loop
                    )

                elif event == "suicide":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Suicide", 0x550000, line, "☠️"),
                        client.loop
                    )

                elif event == "uncon":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Unconscious", 0xffa500, line, "🧍"),
                        client.loop
                    )

                elif event == "wake":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Regained Consciousness", 0x00ff00, line, "💓"),
                        client.loop
                    )

                elif event == "zombie":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Hit by Zombie", 0x228B22, line, "🧟"),
                        client.loop
                    )

                elif event == "animal":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Hit by Animal", 0x8B0000, line, "🐻"),
                        client.loop
                    )

                elif event == "pvp":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Player Combat", 0x800080, line, "🔫"),
                        client.loop
                    )

                elif event == "damage":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Damage Event", 0xffa500, line, "👊"),
                        client.loop
                    )

                elif event == "build":
                    asyncio.run_coroutine_threadsafe(
                        send_event("Construction", 0x8B4513, line, "🧱"),
                        client.loop
                    )

    except Exception as e:
        print("Tracker error:", e)


# ===== DISCORD READY =====
@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Wandering Bot is live.")

    threading.Thread(target=track_logs, daemon=True).start()


# ===== RUN =====
client.run(TOKEN)