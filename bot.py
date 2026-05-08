import os
            embed = discord.Embed(
                description=(
                    f"☠️ {killer} killed {victim}\n"
                    f"⚡ LIVE RCON EVENT"
                ),
                color=0xC0392B
            )

            embed.set_thumbnail(url=BOT_IMAGE)

            await killfeed_channel.send(embed=embed)

# ================= READY =================

@bot.event
async def on_ready():

    await bot.tree.sync()

    if not adm_loop.is_running():
        adm_loop.start()

    if not world_events.is_running():
        world_events.start()

    if not dynamic_economy.is_running():
        dynamic_economy.start()

    if not territory_income.is_running():
        territory_income.start()

    if not ai_radio.is_running():
        ai_radio.start()

    if RCON_ENABLED:
        asyncio.create_task(rcon_listener())

    print(f"✅ Logged in as {bot.user}")

# ================= TASKS =================

@tasks.loop(seconds=30)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

    if success:
        print("ADM UPDATED")

@tasks.loop(minutes=20)
async def world_events():
    pass

@tasks.loop(minutes=60)
async def dynamic_economy():
    pass

@tasks.loop(hours=2)
async def territory_income():
    pass

@tasks.loop(minutes=25)
async def ai_radio():
    pass

# ================= START =================

bot.run(DISCORD_TOKEN)
