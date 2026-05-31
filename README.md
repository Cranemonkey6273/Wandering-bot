# Wandering-bot

Wandering Bot is a multi-guild Discord bot for DayZ communities. It reads ADM activity, manages Discord feeds, tracks player stats, powers economy/faction tooling, and ships with a Wandering Bot feature dashboard.

## Web dashboard

The dashboard runs from the same JSON data files that the Discord bot writes. It now uses a mobile-first Wandering Bot feature-panel style with the local `wanderingbot.png` survivor image, black/cream/survivor-green branding, gritty DayZ-inspired panels, and module sections for:

- server overview and setup status
- live online survivors and leaderboards
- radar/polygon zone management scaffold
- economy, shop, wallets, delivery queue, and wages overview
- faction management overview
- embed studio scaffold
- per-guild dashboard access/subscription status

Secrets such as Nitrado tokens and FTP credentials are filtered before data is shown in the UI or returned by `/api/summary`.

### Embedded with the bot

`bot.py` starts the dashboard automatically before connecting to Discord. When embedded, the dashboard receives live in-memory bot state for guild configs, player stats, online players, factions, shop items, wallets, and delivery queue counts.

Required environment variables:

- `DISCORD_TOKEN` - Discord bot token.
- `PORT` - web port supplied by Railway/your host. Defaults to `8080` locally.

Optional environment variables:

- `WANDERING_DASHBOARD_ENABLED=0` - disables the embedded dashboard.
- `WANDERING_DASHBOARD_HOST=0.0.0.0` - host interface for Flask.
- `WANDERING_DASHBOARD_PORT=8080` - fallback port when `PORT` is not set.
- `WANDERING_DASHBOARD_REFRESH_SECONDS=60` - browser auto-refresh interval.
- `WANDERING_BOT_IMAGE_FILE=/path/to/image.png` - override the dashboard brand image. Defaults to `wanderingbot.png` in the repo.
- `WANDERING_DATA_DIR` - persistent data folder. The dashboard also honors Railway volume variables used by the bot.

### Standalone local run

```bash
python dashboard.py
```

Then open:

- `http://localhost:8080/` for the dashboard page.
- `http://localhost:8080/brand-image` for the Wandering Bot brand image used by the UI.
- `http://localhost:8080/api/summary` for JSON.
- `http://localhost:8080/healthz` for a health check.

> Note: The current dashboard keeps management controls as a safe scaffold until Discord OAuth, permission checks, and subscription gates are added. Do not expose write actions publicly until those protections are in place.

## Bot entry point

```bash
python bot.py
```
