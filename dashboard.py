"""Web dashboard for Wandering Bot.

This module intentionally reads the same JSON files that ``bot.py`` writes,
so it can run embedded beside the Discord bot or standalone for local checks.
Secrets such as Nitrado tokens and FTP credentials are never rendered.
"""

import json
import os
from datetime import UTC, datetime
from threading import Thread

from flask import Flask, jsonify, render_template_string, send_file


DATA_ROOT = (
    os.getenv("WANDERING_DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or os.getenv("RAILWAY_VOLUME_PATH")
    or "."
)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
BOT_IMAGE_FILE = os.getenv("WANDERING_BOT_IMAGE_FILE", os.path.join(APP_ROOT, "wanderingbot.png"))

DASHBOARD_REFRESH_SECONDS = int(os.getenv("WANDERING_DASHBOARD_REFRESH_SECONDS", "60"))
DASHBOARD_HOST = os.getenv("WANDERING_DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("PORT") or os.getenv("WANDERING_DASHBOARD_PORT", "8080"))


APP = Flask(__name__)
CUSTOM_STATE_PROVIDER = None


PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{{ refresh_seconds }}">
  <title>Wandering Bot Control Deck</title>
  <style>
    :root {
      color-scheme: dark;
      --void: #050912;
      --ink: #0b1423;
      --navy: #111d31;
      --card: #182641;
      --card-soft: #213554;
      --field: #0f1a2c;
      --field-2: #15233a;
      --line: rgba(180, 204, 255, .12);
      --text: #edf5ff;
      --muted: #a9bbd5;
      --dim: #70839f;
      --brand: #7154ff;
      --brand-2: #9a7cff;
      --cyan: #44d7ff;
      --green: #45df9a;
      --red: #ee2238;
      --gold: #f5c85c;
      --radius: 1.35rem;
    }
    * { box-sizing: border-box; }
    html { background: var(--void); }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 7% -8%, rgba(113, 84, 255, .38), transparent 23rem),
        radial-gradient(circle at 105% 8%, rgba(68, 215, 255, .14), transparent 22rem),
        linear-gradient(180deg, #0a1220 0%, var(--void) 100%);
      color: var(--text);
    }
    a { color: var(--cyan); text-decoration: none; }
    h1, h2, h3, p { margin-top: 0; }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 20;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: .85rem clamp(1rem, 4vw, 2rem);
      background: rgba(12, 22, 38, .88);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(18px);
    }
    .brand { display: flex; align-items: center; gap: .8rem; min-width: 0; }
    .brand img {
      width: 2.25rem;
      height: 2.25rem;
      border-radius: .8rem;
      object-fit: cover;
      box-shadow: 0 0 0 1px rgba(255,255,255,.18), 0 0 1.5rem rgba(113,84,255,.4);
    }
    .brand strong { display: block; font-size: .98rem; letter-spacing: .02em; }
    .brand span { display: block; color: var(--muted); font-size: .78rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hamburger { display: grid; gap: .28rem; padding: .55rem; border: 1px solid var(--line); border-radius: .8rem; background: var(--field); }
    .hamburger i { display: block; width: 1.35rem; height: .13rem; border-radius: 1rem; background: var(--text); }
    .shell {
      display: grid;
      grid-template-columns: minmax(13rem, 17rem) minmax(0, 1fr);
      gap: 1.25rem;
      padding: 1.25rem clamp(1rem, 4vw, 2rem) 2rem;
      max-width: 1480px;
      margin: 0 auto;
    }
    .sidebar, .hero, .card, .zone-card, .server-card {
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(255,255,255,.045), rgba(255,255,255,.015)), var(--navy);
      border-radius: var(--radius);
      box-shadow: 0 1.25rem 3rem rgba(0, 0, 0, .34);
    }
    .sidebar { position: sticky; top: 5rem; align-self: start; padding: .9rem; }
    .nav-title { color: var(--dim); font-size: .72rem; letter-spacing: .14em; text-transform: uppercase; padding: .55rem .7rem; }
    .nav-link { display: flex; justify-content: space-between; gap: .6rem; padding: .72rem .78rem; border-radius: .9rem; color: var(--muted); }
    .nav-link strong { color: var(--text); font-weight: 700; }
    .nav-link.active, .nav-link:hover { background: rgba(113, 84, 255, .16); color: var(--text); }
    .badge { color: var(--text); background: var(--brand); border-radius: 999px; padding: .12rem .45rem; font-size: .7rem; font-weight: 800; }
    main { display: grid; gap: 1.1rem; min-width: 0; }
    .hero { padding: clamp(1.1rem, 4vw, 1.8rem); overflow: hidden; position: relative; }
    .hero:after { content: ""; position: absolute; inset: auto -8rem -10rem auto; width: 24rem; height: 24rem; background: radial-gradient(circle, rgba(113,84,255,.35), transparent 65%); pointer-events: none; }
    .eyebrow { color: var(--brand-2); font-size: .78rem; font-weight: 900; letter-spacing: .14em; text-transform: uppercase; }
    h1 { margin: .25rem 0 .5rem; font-size: clamp(1.8rem, 5vw, 4rem); line-height: .98; }
    .sub { color: var(--muted); max-width: 68rem; line-height: 1.6; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .8rem; }
    .stat-card { padding: 1rem; border-radius: 1.1rem; background: rgba(15, 26, 44, .72); border: 1px solid var(--line); }
    .stat-card span { color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }
    .stat-card strong { display: block; margin-top: .25rem; font-size: 1.75rem; }
    .module-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .9rem; }
    .card { padding: 1rem; }
    .card h3, .zone-card h2, .server-card h2 { margin-bottom: .35rem; }
    .card p { color: var(--muted); line-height: 1.5; font-size: .93rem; }
    .status { display: inline-flex; align-items: center; gap: .35rem; margin-top: .45rem; padding: .28rem .55rem; border-radius: 999px; background: var(--field); color: var(--muted); font-size: .78rem; border: 1px solid var(--line); }
    .status.good { color: #d8ffed; background: rgba(69, 223, 154, .14); }
    .status.locked { color: #ffe5ec; background: rgba(238, 34, 56, .13); }
    .server-list { display: grid; gap: .9rem; }
    .server-card { padding: 1rem; }
    .server-head { display: flex; gap: 1rem; align-items: flex-start; justify-content: space-between; }
    .pill-row { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .65rem; }
    .pill { padding: .32rem .55rem; border-radius: 999px; background: var(--field); color: var(--muted); font-size: .78rem; border: 1px solid var(--line); }
    .pill.good { color: #dbfff0; background: rgba(69,223,154,.14); }
    .pill.warn { color: #fff1ce; background: rgba(245,200,92,.14); }
    .pill.bad { color: #ffe1e5; background: rgba(238,34,56,.14); }
    .server-body { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem; margin-top: 1rem; }
    .mini-panel { background: rgba(5, 9, 18, .25); border: 1px solid var(--line); border-radius: 1rem; padding: .85rem; min-width: 0; }
    .list { list-style: none; display: grid; gap: .45rem; margin: .65rem 0 0; padding: 0; }
    .row { display: flex; justify-content: space-between; gap: 1rem; color: var(--muted); font-size: .9rem; }
    .row strong { color: var(--text); overflow: hidden; text-overflow: ellipsis; }
    .empty { color: var(--dim); font-style: italic; }
    .zone-card { padding: 1rem; }
    .zone-layout { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(18rem, .85fr); gap: 1rem; margin-top: .9rem; }
    .field { display: grid; gap: .35rem; margin-bottom: .85rem; }
    label { color: var(--muted); font-size: .88rem; }
    .help { display: inline-flex; justify-content: center; align-items: center; width: 1rem; height: 1rem; border-radius: 50%; border: 1px solid var(--muted); color: var(--muted); font-size: .7rem; }
    input, select, textarea {
      width: 100%;
      border: 1px solid rgba(180, 204, 255, .09);
      border-radius: .75rem;
      background: var(--field);
      color: var(--text);
      padding: .8rem .9rem;
      outline: none;
    }
    textarea { min-height: 8rem; resize: vertical; }
    input[type="color"] { height: 2.75rem; padding: .2rem; background: var(--field); }
    .checks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem .7rem; }
    .check { display: flex; align-items: flex-start; gap: .5rem; color: var(--muted); font-size: .86rem; }
    .check input { width: 1rem; height: 1rem; accent-color: var(--brand); margin-top: .15rem; }
    .chips { display: flex; flex-wrap: wrap; gap: .42rem; padding: .65rem; background: var(--field); border-radius: .8rem; border: 1px solid rgba(180, 204, 255, .09); }
    .chip { background: var(--field-2); color: var(--muted); padding: .38rem .52rem; border-radius: .45rem; font-size: .82rem; }
    .chip:after { content: " ×"; color: var(--text); }
    .actions { display: flex; flex-wrap: wrap; gap: .7rem; margin-top: .9rem; }
    .btn { border: 0; border-radius: .85rem; color: var(--text); font-weight: 900; padding: .78rem 1rem; background: var(--field-2); }
    .btn.primary { background: linear-gradient(135deg, var(--brand), #482ee8); box-shadow: 0 .65rem 1.4rem rgba(113,84,255,.28); }
    .btn.ghost { border: 1px solid var(--line); }
    .map-preview { min-height: 100%; border-radius: 1rem; padding: 1rem; background: linear-gradient(135deg, rgba(68,215,255,.1), rgba(113,84,255,.1)), var(--field); border: 1px solid var(--line); position: relative; overflow: hidden; }
    .map-preview:before { content: ""; position: absolute; inset: 1rem; opacity: .18; background-image: linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px); background-size: 2rem 2rem; }
    .zone-dot { position: absolute; width: 8rem; height: 8rem; border: 2px solid var(--red); background: rgba(238,34,56,.12); border-radius: 43% 57% 47% 53%; left: 31%; top: 35%; box-shadow: 0 0 2rem rgba(238,34,56,.18); }
    .map-preview strong, .map-preview span { position: relative; z-index: 1; display: block; }
    .map-preview span { color: var(--muted); margin-top: .35rem; }
    footer { max-width: 1480px; margin: 0 auto; padding: 0 clamp(1rem, 4vw, 2rem) 2rem; color: var(--muted); }
    code { background: rgba(255,255,255,.08); padding: .12rem .35rem; border-radius: .35rem; }
    @media (max-width: 1050px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { position: static; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .nav-title { grid-column: 1 / -1; }
      .stats, .server-body, .module-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .zone-layout { grid-template-columns: 1fr; }
    }
    @media (max-width: 640px) {
      .topbar { padding: .75rem .85rem; }
      .brand span { max-width: 12rem; }
      .shell { padding: .85rem .7rem 1.4rem; }
      .sidebar { display: none; }
      .stats, .server-body, .module-grid, .checks { grid-template-columns: 1fr; }
      .hero, .card, .server-card, .zone-card { border-radius: 1rem; }
      .server-head { display: grid; }
      .actions .btn { flex: 1 1 auto; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <img src="/brand-image" alt="Wandering Bot logo">
      <div><strong>Wandering Bot</strong><span>DayZ community control deck</span></div>
    </div>
    <div class="hamburger" aria-hidden="true"><i></i><i></i><i></i></div>
  </header>

  <div class="shell">
    <aside class="sidebar" aria-label="Dashboard modules">
      <div class="nav-title">Control modules</div>
      <a class="nav-link active" href="#overview"><strong>Overview</strong><span>Live</span></a>
      <a class="nav-link" href="#radar"><strong>Radar Zones</strong><span class="badge">{{ summary.radar_zones }}</span></a>
      <a class="nav-link" href="#economy"><strong>Economy & Shop</strong><span>{{ summary.shop_items }}</span></a>
      <a class="nav-link" href="#factions"><strong>Factions</strong><span>{{ summary.factions }}</span></a>
      <a class="nav-link" href="#embeds"><strong>Embeds</strong><span>Builder</span></a>
      <a class="nav-link" href="#access"><strong>Access</strong><span>{{ summary.dashboard_enabled }}/{{ summary.guilds }}</span></a>
    </aside>

    <main>
      <section class="hero" id="overview">
        <div class="eyebrow">Private alpha dashboard</div>
        <h1>Server tools, radar zones, factions and economy in one place.</h1>
        <p class="sub">A Wandering Bot styled control surface inspired by DayZ admin panels, not a copy of them. This version keeps secrets filtered, shows live bot data, and lays out the management modules that can be connected to Discord OAuth/subscription gates next.</p>
      </section>

      <section class="stats" aria-label="Summary">
        <div class="stat-card"><span>Servers</span><strong>{{ summary.guilds }}</strong></div>
        <div class="stat-card"><span>Online survivors</span><strong>{{ summary.online }}</strong></div>
        <div class="stat-card"><span>Tracked players</span><strong>{{ summary.players }}</strong></div>
        <div class="stat-card"><span>Total kills</span><strong>{{ summary.kills }}</strong></div>
      </section>

      <section class="module-grid" aria-label="Feature modules">
        <article class="card" id="economy"><h3>💰 Economy & shop</h3><p>Review wallets, shop inventory, delivery queues and wages from the same command data the bot uses.</p><span class="status good">{{ summary.shop_items }} shop items detected</span></article>
        <article class="card" id="factions"><h3>🏴 Factions</h3><p>Faction rosters, leaders, role routing and alert channels are grouped for owner/staff management.</p><span class="status good">{{ summary.factions }} factions loaded</span></article>
        <article class="card" id="embeds"><h3>🧩 Embed studio</h3><p>Draft announcement, rules, restart and update embeds with preview/send controls ready for OAuth protection.</p><span class="status">Preview scaffold</span></article>
        <article class="card" id="access"><h3>🔐 Dashboard access</h3><p>Each guild can be toggled for dashboard access, tier and feature locks before you turn subscriptions on.</p><span class="status {{ 'good' if summary.dashboard_enabled else 'locked' }}">{{ summary.dashboard_enabled }} enabled</span></article>
        <article class="card"><h3>🏆 Leaderboards</h3><p>Top kills, deaths and build activity remain available at server level without exposing private credentials.</p><span class="status good">Live stats</span></article>
        <article class="card"><h3>📡 Feeds</h3><p>Online, heatmap, PVE, economy and faction channels are surfaced per server for setup checks.</p><span class="status">Channel audit</span></article>
      </section>

      <section class="zone-card" id="radar">
        <h2>Polygon radar zone builder</h2>
        <p class="sub">Mobile-first radar-zone controls using Wandering Bot colours and branding. Until Discord OAuth write protection is added, this screen is a safe management scaffold backed by the read-only API.</p>
        <div class="zone-layout">
          <form>
            <div class="field"><label>Server <span class="help">?</span></label><select><option>{{ servers[0].guild_name if servers else 'No server configured' }}</option></select></div>
            <div class="field"><label>Zone name <span class="help">?</span></label><input value="{{ servers[0].example_zone.name if servers and servers[0].example_zone else 'Prison Island Ping' }}"></div>
            <div class="field"><label>Alert channel <span class="help">?</span></label><select><option>{{ servers[0].channels[0].key if servers and servers[0].channels else 'Choose channel' }}</option></select></div>
            <div class="field"><label>Zone colour <span class="help">?</span></label><input type="color" value="{{ servers[0].example_zone.colour if servers and servers[0].example_zone else '#ee2238' }}"></div>
            <div class="field"><label>Allowed / ignored events <span class="help">?</span></label>
              <div class="checks">
                {% for event in radar_events %}
                  <label class="check"><input type="checkbox" {% if event.checked %}checked{% endif %}> {{ event.label }}</label>
                {% endfor %}
              </div>
            </div>
            <div class="field"><label>Allowlist management users <span class="help">?</span></label><div class="chips"><span class="chip">Edward80</span><span class="chip">Zz P03ZY zZ</span><span class="chip">MissRedinKy</span></div></div>
            <div class="field"><label>Polygon coordinates <span class="help">?</span></label><div class="chips">{% for coord in polygon_coords %}<span class="chip">{{ coord }}</span>{% endfor %}</div></div>
            <div class="actions"><button class="btn ghost" type="button">Copy coordinates</button><button class="btn primary" type="button">Update zone</button></div>
          </form>
          <div class="map-preview"><strong>Radar preview</strong><span>Map: {{ servers[0].map|upper if servers else 'CHERNARUS' }}</span><span>Detection payout, ping roles, allowlists and active toggles will be wired after auth.</span><div class="zone-dot"></div></div>
        </div>
      </section>

      <section class="server-list" aria-label="Servers">
      {% if servers %}
        {% for server in servers %}
        <article class="server-card">
          <div class="server-head">
            <div>
              <h2>{{ server.guild_name }}</h2>
              <div class="pill-row">
                <span class="pill">Guild {{ server.guild_id }}</span>
                <span class="pill {{ 'good' if server.active else 'warn' }}">{{ 'active' if server.active else 'inactive' }}</span>
                <span class="pill {{ 'good' if server.dashboard_access.enabled else 'bad' }}">Dashboard {{ 'enabled' if server.dashboard_access.enabled else 'locked' }}</span>
                <span class="pill {{ 'good' if server.nitrado_configured else 'bad' }}">Nitrado {{ 'configured' if server.nitrado_configured else 'missing' }}</span>
                <span class="pill">{{ server.map|upper }} / {{ server.heatmap_mode|upper }}</span>
              </div>
            </div>
            <span class="pill">Updated {{ generated_at }}</span>
          </div>
          <div class="server-body">
            <section class="mini-panel"><h3>🟢 Online</h3>{% if server.online %}<ul class="list">{% for player in server.online[:5] %}<li class="row"><strong>{{ player }}</strong><span>online</span></li>{% endfor %}</ul>{% else %}<p class="empty">No survivors online.</p>{% endif %}</section>
            <section class="mini-panel"><h3>🏆 Leaders</h3>{% if server.leaders %}<ul class="list">{% for leader in server.leaders[:5] %}<li class="row"><strong>{{ leader.name }}</strong><span>{{ leader.kills }} kills</span></li>{% endfor %}</ul>{% else %}<p class="empty">No player stats yet.</p>{% endif %}</section>
            <section class="mini-panel"><h3>📡 Channels</h3>{% if server.channels %}<ul class="list">{% for channel in server.channels[:5] %}<li class="row"><strong>{{ channel.key }}</strong><span>{{ channel.id }}</span></li>{% endfor %}</ul>{% else %}<p class="empty">No channels saved.</p>{% endif %}</section>
            <section class="mini-panel"><h3>🧾 Totals</h3><ul class="list"><li class="row"><strong>Kills</strong><span>{{ server.totals.kills }}</span></li><li class="row"><strong>Deaths</strong><span>{{ server.totals.deaths }}</span></li><li class="row"><strong>Builds</strong><span>{{ server.totals.builds }}</span></li><li class="row"><strong>Radar zones</strong><span>{{ server.radar_zones|length }}</span></li></ul></section>
          </div>
        </article>
        {% endfor %}
      {% else %}
        <section class="card"><h2>No guilds configured yet</h2><p class="empty">Run the bot setup commands in Discord, then refresh this page.</p></section>
      {% endif %}
      </section>
    </main>
  </div>

  <footer>
    JSON API: <a href="/api/summary"><code>/api/summary</code></a>. Health check: <a href="/healthz"><code>/healthz</code></a>. Secrets are filtered before rendering.
  </footer>
</body>
</html>
"""


SECRET_KEYS = {
    "nitrado_token",
    "ftp_password",
    "ftp_user",
    "ftp_host",
    "nitrado_user",
    "service_id",
}

RADAR_EVENTS = [
    {"label": "Temporary ban", "checked": False},
    {"label": "Ban on login", "checked": False},
    {"label": "Ban on build", "checked": False},
    {"label": "Ban on place", "checked": False},
    {"label": "Ban on kill", "checked": False},
    {"label": "Ban on hit", "checked": False},
    {"label": "Ping on detection", "checked": True},
    {"label": "Verbose mode", "checked": True},
    {"label": "Kill zone", "checked": False},
    {"label": "Hit zone", "checked": False},
    {"label": "Location", "checked": False},
    {"label": "Active", "checked": True},
]

POLYGON_COORDS = [
    "3393.75 / 1911.25",
    "3315.0 / 1941.25",
    "2808.75 / 1858.75",
    "2715.0 / 1813.75",
    "2643.75 / 1750.0",
    "2557.5 / 1652.5",
    "2313.75 / 1952.5",
    "2250.0 / 1735.0",
    "2355.0 / 1480.0",
    "2403.75 / 1131.25",
    "2883.75 / 1015.0",
    "3345.0 / 1225.0",
    "3198.75 / 1532.5",
]


def data_path(*parts):
    return os.path.join(DATA_ROOT, *parts)


def read_json_file(filename, default):
    path = data_path(filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if data is not None else default
    except (OSError, json.JSONDecodeError):
        return default


def normalize_guild_id(value):
    return str(value or "").strip()


def safe_int(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def public_channels(channels):
    if not isinstance(channels, dict):
        return []
    return [
        {"key": str(key), "id": str(value)}
        for key, value in sorted(channels.items())
        if value
    ]


def guild_players(player_stats, guild_id):
    players = []
    for name, stats in (player_stats or {}).items():
        if not isinstance(stats, dict):
            continue
        stat_guild_id = normalize_guild_id(stats.get("guild_id"))
        if stat_guild_id and stat_guild_id != guild_id:
            continue
        players.append(
            {
                "name": str(name),
                "kills": safe_int(stats.get("kills")),
                "deaths": safe_int(stats.get("deaths")),
                "builds": safe_int(stats.get("builds")),
            }
        )
    return players


def sanitize_config(config):
    if not isinstance(config, dict):
        return {}
    return {
        key: value
        for key, value in config.items()
        if key not in SECRET_KEYS and "token" not in key.lower() and "password" not in key.lower()
    }


def normalize_dashboard_access(config):
    access = config.get("dashboard") if isinstance(config, dict) else {}
    if not isinstance(access, dict):
        access = {}
    features = access.get("features") if isinstance(access.get("features"), dict) else {}
    return {
        "enabled": bool(access.get("enabled", False)),
        "tier": str(access.get("tier") or "none"),
        "trial_until": access.get("trial_until"),
        "allowed_role_ids": [str(item) for item in access.get("allowed_role_ids", []) if item],
        "allowed_user_ids": [str(item) for item in access.get("allowed_user_ids", []) if item],
        "features": {
            "leaderboards": bool(features.get("leaderboards", True)),
            "economy": bool(features.get("economy", False)),
            "factions": bool(features.get("factions", False)),
            "radar_zones": bool(features.get("radar_zones", False)),
            "embeds": bool(features.get("embeds", False)),
        },
    }


def normalize_radar_zones(config):
    raw_zones = config.get("radar_zones") or config.get("zones") or []
    if isinstance(raw_zones, dict):
        zone_items = raw_zones.items()
    elif isinstance(raw_zones, list):
        zone_items = enumerate(raw_zones)
    else:
        zone_items = []

    zones = []
    for fallback_name, zone in zone_items:
        if not isinstance(zone, dict):
            continue
        coords = zone.get("polygon") or zone.get("coordinates") or zone.get("coords") or []
        zones.append(
            {
                "name": str(zone.get("name") or fallback_name or "Unnamed zone"),
                "channel_id": str(zone.get("channel_id") or zone.get("channel") or ""),
                "colour": str(zone.get("colour") or zone.get("color") or "#ee2238"),
                "active": bool(zone.get("active", True)),
                "coordinates": coords if isinstance(coords, list) else [],
            }
        )
    return zones


def count_records(data):
    if isinstance(data, dict):
        return len(data)
    if isinstance(data, list):
        return len(data)
    return 0


def load_dashboard_state():
    runtime_state = CUSTOM_STATE_PROVIDER() if CUSTOM_STATE_PROVIDER else {}
    if not isinstance(runtime_state, dict):
        runtime_state = {}

    guild_configs = runtime_state.get("guild_configs") or read_json_file("guild_configs.json", {})
    player_stats = runtime_state.get("player_stats") or read_json_file("player_stats.json", {})
    online_players = runtime_state.get("online_players") or read_json_file("online_players.json", {})
    economy = runtime_state.get("economy") or read_json_file("economy.json", {})
    factions = runtime_state.get("factions") or read_json_file("factions.json", {})
    shop = runtime_state.get("shop") or read_json_file("shop.json", {})
    wallets = runtime_state.get("wallets") or read_json_file("wallets.json", {})
    delivery_queue = runtime_state.get("delivery_queue") or read_json_file("delivery_queue.json", [])
    if not isinstance(online_players, dict):
        online_players = {}

    servers = []
    total_online = 0
    total_kills = 0
    total_players = 0
    dashboard_enabled = 0
    radar_zone_count = 0

    for guild_id, config in sorted((guild_configs or {}).items(), key=lambda item: str(item[1].get("guild_name", item[0])).lower()):
        if not isinstance(config, dict):
            continue

        guild_id = normalize_guild_id(guild_id)
        players = guild_players(player_stats, guild_id)
        players.sort(key=lambda player: (-player["kills"], player["deaths"], player["name"].lower()))
        online = sorted(str(player) for player in online_players.get(guild_id, []) if player)
        dashboard_access = normalize_dashboard_access(config)
        radar_zones = normalize_radar_zones(config)
        example_zone = radar_zones[0] if radar_zones else None

        totals = {
            "kills": sum(player["kills"] for player in players),
            "deaths": sum(player["deaths"] for player in players),
            "builds": sum(player["builds"] for player in players),
            "players": len(players),
        }
        total_online += len(online)
        total_kills += totals["kills"]
        total_players += totals["players"]
        dashboard_enabled += 1 if dashboard_access["enabled"] else 0
        radar_zone_count += len(radar_zones)

        servers.append(
            {
                "guild_id": guild_id,
                "guild_name": str(config.get("guild_name") or f"Guild {guild_id}"),
                "active": not bool(config.get("bot_removed")),
                "nitrado_configured": bool(config.get("nitrado_token") and config.get("service_id")),
                "map": str(config.get("server_map") or config.get("map") or "chernarus"),
                "heatmap_mode": str(config.get("heatmap_mode") or "all"),
                "online": online,
                "online_count": len(online),
                "leaders": players[:5],
                "channels": public_channels(config.get("channels", {})),
                "totals": totals,
                "dashboard_access": dashboard_access,
                "radar_zones": radar_zones,
                "example_zone": example_zone,
                "config": sanitize_config(config),
            }
        )

    return {
        "summary": {
            "guilds": len(servers),
            "online": total_online,
            "players": total_players,
            "kills": total_kills,
            "dashboard_enabled": dashboard_enabled,
            "radar_zones": radar_zone_count,
            "shop_items": count_records(shop) or count_records(economy.get("shop") if isinstance(economy, dict) else {}),
            "wallets": count_records(wallets),
            "delivery_queue": count_records(delivery_queue),
            "factions": count_records(factions),
        },
        "servers": servers,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


@APP.get("/healthz")
def healthz():
    return jsonify({"ok": True, "generated_at": datetime.now(UTC).isoformat()})


@APP.get("/api/summary")
def api_summary():
    return jsonify(load_dashboard_state())


@APP.get("/brand-image")
def brand_image():
    if os.path.exists(BOT_IMAGE_FILE):
        return send_file(BOT_IMAGE_FILE)
    return ("", 404)


@APP.get("/")
def index():
    state = load_dashboard_state()
    return render_template_string(
        PAGE_TEMPLATE,
        refresh_seconds=DASHBOARD_REFRESH_SECONDS,
        summary=state["summary"],
        servers=state["servers"],
        generated_at=state["generated_at"],
        radar_events=RADAR_EVENTS,
        polygon_coords=POLYGON_COORDS,
    )


def configure_dashboard_state_provider(provider):
    """Let bot.py provide live in-memory state while the dashboard is embedded."""
    global CUSTOM_STATE_PROVIDER
    CUSTOM_STATE_PROVIDER = provider


def run_dashboard_server():
    APP.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, use_reloader=False)


def start_dashboard_server():
    """Start the dashboard in a daemon thread beside the Discord bot."""
    thread = Thread(target=run_dashboard_server, name="wandering-dashboard", daemon=True)
    thread.start()
    print(f"[DASHBOARD] Web dashboard listening on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    return thread


if __name__ == "__main__":
    run_dashboard_server()
