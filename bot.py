import os

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await connect_channel.send(
                    embed=embed
                )

        elif (
            "is connected" in lower
            or "connected" in lower
        ):

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match and connect_channel:

                player_name = player_match.group(1)

                online_players.add(player_name)

                embed = discord.Embed(
                    description=(
                        f"☣️ {player_name} connected\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x4E7F3D
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await connect_channel.send(
                    embed=embed
                )

        elif (
            "has been disconnected" in lower
            or "disconnected" in lower
        ):

            player_match = re.search(
                r'Player\s+"([^"]+)"',
                line,
                re.IGNORECASE
            )

            if player_match and connect_channel:

                player_name = player_match.group(1)

                online_players.discard(player_name)

                embed = discord.Embed(
                    description=(
                        f"❌ {player_name} disconnected\n"
                        f"🕒 {line[:8]}"
                    ),
                    color=0x8E2E2E
                )

                embed.set_thumbnail(url=BOT_IMAGE)

                embed.set_footer(
                    text="Wandering Bot Intelligence"
                )

                await connect_channel.send(
                    embed=embed
                )


# ================= TASKS =================

@tasks.loop(seconds=30)
async def adm_loop():

    success = await asyncio.to_thread(
        download_adm
    )

    if success:
        await parse_adm()


# ================= START =================

bot.run(DISCORD_TOKEN)
