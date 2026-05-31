"""Flask dashboard for Wandering Bot.

The dashboard reads and writes the same JSON files used by ``bot.py``. It is
deliberately conservative: secrets are never rendered, and admin routes mutate
local JSON state only so the Discord bot can pick up changes on its next read.
"""

from __future__ import annotations

import json
import os
import secrets
import hashlib
from datetime import UTC, datetime
from threading import Thread
from typing import Any

from flask import Flask, jsonify, make_response, redirect, render_template_string, request, send_file


DATA_ROOT = (
    os.getenv("WANDERING_DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or os.getenv("RAILWAY_VOLUME_PATH")
    or "."
)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
BOT_IMAGE_FILE = os.getenv("WANDERING_BOT_IMAGE_FILE", os.path.join(APP_ROOT, "wanderingbot.png"))
DASHBOARD_HOST = os.getenv("WANDERING_DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("PORT") or os.getenv("WANDERING_DASHBOARD_PORT", "8080"))
DASHBOARD_REFRESH_SECONDS = int(os.getenv("WANDERING_DASHBOARD_REFRESH_SECONDS", "45"))
ADMIN_TOKEN = os.getenv("WANDERING_DASHBOARD_ADMIN_TOKEN", "")
DASHBOARD_COOKIE_SECRET = os.getenv("WANDERING_DASHBOARD_COOKIE_SECRET") or ADMIN_TOKEN or secrets.token_urlsafe(32)
DASHBOARD_PUBLIC_URL = os.getenv("WANDERING_DASHBOARD_PUBLIC_URL", "https://dayzwanderingbot.com")

APP = Flask(__name__)
APP.secret_key = DASHBOARD_COOKIE_SECRET
CUSTOM_STATE_PROVIDER = None

SECRET_KEYS = {
    "token",
    "password",
    "secret",
    "ftp_password",
    "ftp_user",
    "ftp_host",
    "nitrado_token",
    "nitrado_user",
    "service_id",
}

FILES = {
    "guild_configs": "guild_configs.json",
    "player_stats": "player_stats.json",
    "online_players": "online_players.json",
    "shop": "shop.json",
    "wallets": "wallets.json",
    "factions": "factions.json",
    "wages": "wages.json",
    "delivery_queue": "delivery_queue.json",
    "dashboard_admin": "dashboard_admin.json",
}

LOGIN_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wandering Bot Dashboard Login</title>
  <style>
    :root { color-scheme: dark; --bg: #050806; --panel: #111710; --line: rgba(209,203,145,.24); --text: #f3ecd9; --muted: #c4bda7; --gold: #d5b45f; --olive: #8d963e; --red: #ed3853; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: linear-gradient(180deg, #10150d, var(--bg)); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width: min(94vw, 30rem); border: 1px solid var(--line); border-radius: .5rem; background: var(--panel); padding: 1.25rem; box-shadow: 0 1rem 2.5rem rgba(0,0,0,.35); }
    img { width: 4rem; height: 4rem; border-radius: .75rem; object-fit: cover; }
    h1 { margin: .8rem 0 .35rem; text-transform: uppercase; letter-spacing: 0; }
    p { color: var(--muted); line-height: 1.5; }
    form { display: grid; gap: .75rem; margin-top: 1rem; }
    label { display: grid; gap: .25rem; color: var(--muted); font-size: .9rem; }
    input { width: 100%; border: 1px solid var(--line); border-radius: .45rem; background: #080d09; color: var(--text); padding: .75rem .8rem; }
    button { border: 0; border-radius: .45rem; background: var(--olive); color: #070a06; padding: .8rem; font-weight: 900; cursor: pointer; }
    .error { color: #ffd8df; background: rgba(237,56,83,.16); border: 1px solid rgba(237,56,83,.35); padding: .65rem; border-radius: .45rem; }
    code { color: var(--gold); }
  </style>
</head>
<body>
  <main>
    <img src="/brand-image" alt="Wandering Bot logo">
    <h1>Wandering Bot</h1>
    <p>Use the private dashboard ID and password created during Discord <code>/setup</code>. Each login opens only that server's dashboard.</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="post" action="/login">
      <label>Dashboard ID <input name="dashboard_id" autocomplete="username" required></label>
      <label>Password <input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit">Open Dashboard</button>
    </form>
  </main>
</body>
</html>
"""

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wandering Bot Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050806;
      --panel: #111710;
      --panel-2: #192014;
      --panel-3: #0b100b;
      --line: rgba(209, 203, 145, .24);
      --text: #f3ecd9;
      --muted: #c4bda7;
      --dim: #8f8a6e;
      --olive: #8d963e;
      --gold: #d5b45f;
      --red: #ed3853;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background: linear-gradient(180deg, #10150d 0%, var(--bg) 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    a { color: var(--gold); text-decoration: none; }
    h1, h2, h3, p { margin-top: 0; }
    header {
      position: sticky;
      top: 0;
      z-index: 3;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: .85rem clamp(1rem, 4vw, 2rem);
      background: rgba(5, 8, 6, .92);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(16px);
    }
    .brand { display: flex; align-items: center; gap: .75rem; min-width: 0; }
    .brand img { width: 3rem; height: 3rem; border-radius: .75rem; object-fit: cover; }
    .brand strong { display: block; text-transform: uppercase; letter-spacing: .08em; }
    .brand span, .muted { color: var(--muted); }
    nav { display: flex; flex-wrap: wrap; gap: .45rem; }
    nav a, button, .button, .tab-link {
      border: 1px solid var(--line);
      border-radius: .5rem;
      background: var(--panel-2);
      color: var(--text);
      padding: .6rem .8rem;
      font-weight: 800;
      cursor: pointer;
    }
    main { max-width: 1440px; margin: 0 auto; padding: 1.1rem clamp(1rem, 4vw, 2rem) 2rem; display: grid; gap: 1rem; }
    .hero, .card, .wide, .section-panel {
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(243, 236, 217, .05), rgba(243, 236, 217, .015)), var(--panel);
      border-radius: .5rem;
      box-shadow: 0 1rem 2.5rem rgba(0, 0, 0, .3);
    }
    .hero { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; align-items: center; padding: clamp(1rem, 4vw, 2rem); }
    h1 { margin: .2rem 0 .5rem; font-size: clamp(2rem, 5vw, 4.25rem); line-height: .95; text-transform: uppercase; letter-spacing: 0; }
    .hero img { width: min(11rem, 35vw); aspect-ratio: 1; object-fit: cover; border-radius: 50%; border: 2px solid var(--gold); }
    .stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .75rem; }
    .stat, .card { padding: 1rem; }
    .stat { border: 1px solid var(--line); border-radius: .5rem; background: var(--panel-3); }
    .stat span { display: block; color: var(--muted); font-size: .8rem; text-transform: uppercase; }
    .stat strong { display: block; color: var(--gold); font-size: 1.8rem; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .85rem; }
    .servers { display: grid; gap: .85rem; }
    .server-head { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
    .pills { display: flex; flex-wrap: wrap; gap: .4rem; }
    .pill { border: 1px solid var(--line); border-radius: 999px; padding: .28rem .55rem; color: var(--muted); background: #0a0f0b; font-size: .8rem; }
    .ok { color: #eef7c6; background: rgba(141, 150, 62, .22); }
    .bad { color: #ffd8df; background: rgba(237, 56, 83, .16); }
    .columns { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; margin-top: .85rem; }
    ul { margin: .4rem 0 0; padding: 0; list-style: none; display: grid; gap: .35rem; }
    li { display: flex; justify-content: space-between; gap: .75rem; color: var(--muted); }
    code { background: #0a0f0b; border: 1px solid var(--line); border-radius: .35rem; padding: .1rem .3rem; }
    form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
    label { display: grid; gap: .25rem; color: var(--muted); font-size: .9rem; }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: .45rem;
      background: #080d09;
      color: var(--text);
      padding: .65rem .75rem;
    }
    textarea { min-height: 7rem; resize: vertical; }
    input[readonly] { color: var(--gold); background: rgba(213, 180, 95, .08); cursor: default; }
    .full { grid-column: 1 / -1; }
    .route-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .4rem; }
    .route-list code { display: block; overflow-wrap: anywhere; }
    .panel-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; align-items: start; }
    .admin-panel { border: 1px solid var(--line); border-radius: .5rem; padding: 1rem; background: var(--panel-3); }
    .admin-panel form { margin-top: .75rem; }
    .result { min-height: 1.25rem; }
    .owner-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
    .owner-tile { border: 1px solid var(--line); border-radius: .5rem; padding: .85rem; background: var(--panel-3); }
    .owner-tile strong { display: block; color: var(--gold); font-size: 1.35rem; }
    .table { width: 100%; border-collapse: collapse; margin-top: .75rem; }
    .table th, .table td { border-bottom: 1px solid var(--line); padding: .55rem; text-align: left; color: var(--muted); }
    .table th { color: var(--text); font-size: .8rem; text-transform: uppercase; }
    .section-nav { position: sticky; top: 5rem; z-index: 2; display: flex; flex-wrap: wrap; gap: .5rem; padding: .65rem; border: 1px solid var(--line); border-radius: .5rem; background: rgba(5, 8, 6, .9); backdrop-filter: blur(14px); }
    .section-panel { padding: 1rem; scroll-margin-top: 8rem; }
    .section-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; flex-wrap: wrap; margin-bottom: .85rem; }
    .server-lock { display: grid; grid-template-columns: 1fr; gap: .35rem; margin-bottom: .75rem; }
    .server-lock span { color: var(--muted); font-size: .85rem; }
    .leaderboard { display: grid; gap: .45rem; margin-top: .75rem; }
    .leader-row { display: grid; grid-template-columns: 3rem minmax(0, 1fr) repeat(3, minmax(4rem, auto)); gap: .55rem; align-items: center; border: 1px solid var(--line); border-radius: .5rem; padding: .65rem; background: #070b08; }
    .rank { color: var(--gold); font-weight: 900; font-size: 1.15rem; }
    .leader-name { color: var(--text); font-weight: 900; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .metric { color: var(--muted); text-align: right; }
    .metric strong { color: var(--text); display: block; }
    .tool-note { color: var(--muted); font-size: .9rem; line-height: 1.45; }
    .option-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
    .option-card { border: 1px solid var(--line); border-radius: .5rem; padding: .8rem; background: #070b08; }
    .option-card strong { display: block; color: var(--gold); margin-bottom: .25rem; }
    .check-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .5rem; }
    .check { display: flex; align-items: center; gap: .5rem; color: var(--muted); border: 1px solid var(--line); border-radius: .45rem; padding: .55rem; background: #070b08; }
    .check input { width: auto; accent-color: var(--olive); }
    .hidden-field { display: none; }
    @media (max-width: 980px) {
      .hero, .grid, .columns, .stats, form, .route-list, .panel-grid, .owner-grid, .option-grid, .leader-row, .check-grid { grid-template-columns: 1fr; }
      .metric { text-align: left; }
      nav { display: none; }
    }
  </style>
</head>
<body>
  {% set server = servers[0] if servers else none %}
  <header>
    <div class="brand">
      <img src="/brand-image" alt="Wandering Bot logo">
      <div><strong>Wandering Bot</strong><span>{{ view_title }}</span></div>
    </div>
    <nav>
      <a href="/">Overview</a>
      <a href="/admin">Admin</a>
      {% if auth.kind == "owner" %}<a href="/owner">Owner</a>{% endif %}
      <a href="/api/summary">API</a>
      <a href="/logout">Logout</a>
    </nav>
  </header>
  <main>
    <section class="hero">
      <div>
        <p class="muted">{{ generated_at }}</p>
        <h1>{{ view_title }}</h1>
        <p class="muted">Live readout for {{ auth.label }}. Server dashboards are scoped by private ID/password and cannot access another guild.</p>
        {% if server %}
        <div class="pills">
          <span class="pill ok">{{ server.guild_name }}</span>
          <span class="pill">{{ server.map|upper }}</span>
          <span class="pill">{{ server.channels|length }} channels</span>
        </div>
        {% endif %}
      </div>
      <img src="/brand-image" alt="Wandering Bot mark">
    </section>

    <section class="stats">
      <div class="stat"><span>Server</span><strong>{{ server.map|upper if server else summary.guilds }}</strong></div>
      <div class="stat"><span>Online</span><strong>{{ summary.online }}</strong></div>
      <div class="stat"><span>Players</span><strong>{{ summary.players }}</strong></div>
      <div class="stat"><span>Shop</span><strong>{{ summary.shop_items }}</strong></div>
      <div class="stat"><span>Factions</span><strong>{{ summary.factions }}</strong></div>
    </section>

    <section class="section-nav" aria-label="Dashboard sections">
      <a class="tab-link" href="#leaderboards">Leaderboards</a>
      <a class="tab-link" href="#automations">Auto Messages</a>
      <a class="tab-link" href="#factions-radar">Factions & Radar</a>
      <a class="tab-link" href="#economy">Economy</a>
      <a class="tab-link" href="#access">Access</a>
    </section>

    <section class="section-panel" id="leaderboards">
      <div class="section-head">
        <div>
          <h2>{{ server.guild_name if server else 'Server' }} Leaderboard</h2>
          <p class="tool-note">Styled like the bot leaderboard: rank, survivor, kills, deaths, and builds.</p>
        </div>
        <span class="pill">{{ server.map|upper if server else 'NO SERVER' }}</span>
      </div>
      <div class="leaderboard">
        {% for leader in (server.leaders[:10] if server else []) %}
        <div class="leader-row">
          <div class="rank">#{{ loop.index }}</div>
          <div class="leader-name">{{ leader.name }}</div>
          <div class="metric"><strong>{{ leader.kills }}</strong>Kills</div>
          <div class="metric"><strong>{{ leader.deaths }}</strong>Deaths</div>
          <div class="metric"><strong>{{ leader.builds }}</strong>Builds</div>
        </div>
        {% else %}
        <p class="muted">No player stats have been recorded for this server yet.</p>
        {% endfor %}
      </div>
    </section>

    {% if mode in ["admin", "owner"] %}
    <section class="section-panel" id="automations">
      <div class="section-head">
        <div>
          <h2>Auto Messages & Embeds</h2>
          <p class="tool-note">Create messages the bot can use for rules, restarts, welcomes, events, shop notices, and staff announcements.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Auto Message</h3>
          <form class="admin-form" data-route="/api/admin/embed-template">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Purpose
              <select name="name">
                <option value="server-rules">Server rules</option>
                <option value="restart-warning">Restart warning</option>
                <option value="event-announcement">Event announcement</option>
                <option value="shop-notice">Shop notice</option>
                <option value="staff-alert">Staff alert</option>
              </select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}">{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label>Title <input name="title" value="Server Rules"></label>
            <label>Colour <input name="colour" value="#8d963e"></label>
            <label class="full">Message <textarea name="body">Respect the server, no exploits, and keep it fair.</textarea></label>
            <div class="full"><button type="submit">Save Message</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Welcome Automation</h3>
          <form class="admin-form" data-route="/api/admin/welcome-automation">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>When should it send?
              <select name="name">
                <option value="new-survivor-welcome">New survivor joins Discord</option>
                <option value="first-time-seen">New gamertag appears in ADM</option>
                <option value="returning-player">Returning player reconnects</option>
              </select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}" {% if channel.key == 'welcome' %}selected{% endif %}>{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label class="full">Message <textarea name="message">Welcome survivor. Read the rules, link your gamer tag, and good luck out there.</textarea></label>
            <div class="full"><button type="submit">Save Welcome</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Reaction Roles</h3>
          <form class="admin-form" data-route="/api/admin/reaction-role-panel">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Panel type
              <select name="name">
                <option value="server-roles">Server roles</option>
                <option value="platform-roles">Platform roles</option>
                <option value="event-pings">Event pings</option>
                <option value="faction-alerts">Faction alert roles</option>
              </select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}">{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label class="full">Role lines <textarea name="roles">Verified | yes | 1234567890
Trader pings | coin | 1234567890
Event pings | bell | 1234567890</textarea></label>
            <div class="full"><button type="submit">Save Panel</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>

    <section class="section-panel" id="factions-radar">
      <div class="section-head">
        <div>
          <h2>Factions & Radar</h2>
          <p class="tool-note">Manage faction info, faction members, and the channels that should receive radar pings or faction alerts.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Faction</h3>
          <form class="admin-form" data-route="/api/admin/faction">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Faction name <input name="name" value="The Wanderers"></label>
            <label>Leader Discord ID <input name="leader_id" placeholder="Discord user id"></label>
            <label>Faction role ID <input name="role_id" placeholder="Discord role id"></label>
            <label>Alert channel
              <select name="alert_channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}" {% if channel.key == 'factions_chat' %}selected{% endif %}>{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label>Colour <input name="colour" value="#8d963e"></label>
            <div class="full"><button type="submit">Save Faction</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Faction Member</h3>
          <form class="admin-form" data-route="/api/admin/faction-member">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Faction <input name="name" value="The Wanderers"></label>
            <label>Member Discord ID <input name="member_id" placeholder="Discord user id"></label>
            <label>Action <select name="action"><option value="add">Add member</option><option value="remove">Remove member</option></select></label>
            <div class="full"><button type="submit">Update Member</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Radar Ping Routing</h3>
          <form class="admin-form" data-route="/api/admin/embed-template">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <input class="hidden-field" name="name" value="radar-routing-note">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Default radar channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}" {% if channel.key == 'radar' or channel.key == 'pvp_intel' %}selected{% endif %}>{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label>Ping reason <input name="title" value="Radar Ping"></label>
            <label class="full">Staff note <textarea name="body">Use this routing for radar pings, faction territory alerts, and suspicious movement reports.</textarea></label>
            <div class="full"><button type="submit">Save Radar Routing</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>

    <section class="section-panel" id="economy">
      <div class="section-head">
        <div>
          <h2>Economy</h2>
          <p class="tool-note">Control shop items, player wallet adjustments, and recurring wages without touching raw JSON.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Shop Item</h3>
          <form class="admin-form" data-route="/api/admin/shop-item">
            <label>Item name <input name="item_name" value="NailsBox"></label>
            <label>Price <input name="price" type="number" value="100"></label>
            <label>Category
              <select name="category">
                <option value="Building">Building</option>
                <option value="Weapons">Weapons</option>
                <option value="Medical">Medical</option>
                <option value="Vehicles">Vehicles</option>
                <option value="Food">Food</option>
                <option value="Tools">Tools</option>
              </select>
            </label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <div class="full"><button type="submit">Save Item</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Wage</h3>
          <form class="admin-form" data-route="/api/admin/wage">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Pay who?
              <select name="target_type"><option value="user">One player</option><option value="role">Discord role</option><option value="faction">Whole faction</option></select>
            </label>
            <label>Target ID or faction name <input name="target_id" placeholder="user id, role id, or faction"></label>
            <label>Amount <input name="amount" type="number" value="250"></label>
            <label>Cadence <select name="cadence"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></label>
            <label>Active <select name="active"><option value="true">On</option><option value="false">Off</option></select></label>
            <div class="full"><button type="submit">Save Wage</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Wallet Adjustment</h3>
          <form class="admin-form" data-route="/api/admin/wallet-adjustment">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Player Discord ID <input name="user_id" placeholder="Discord user id"></label>
            <label>Amount <input name="amount" type="number" value="100"></label>
            <label>Reason
              <select name="reason">
                <option value="admin reward">Admin reward</option>
                <option value="event prize">Event prize</option>
                <option value="refund">Refund</option>
                <option value="rule penalty">Rule penalty</option>
              </select>
            </label>
            <div class="full"><button type="submit">Adjust Wallet</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>

    <section class="section-panel" id="access">
      <div class="section-head">
        <div>
          <h2>Dashboard Access</h2>
          <p class="tool-note">Server identity is locked to the logged-in guild. Use Discord `/dashboardcredentials reset:true` to change the private password.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Feature Access</h3>
          <form class="admin-form" data-route="/api/admin/guild-access">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Tier <select name="tier"><option value="owner">owner</option><option value="premium">premium</option><option value="trial">trial</option><option value="none">none</option></select></label>
            <label>Allowed role IDs <input name="allowed_role_ids" placeholder="optional Discord role IDs"></label>
            <div class="full">
              <span class="muted">Enabled modules</span>
              <div class="check-grid">
                <label class="check"><input type="checkbox" name="feature_leaderboards" checked> Leaderboards</label>
                <label class="check"><input type="checkbox" name="feature_economy" checked> Economy</label>
                <label class="check"><input type="checkbox" name="feature_factions" checked> Factions</label>
                <label class="check"><input type="checkbox" name="feature_embeds" checked> Auto messages</label>
                <label class="check"><input type="checkbox" name="feature_safe_zones" checked> Radar zones</label>
              </div>
            </div>
            <div class="full"><button type="submit">Save Access</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode == "owner" %}
    <section class="wide card">
      <h2>Owner Console</h2>
      <div class="owner-grid">
        <div class="owner-tile"><span class="muted">Active guilds</span><strong>{{ summary.guilds }}</strong></div>
        <div class="owner-tile"><span class="muted">Dashboard enabled</span><strong>{{ summary.dashboard_enabled }}</strong></div>
        <div class="owner-tile"><span class="muted">Admin routes</span><strong>{{ admin_routes|length }}</strong></div>
      </div>
      <table class="table">
        <thead><tr><th>Server</th><th>Server ID</th><th>Map</th><th>Channels</th><th>Access</th></tr></thead>
        <tbody>
          {% for server in servers %}
          <tr><td>{{ server.guild_name }}</td><td>{{ server.guild_id }}</td><td>{{ server.map }}</td><td>{{ server.channels|length }}</td><td>{{ 'enabled' if server.dashboard_access.enabled else 'locked' }}</td></tr>
          {% endfor %}
        </tbody>
      </table>
      <h3>Routes</h3>
      <div class="route-list">
        {% for route in all_routes %}<code>{{ route }}</code>{% endfor %}
      </div>
    </section>
    {% endif %}

    <section class="grid">
      <article class="card"><h3>Economy</h3><p class="muted">{{ summary.wallets }} wallets, {{ summary.delivery_queue }} queued deliveries and {{ summary.wages }} active wages.</p></article>
      <article class="card"><h3>Automations</h3><p class="muted">{{ summary.embed_templates }} message templates, {{ summary.welcome_automations }} welcomes and {{ summary.reaction_role_panels }} role panels.</p></article>
      <article class="card"><h3>Access</h3><p class="muted">{{ 'This dashboard is enabled.' if summary.dashboard_enabled else 'This dashboard is locked.' }}</p></article>
    </section>

    <section class="servers">
      {% for server in servers %}
      <article class="card">
        <div class="server-head">
          <div>
            <h2>{{ server.guild_name }}</h2>
            <div class="pills">
              <span class="pill">Server ID {{ server.guild_id }}</span>
              <span class="pill {{ 'ok' if server.active else 'bad' }}">{{ 'active' if server.active else 'inactive' }}</span>
              <span class="pill {{ 'ok' if server.dashboard_access.enabled else 'bad' }}">Dashboard {{ 'enabled' if server.dashboard_access.enabled else 'locked' }}</span>
              <span class="pill">{{ server.map|upper }}</span>
            </div>
          </div>
        </div>
        <div class="columns">
          <section><h3>Online</h3><ul>{% for player in server.online[:6] %}<li><span>{{ player }}</span><span>online</span></li>{% else %}<li>No survivors online</li>{% endfor %}</ul></section>
          <section><h3>Leaders</h3><ul>{% for leader in server.leaders[:6] %}<li><span>{{ leader.name }}</span><span>{{ leader.kills }}</span></li>{% else %}<li>No stats yet</li>{% endfor %}</ul></section>
          <section><h3>Channels</h3><ul>{% for channel in server.channels[:6] %}<li><span>{{ channel.key }}</span><span>{{ channel.id }}</span></li>{% else %}<li>No channels saved</li>{% endfor %}</ul></section>
          <section><h3>Totals</h3><ul><li><span>Kills</span><span>{{ server.totals.kills }}</span></li><li><span>Deaths</span><span>{{ server.totals.deaths }}</span></li><li><span>Safe zones</span><span>{{ server.safe_zones|length }}</span></li><li><span>Factions</span><span>{{ server.factions|length }}</span></li></ul></section>
        </div>
      </article>
      {% else %}
      <article class="card"><h2>No guilds configured</h2><p class="muted">Run the Discord setup flow, then refresh this dashboard.</p></article>
      {% endfor %}
    </section>
  </main>
  <script>
    function formValue(value) {
      const text = String(value || "").trim();
      if (text === "true") return true;
      if (text === "false") return false;
      if (/^-?\\d+$/.test(text)) return Number(text);
      if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) {
        try { return JSON.parse(text); } catch (error) { return value; }
      }
      return value;
    }
    document.querySelectorAll(".admin-form").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = new FormData(form);
        const result = form.querySelector(".result");
        let payload = {};
        data.forEach((value, key) => {
          if (value !== "") payload[key] = formValue(value);
        });
        const featureBoxes = form.querySelectorAll('input[name^="feature_"]');
        if (featureBoxes.length) {
          payload.features = {};
          featureBoxes.forEach((box) => {
            payload.features[box.name.replace("feature_", "")] = box.checked;
            delete payload[box.name];
          });
        }
        result.textContent = "Saving...";
        const token = new URLSearchParams(window.location.search).get("token");
        const route = token ? `${form.dataset.route}?token=${encodeURIComponent(token)}` : form.dataset.route;
        const response = await fetch(route, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        let body = {};
        try { body = await response.json(); } catch (error) {}
        result.textContent = response.ok ? "Saved" : (body.error || "Rejected");
      });
    });
  </script>
</body>
</html>
"""

ADMIN_ROUTES = [
    "/api/admin/embed-template",
    "/api/admin/welcome-automation",
    "/api/admin/reaction-role-panel",
    "/api/admin/shop-item",
    "/api/admin/faction",
    "/api/admin/faction-member",
    "/api/admin/wage",
    "/api/admin/wallet-adjustment",
    "/api/admin/guild-access",
]


def data_path(filename: str) -> str:
    return os.path.join(DATA_ROOT, filename)


def read_json_file(filename: str, default: Any) -> Any:
    path = data_path(filename)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default
    return default if data is None else data


def write_json_file(filename: str, data: Any) -> None:
    os.makedirs(DATA_ROOT, exist_ok=True)
    with open(data_path(filename), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def load_store(name: str, default: Any) -> Any:
    return read_json_file(FILES[name], default)


def save_store(name: str, data: Any) -> None:
    write_json_file(FILES[name], data)


def dashboard_password_hash(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def verify_dashboard_password(password: str, credentials: dict[str, Any]) -> bool:
    salt = str(credentials.get("password_salt") or "")
    expected = str(credentials.get("password_hash") or "")
    if not salt or not expected:
        return False
    return secrets.compare_digest(dashboard_password_hash(password, salt), expected)


def session_signature(guild_id: str, password_hash: str) -> str:
    return hashlib.sha256(f"{guild_id}:{password_hash}:{DASHBOARD_COOKIE_SECRET}".encode("utf-8")).hexdigest()


def make_session_cookie(guild_id: str, credentials: dict[str, Any]) -> str:
    password_hash = str(credentials.get("password_hash") or "")
    return f"{guild_id}:{session_signature(guild_id, password_hash)}"


def find_guild_by_dashboard_id(dashboard_id: str) -> tuple[str | None, dict[str, Any] | None]:
    dashboard_id = str(dashboard_id or "").strip().lower()
    if not dashboard_id:
        return None, None
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return None, None
    for guild_id, config in guild_configs.items():
        if not isinstance(config, dict):
            continue
        credentials = config.get("dashboard_credentials")
        if not isinstance(credentials, dict):
            credentials = config.get("dashboard_login")
        if not isinstance(credentials, dict):
            continue
        if str(credentials.get("dashboard_id") or "").strip().lower() == dashboard_id:
            return str(guild_id), config
    return None, None


def current_auth() -> dict[str, Any] | None:
    provided = request.headers.get("X-Dashboard-Token") or request.args.get("token") or ""
    if ADMIN_TOKEN and secrets.compare_digest(provided, ADMIN_TOKEN):
        return {"kind": "owner", "guild_id": None, "label": "all servers"}

    cookie = request.cookies.get("dashboard_session", "")
    if ":" not in cookie:
        return None
    guild_id, signature = cookie.split(":", 1)
    guild_configs = load_store("guild_configs", {})
    config = guild_configs.get(guild_id) if isinstance(guild_configs, dict) else None
    if not isinstance(config, dict):
        return None
    credentials = config.get("dashboard_credentials")
    if not isinstance(credentials, dict):
        credentials = config.get("dashboard_login")
    if not isinstance(credentials, dict):
        return None
    expected = session_signature(guild_id, str(credentials.get("password_hash") or ""))
    if not secrets.compare_digest(signature, expected):
        return None
    return {
        "kind": "guild",
        "guild_id": guild_id,
        "label": str(config.get("guild_name") or f"Guild {guild_id}"),
    }


def login_page(error: str = ""):
    return render_template_string(LOGIN_TEMPLATE, error=error)


def require_page_auth(owner_only: bool = False):
    auth = current_auth()
    if not auth:
        return None, redirect("/login")
    if owner_only and auth["kind"] != "owner":
        return None, (jsonify({"ok": False, "error": "owner token required"}), 403)
    return auth, None


def scoped_payload_for_auth(payload: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    if auth["kind"] == "guild":
        payload = dict(payload)
        payload["guild_id"] = auth["guild_id"]
    return payload


def request_payload() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form.to_dict(flat=True)
    return dict(data or {})


def require_admin() -> tuple[dict[str, Any] | None, Any | None]:
    auth = current_auth()
    if not auth:
        return None, (jsonify({"ok": False, "error": "dashboard login required"}), 401)
    return scoped_payload_for_auth(request_payload(), auth), None


def normalize_guild_id(value: Any) -> str:
    return str(value or "global").strip() or "global"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def public_channels(channels: Any) -> list[dict[str, str]]:
    if not isinstance(channels, dict):
        return []
    return [{"key": str(key), "id": str(value)} for key, value in sorted(channels.items()) if value]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if any(secret_key in str(key).lower() for secret_key in SECRET_KEYS):
                cleaned[key] = "***"
            else:
                cleaned[key] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def guild_players(player_stats: Any, guild_id: str) -> list[dict[str, Any]]:
    players = []
    if not isinstance(player_stats, dict):
        return players
    for name, stats in player_stats.items():
        if not isinstance(stats, dict):
            continue
        stat_guild_id = str(stats.get("guild_id") or "")
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
    return sorted(players, key=lambda item: (-item["kills"], item["deaths"], item["name"].lower()))


def dashboard_access(config: dict[str, Any]) -> dict[str, Any]:
    access = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    features = access.get("features") if isinstance(access.get("features"), dict) else {}
    return {
        "enabled": bool(access.get("enabled", False)),
        "tier": str(access.get("tier") or "none"),
        "allowed_role_ids": [str(item) for item in access.get("allowed_role_ids", []) if item],
        "allowed_user_ids": [str(item) for item in access.get("allowed_user_ids", []) if item],
        "features": {
            "economy": bool(features.get("economy", False)),
            "embeds": bool(features.get("embeds", False)),
            "factions": bool(features.get("factions", False)),
            "leaderboards": bool(features.get("leaderboards", True)),
            "safe_zones": bool(features.get("safe_zones", False)),
        },
    }


def count_records(value: Any) -> int:
    if isinstance(value, (dict, list)):
        return len(value)
    return 0


def guild_block(data: Any, guild_id: str, default: Any) -> Any:
    if isinstance(data, dict):
        return data.get(guild_id, default)
    return default


def load_dashboard_state() -> dict[str, Any]:
    runtime_state = CUSTOM_STATE_PROVIDER() if CUSTOM_STATE_PROVIDER else {}
    if not isinstance(runtime_state, dict):
        runtime_state = {}

    guild_configs = runtime_state.get("guild_configs") or load_store("guild_configs", {})
    player_stats = runtime_state.get("player_stats") or load_store("player_stats", {})
    online_players = runtime_state.get("online_players") or load_store("online_players", {})
    shop = runtime_state.get("shop_items") or runtime_state.get("shop") or load_store("shop", {})
    wallets = runtime_state.get("wallets") or load_store("wallets", {})
    factions = runtime_state.get("factions") or load_store("factions", {})
    wages = runtime_state.get("wages") or load_store("wages", {})
    delivery_queue = runtime_state.get("delivery_queue") or load_store("delivery_queue", [])
    dashboard_admin = load_store("dashboard_admin", {})

    if not isinstance(guild_configs, dict):
        guild_configs = {}
    if not isinstance(online_players, dict):
        online_players = {}

    servers = []
    total_online = 0
    total_players = 0
    total_kills = 0
    dashboard_enabled = 0

    for guild_id, config in sorted(guild_configs.items(), key=lambda item: str(item[1].get("guild_name", item[0])).lower() if isinstance(item[1], dict) else str(item[0])):
        if not isinstance(config, dict):
            continue
        guild_id = normalize_guild_id(guild_id)
        players = guild_players(player_stats, guild_id)
        online = sorted(str(player) for player in online_players.get(guild_id, []) if player)
        access = dashboard_access(config)
        safe_zones = config.get("safe_zones") or config.get("radar_zones") or []
        if not isinstance(safe_zones, list):
            safe_zones = []
        server_factions = guild_block(factions, guild_id, {})
        server_wages = guild_block(wages, guild_id, [])
        totals = {
            "kills": sum(player["kills"] for player in players),
            "deaths": sum(player["deaths"] for player in players),
            "builds": sum(player["builds"] for player in players),
            "players": len(players),
        }
        total_online += len(online)
        total_players += len(players)
        total_kills += totals["kills"]
        dashboard_enabled += 1 if access["enabled"] else 0
        servers.append(
            {
                "guild_id": guild_id,
                "guild_name": str(config.get("guild_name") or f"Guild {guild_id}"),
                "active": not bool(config.get("bot_removed")),
                "map": str(config.get("server_map") or config.get("map") or "chernarus"),
                "online": online,
                "leaders": players,
                "channels": public_channels(config.get("channels", {})),
                "totals": totals,
                "safe_zones": redact(safe_zones),
                "dashboard_access": access,
                "factions": redact(server_factions),
                "wages": redact(server_wages),
                "config": redact(config),
            }
        )

    admin_embed_templates = dashboard_admin.get("embed_templates", {}) if isinstance(dashboard_admin, dict) else {}
    admin_welcome = dashboard_admin.get("welcome_automations", {}) if isinstance(dashboard_admin, dict) else {}
    admin_reaction_roles = dashboard_admin.get("reaction_role_panels", {}) if isinstance(dashboard_admin, dict) else {}

    return {
        "summary": {
            "guilds": len(servers),
            "online": total_online,
            "players": total_players,
            "kills": total_kills,
            "dashboard_enabled": dashboard_enabled,
            "shop_items": count_records(shop),
            "wallets": count_records(wallets),
            "delivery_queue": count_records(delivery_queue),
            "factions": sum(count_records(server.get("factions")) for server in servers),
            "wages": sum(count_records(server.get("wages")) for server in servers),
            "embed_templates": count_records(admin_embed_templates),
            "welcome_automations": count_records(admin_welcome),
            "reaction_role_panels": count_records(admin_reaction_roles),
        },
        "servers": servers,
        "shop": redact(shop),
        "wallets": redact(wallets),
        "delivery_queue": redact(delivery_queue),
        "dashboard_admin": redact(dashboard_admin),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def filter_state_for_auth(state: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    if auth["kind"] == "owner":
        return state
    guild_id = str(auth["guild_id"])
    servers = [server for server in state["servers"] if str(server.get("guild_id")) == guild_id]
    summary = dict(state["summary"])
    if servers:
        server = servers[0]
        summary.update(
            {
                "guilds": 1,
                "online": len(server.get("online", [])),
                "players": server.get("totals", {}).get("players", 0),
                "kills": server.get("totals", {}).get("kills", 0),
                "dashboard_enabled": 1 if server.get("dashboard_access", {}).get("enabled") else 0,
                "factions": count_records(server.get("factions")),
                "wages": count_records(server.get("wages")),
            }
        )
    else:
        summary.update({"guilds": 0, "online": 0, "players": 0, "kills": 0, "dashboard_enabled": 0, "factions": 0, "wages": 0})
    scoped = dict(state)
    scoped["summary"] = summary
    scoped["servers"] = servers
    return scoped


def page(mode: str, auth: dict[str, Any]):
    state = load_dashboard_state()
    state = filter_state_for_auth(state, auth)
    return render_template_string(
        PAGE_TEMPLATE,
        mode=mode,
        view_title={"overview": "Operations Dashboard", "admin": "Admin Control Panel", "owner": "Owner Console"}[mode],
        auth=auth,
        refresh_seconds=DASHBOARD_REFRESH_SECONDS,
        summary=state["summary"],
        servers=state["servers"],
        generated_at=state["generated_at"],
        admin_routes=ADMIN_ROUTES,
        all_routes=sorted(str(rule) for rule in APP.url_map.iter_rules()),
    )


def save_dashboard_admin(section: str, payload: dict[str, Any], key_name: str = "id") -> dict[str, Any]:
    data = load_store("dashboard_admin", {})
    if not isinstance(data, dict):
        data = {}
    block = data.setdefault(section, {})
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_block_data = block.setdefault(guild_id, {})
    item_id = str(payload.get(key_name) or payload.get("name") or f"{section}-{int(datetime.now(UTC).timestamp())}")
    record = dict(payload)
    record[key_name] = item_id
    record["guild_id"] = guild_id
    record["updated_at"] = datetime.now(UTC).isoformat()
    guild_block_data[item_id] = record
    save_store("dashboard_admin", data)
    return record


@APP.get("/healthz")
def healthz():
    return jsonify({"ok": True, "generated_at": datetime.now(UTC).isoformat()})


@APP.get("/brand-image")
def brand_image():
    if os.path.exists(BOT_IMAGE_FILE):
        return send_file(BOT_IMAGE_FILE)
    return ("", 404)


@APP.get("/")
def index():
    auth, error = require_page_auth()
    if error:
        return error
    return page("overview", auth)


@APP.get("/admin")
def admin():
    auth, error = require_page_auth()
    if error:
        return error
    return page("admin", auth)


@APP.get("/owner")
def owner():
    auth, error = require_page_auth(owner_only=True)
    if error:
        return error
    return page("owner", auth)


@APP.get("/login")
def login_get():
    if current_auth():
        return redirect("/")
    return login_page()


@APP.post("/login")
def login_post():
    dashboard_id = str(request.form.get("dashboard_id") or "").strip()
    password = str(request.form.get("password") or "")
    guild_id, config = find_guild_by_dashboard_id(dashboard_id)
    if not guild_id or not isinstance(config, dict):
        return login_page("Dashboard ID or password is incorrect."), 401
    credentials = config.get("dashboard_credentials")
    if not isinstance(credentials, dict):
        credentials = config.get("dashboard_login")
    if not isinstance(credentials, dict) or not verify_dashboard_password(password, credentials):
        return login_page("Dashboard ID or password is incorrect."), 401
    response = make_response(redirect("/admin"))
    response.set_cookie(
        "dashboard_session",
        make_session_cookie(guild_id, credentials),
        httponly=True,
        secure=True,
        samesite="Lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@APP.get("/logout")
def logout():
    response = make_response(redirect("/login"))
    response.delete_cookie("dashboard_session")
    return response


@APP.get("/api/summary")
def api_summary():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    return jsonify(filter_state_for_auth(load_dashboard_state(), auth))


@APP.get("/api/admin")
def api_admin_index():
    if not current_auth():
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    return jsonify({"ok": True, "routes": ADMIN_ROUTES})


@APP.post("/api/admin/embed-template")
def api_embed_template():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("embed_templates", payload or {}, "template_id")
    return jsonify({"ok": True, "template": record})


@APP.post("/api/admin/welcome-automation")
def api_welcome_automation():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("welcome_automations", payload or {}, "automation_id")
    return jsonify({"ok": True, "automation": record})


@APP.post("/api/admin/reaction-role-panel")
def api_reaction_role_panel():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("reaction_role_panels", payload or {}, "panel_id")
    return jsonify({"ok": True, "panel": record})


@APP.post("/api/admin/shop-item")
def api_shop_item():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    item_name = str(payload.get("item_name") or payload.get("name") or "").strip()
    if not item_name:
        return jsonify({"ok": False, "error": "item_name is required"}), 400
    shop = load_store("shop", {})
    if not isinstance(shop, dict):
        shop = {}
    existing = shop.get(item_name, {}) if isinstance(shop.get(item_name), dict) else {}
    existing.update(
        {
            "price": safe_int(payload.get("price", existing.get("price", 0))),
            "category": str(payload.get("category") or existing.get("category") or "General"),
            "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    shop[item_name] = existing
    save_store("shop", shop)
    return jsonify({"ok": True, "item": {item_name: existing}})


@APP.post("/api/admin/faction")
def api_faction():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    name = str(payload.get("name") or payload.get("faction") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name is required"}), 400
    factions = load_store("factions", {})
    if not isinstance(factions, dict):
        factions = {}
    block = factions.setdefault(guild_id, {})
    faction = block.get(name, {}) if isinstance(block.get(name), dict) else {}
    faction.update(
        {
            "name": name,
            "leader_id": str(payload.get("leader_id") or faction.get("leader_id") or ""),
            "role_id": str(payload.get("role_id") or faction.get("role_id") or ""),
            "alert_channel_id": str(payload.get("alert_channel_id") or faction.get("alert_channel_id") or ""),
            "alert_channel_key": str(payload.get("alert_channel_key") or faction.get("alert_channel_key") or ""),
            "colour": str(payload.get("colour") or payload.get("color") or faction.get("colour") or "#8d963e"),
            "members": faction.get("members", []),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    block[name] = faction
    save_store("factions", factions)
    return jsonify({"ok": True, "faction": faction})


@APP.post("/api/admin/faction-member")
def api_faction_member():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    name = str(payload.get("name") or payload.get("faction") or "").strip()
    member_id = str(payload.get("member_id") or payload.get("user_id") or "").strip()
    if not name or not member_id:
        return jsonify({"ok": False, "error": "name and member_id are required"}), 400
    factions = load_store("factions", {})
    if not isinstance(factions, dict):
        factions = {}
    faction = factions.setdefault(guild_id, {}).setdefault(name, {"name": name, "members": []})
    members = faction.setdefault("members", [])
    action = str(payload.get("action") or "add").lower()
    if action in {"remove", "delete"}:
        faction["members"] = [member for member in members if str(member.get("user_id", member) if isinstance(member, dict) else member) != member_id]
    elif member_id not in [str(member.get("user_id", member) if isinstance(member, dict) else member) for member in members]:
        members.append({"user_id": member_id, "name": str(payload.get("member_name") or ""), "added_at": datetime.now(UTC).isoformat()})
    faction["updated_at"] = datetime.now(UTC).isoformat()
    save_store("factions", factions)
    return jsonify({"ok": True, "faction": faction})


@APP.post("/api/admin/wage")
def api_wage():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    wages = load_store("wages", {})
    if not isinstance(wages, dict):
        wages = {}
    block = wages.setdefault(guild_id, [])
    wage_id = str(payload.get("id") or payload.get("wage_id") or f"wage-{int(datetime.now(UTC).timestamp())}")
    action = str(payload.get("action") or "upsert").lower()
    if action in {"cancel", "delete", "remove"}:
        wages[guild_id] = [wage for wage in block if str(wage.get("id")) != wage_id]
        save_store("wages", wages)
        return jsonify({"ok": True, "wage_id": wage_id, "active": False})
    record = next((wage for wage in block if str(wage.get("id")) == wage_id), None)
    if record is None:
        record = {"id": wage_id}
        block.append(record)
    record.update(
        {
            "target_type": str(payload.get("target_type") or record.get("target_type") or "user"),
            "target_id": str(payload.get("target_id") or record.get("target_id") or ""),
            "amount": safe_int(payload.get("amount", record.get("amount", 0))),
            "cadence": str(payload.get("cadence") or record.get("cadence") or "weekly"),
            "active": bool(payload.get("active", record.get("active", True))),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    save_store("wages", wages)
    return jsonify({"ok": True, "wage": record})


@APP.post("/api/admin/wallet-adjustment")
def api_wallet_adjustment():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    user_id = str(payload.get("user_id") or payload.get("member_id") or "").strip()
    if not user_id:
        return jsonify({"ok": False, "error": "user_id is required"}), 400
    amount = safe_int(payload.get("amount"))
    wallets = load_store("wallets", {})
    if not isinstance(wallets, dict):
        wallets = {}
    wallet = wallets.setdefault(user_id, {"name": str(payload.get("name") or ""), "balance": 0, "daily_transactions": 0})
    wallet["balance"] = safe_int(wallet.get("balance")) + amount
    wallet["updated_at"] = datetime.now(UTC).isoformat()
    wallet.setdefault("adjustments", []).append(
        {
            "amount": amount,
            "reason": str(payload.get("reason") or "dashboard adjustment"),
            "guild_id": normalize_guild_id(payload.get("guild_id")),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    save_store("wallets", wallets)
    return jsonify({"ok": True, "wallet": redact(wallet)})


@APP.post("/api/admin/guild-access")
def api_guild_access():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    access = config.setdefault("dashboard", {})
    if not isinstance(access, dict):
        access = {}
        config["dashboard"] = access
    access["enabled"] = bool(payload.get("enabled", access.get("enabled", True)))
    access["tier"] = str(payload.get("tier") or access.get("tier") or "owner")
    role_ids = payload.get("allowed_role_ids", access.get("allowed_role_ids", []))
    user_ids = payload.get("allowed_user_ids", access.get("allowed_user_ids", []))
    if isinstance(role_ids, str):
        role_ids = [item.strip() for item in role_ids.split(",") if item.strip()]
    if isinstance(user_ids, str):
        user_ids = [item.strip() for item in user_ids.split(",") if item.strip()]
    access["allowed_role_ids"] = [str(item) for item in role_ids if item]
    access["allowed_user_ids"] = [str(item) for item in user_ids if item]
    features = payload.get("features", access.get("features", {}))
    access["features"] = features if isinstance(features, dict) else {}
    access["updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "dashboard": access})


def configure_dashboard_state_provider(provider):
    """Let bot.py provide live in-memory state while the dashboard is embedded."""
    global CUSTOM_STATE_PROVIDER
    CUSTOM_STATE_PROVIDER = provider


def run_dashboard_server():
    APP.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, use_reloader=False)


def start_dashboard_server():
    thread = Thread(target=run_dashboard_server, name="wandering-dashboard", daemon=True)
    thread.start()
    print(f"[DASHBOARD] Web dashboard listening on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    return thread


if __name__ == "__main__":
    run_dashboard_server()
