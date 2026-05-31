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
    "heatmap": "heatmap.json",
    "pve_challenges": "pve_challenges.json",
    "pve_ai_campaigns": "pve_ai_campaigns.json",
    "pve_workshop_schedules": "pve_workshop_schedules.json",
    "swear_jar": "swear_jar.json",
    "longshot_records": "longshot_records.json",
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
    .discord-board { border-left: 4px solid #f1c40f; border-radius: .45rem; background: #202126; padding: 1rem; }
    .discord-board h2 { margin-bottom: .35rem; text-transform: uppercase; }
    .leader-category-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .95rem; margin-top: 1rem; }
    .lb-card { min-width: 0; }
    .lb-card h3 { margin-bottom: .45rem; color: #f4f4f5; text-transform: uppercase; font-size: 1rem; }
    .lb-list { display: grid; gap: .28rem; }
    .lb-row { display: flex; flex-wrap: wrap; gap: .25rem; align-items: center; color: #f4f4f5; font-weight: 800; }
    .lb-rank { display: inline-grid; place-items: center; min-width: 1.45rem; height: 1.45rem; border-radius: .25rem; background: #3498db; color: white; font-weight: 900; }
    .lb-rank.gold { background: #f1b82d; color: #17202a; border-radius: 999px; }
    .lb-rank.silver { background: #b8c2cc; color: #17202a; border-radius: 999px; }
    .lb-rank.bronze { background: #e67e22; color: #17202a; border-radius: 999px; }
    .lb-value { display: inline-block; border: 1px solid #3f4255; background: #292b3a; color: #f4f4f5; border-radius: .35rem; padding: .05rem .32rem; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-weight: 500; }
    .lb-empty { color: #d8d8dc; font-style: italic; }
    .tool-note { color: var(--muted); font-size: .9rem; line-height: 1.45; }
    .option-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
    .option-card { border: 1px solid var(--line); border-radius: .5rem; padding: .8rem; background: #070b08; }
    .option-card strong { display: block; color: var(--gold); margin-bottom: .25rem; }
    .check-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .5rem; }
    .check { display: flex; align-items: center; gap: .5rem; color: var(--muted); border: 1px solid var(--line); border-radius: .45rem; padding: .55rem; background: #070b08; }
    .check input { width: auto; accent-color: var(--olive); }
    .mini-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; }
    .mini-card { border: 1px solid var(--line); border-radius: .5rem; padding: .75rem; background: #070b08; }
    .mini-card strong { display: block; color: var(--gold); font-size: 1.25rem; }
    .stack { display: grid; gap: .65rem; }
    .notification { display: grid; gap: .2rem; border-left: 3px solid var(--gold); background: #070b08; border-radius: .35rem; padding: .65rem .75rem; color: var(--muted); }
    .toolbar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
    .embed-preview { border-left: 4px solid var(--gold); border-radius: .45rem; background: #202126; padding: .85rem; color: #f4f4f5; }
    .embed-preview strong { display: block; color: #fff; margin-bottom: .25rem; }
    .embed-preview span { color: #d8d8dc; }
    .embed-preview small { display: block; color: #aeb0b8; margin-top: .55rem; }
    .heat-list { display: grid; gap: .45rem; }
    .heat-row { display: grid; grid-template-columns: minmax(0, 1fr) 5rem; gap: .65rem; align-items: center; }
    .bar { height: .65rem; border-radius: 999px; background: rgba(213, 180, 95, .18); overflow: hidden; }
    .bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--olive), var(--gold)); }
    .item-table { width: 100%; border-collapse: collapse; }
    .item-table th, .item-table td { padding: .45rem; border-bottom: 1px solid var(--line); color: var(--muted); text-align: left; }
    input[type="color"] { min-height: 2.8rem; padding: .25rem; cursor: pointer; }
    .item-table button { padding: .35rem .5rem; font-size: .85rem; }
    .shop-toolbar { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .65rem; align-items: end; margin-bottom: .75rem; }
    .zone-builder-form { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .zone-map { position: relative; width: 100%; min-height: 34rem; aspect-ratio: 1 / .62; border: 1px solid var(--line); border-radius: .5rem; overflow: hidden; background:
      radial-gradient(circle at 22% 68%, rgba(213,180,95,.18), transparent 10%),
      radial-gradient(circle at 38% 38%, rgba(141,150,62,.34), transparent 18%),
      radial-gradient(circle at 62% 55%, rgba(52,152,219,.12), transparent 13%),
      linear-gradient(135deg, #182315, #071008 68%);
      cursor: crosshair;
    }
    .zone-map::before { content: ""; position: absolute; inset: 0; background-image: linear-gradient(rgba(243,236,217,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(243,236,217,.08) 1px, transparent 1px); background-size: 12.5% 12.5%; }
    .zone-map::after { content: "Click map to set X/Y"; position: absolute; right: .75rem; bottom: .65rem; color: var(--dim); font-size: .85rem; background: rgba(5,8,6,.72); border: 1px solid var(--line); border-radius: .35rem; padding: .3rem .45rem; }
    .zone-dot { position: absolute; transform: translate(-50%, -50%); border: 2px solid var(--gold); background: rgba(213,180,95,.22); border-radius: 50%; display: grid; place-items: center; color: var(--text); font-size: .75rem; font-weight: 900; pointer-events: none; }
    .zone-dot.safe { border-color: #75d89a; background: rgba(117,216,154,.18); }
    .zone-dot.pvp { border-color: #ed3853; background: rgba(237,56,83,.18); }
    .zone-dot.radar { border-color: #d5b45f; background: rgba(213,180,95,.2); }
    .zone-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; }
    .server-switcher { display: grid; gap: .65rem; }
    .server-tabs { display: flex; flex-wrap: wrap; gap: .5rem; }
    .server-tab { border: 1px solid var(--line); border-radius: .5rem; padding: .65rem .75rem; background: #070b08; color: var(--muted); }
    .server-tab.active { color: var(--text); border-color: var(--gold); background: rgba(213, 180, 95, .12); }
    .category-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .65rem; }
    .category-link { border: 1px solid var(--line); border-radius: .5rem; padding: .85rem; background: #070b08; color: var(--muted); }
    .category-link strong { display: block; color: var(--gold); margin-bottom: .2rem; }
    .hidden-field { display: none; }
    @media (max-width: 980px) {
      .hero, .grid, .columns, .stats, form, .zone-builder-form, .zone-options, .route-list, .panel-grid, .owner-grid, .option-grid, .leader-row, .leader-category-grid, .check-grid, .mini-grid, .heat-row, .category-grid { grid-template-columns: 1fr; }
      .zone-map { min-height: 22rem; }
      .metric { text-align: left; }
      nav { display: none; }
    }
  </style>
</head>
<body>
  {% set server = servers[0] if servers else none %}
  {% set server_qs = '&guild_id=' ~ server.guild_id if server else '' %}
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

    {% if servers|length > 1 %}
    <section class="section-panel server-switcher" id="servers">
      <div class="section-head">
        <div>
          <h2>Server Switcher</h2>
          <p class="tool-note">Linked servers stay in one dashboard. Pick a server, then every category below uses that server's data and locked server identity.</p>
        </div>
      </div>
      <div class="server-tabs">
        {% for item in servers %}
        <a class="server-tab {{ 'active' if server and item.guild_id == server.guild_id else '' }}" href="/admin?guild_id={{ item.guild_id }}">{{ item.guild_name }} · {{ item.map|upper }}</a>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    <section class="section-nav" aria-label="Dashboard sections">
      <a class="tab-link" href="/admin?section=overview{{ server_qs }}">Overview</a>
      {% if servers|length > 1 %}<a class="tab-link" href="/admin?section=overview{{ server_qs }}#servers">Servers</a>{% endif %}
      <a class="tab-link" href="/admin?section=leaderboards{{ server_qs }}">Leaderboards</a>
      <a class="tab-link" href="/admin?section=automations{{ server_qs }}">Embeds & Welcome</a>
      <a class="tab-link" href="/admin?section=factions{{ server_qs }}">Factions</a>
      <a class="tab-link" href="/admin?section=zones{{ server_qs }}">Zones</a>
      <a class="tab-link" href="/admin?section=heatmaps{{ server_qs }}">Heatmaps</a>
      <a class="tab-link" href="/admin?section=pve{{ server_qs }}">PVE & Workshop</a>
      <a class="tab-link" href="/admin?section=economy{{ server_qs }}">Economy</a>
      <a class="tab-link" href="/admin?section=shop{{ server_qs }}">Manage Shop</a>
      <a class="tab-link" href="/admin?section=server-rules{{ server_qs }}">Server Rules</a>
      {% if auth.kind == "owner" %}<a class="tab-link" href="/owner?section=owner">Owner Control</a>{% endif %}
      <a class="tab-link" href="/admin?section=access{{ server_qs }}">Access</a>
    </section>

    {% if active_section == "overview" %}
    <section class="category-grid" aria-label="Main categories">
      <a class="category-link" href="/admin?section=leaderboards{{ server_qs }}"><strong>Leaderboard</strong><span>Live kills, deaths, builds and rankings.</span></a>
      <a class="category-link" href="/admin?section=automations{{ server_qs }}"><strong>Embeds & Welcome</strong><span>Auto messages, welcomes and reaction roles.</span></a>
      <a class="category-link" href="/admin?section=factions{{ server_qs }}"><strong>Factions</strong><span>Faction setup, leaders, roles and members.</span></a>
      <a class="category-link" href="/admin?section=zones{{ server_qs }}"><strong>Zones</strong><span>Safe zones, PVP zones, radar pings and ban/action rules.</span></a>
      <a class="category-link" href="/admin?section=economy{{ server_qs }}"><strong>Economy</strong><span>Wallets, wages, rewards and punishments.</span></a>
      <a class="category-link" href="/admin?section=shop{{ server_qs }}"><strong>Manage Shop</strong><span>Items, prices, limits, availability and role restrictions.</span></a>
      <a class="category-link" href="/admin?section=server-rules{{ server_qs }}"><strong>Server Rules</strong><span>Discord link enforcement, Nitrado bans and on-screen server messages.</span></a>
      <a class="category-link" href="/admin?section=pve{{ server_qs }}"><strong>PVE & Workshop</strong><span>Quest board, campaigns and workshop status.</span></a>
      <a class="category-link" href="/admin?section=heatmaps{{ server_qs }}"><strong>Heatmaps</strong><span>PVP, PVE, infected, animal and build activity.</span></a>
      <a class="category-link" href="/admin?section=access{{ server_qs }}"><strong>Access</strong><span>Credentials, linked servers and enabled modules.</span></a>
    </section>
    {% endif %}

    {% if active_section == "leaderboards" %}
    <section class="section-panel" id="leaderboards">
      <div class="discord-board">
        <h2>{{ server.guild_name if server else 'Server' }} — Server Leaderboard</h2>
        <p><em>Top 10 per category — dashboard live view.</em></p>
        <div class="leader-category-grid">
          {% for board in (server.leaderboards if server else []) %}
          <article class="lb-card">
            <h3>{{ board.title }}</h3>
            <div class="lb-list">
              {% for row in board.rows %}
              <div class="lb-row">
                <span class="lb-rank {{ row.medal }}">{{ loop.index }}</span>
                <span>{{ row.name }}</span>
                <span>·</span>
                <span class="lb-value">{{ row.value }}</span>
              </div>
              {% else %}
              <p class="lb-empty">— no data yet —</p>
              {% endfor %}
            </div>
          </article>
          {% endfor %}
        </div>
      </div>
    </section>
    {% endif %}

    {% if mode == "owner" and active_section in ["owner", "overview"] %}
    <section class="section-panel" id="owner-control">
      <div class="section-head">
        <div>
          <h2>Owner Command Center</h2>
          <p class="tool-note">Only your owner token can open this section. Use it to inspect every guild, jump into a server dashboard, and control which modules customers can use.</p>
        </div>
      </div>
      <div class="mini-grid">
        <div class="mini-card"><span class="muted">Guilds</span><strong>{{ summary.guilds }}</strong></div>
        <div class="mini-card"><span class="muted">Members tracked</span><strong>{{ summary.players }}</strong></div>
        <div class="mini-card"><span class="muted">Heat points</span><strong>{{ summary.heatmap_points }}</strong></div>
        <div class="mini-card"><span class="muted">PVE quests</span><strong>{{ summary.pve_active }}</strong></div>
      </div>
      <div class="panel-grid" style="margin-top:.85rem">
        <article class="admin-panel">
          <h3>Owner Notifications</h3>
          <div class="stack">
            {% for note in owner_notifications %}
            <div class="notification"><strong>{{ note.title }}</strong><span>{{ note.body }}</span></div>
            {% else %}
            <p class="muted">No owner alerts right now.</p>
            {% endfor %}
          </div>
        </article>
        <article class="admin-panel">
          <h3>All Server Dashboards</h3>
          <table class="item-table">
            <thead><tr><th>Server</th><th>Map</th><th>Access</th><th>Open</th></tr></thead>
            <tbody>
              {% for owned in servers %}
              <tr>
                <td>{{ owned.guild_name }}</td>
                <td>{{ owned.map|upper }}</td>
                <td>{{ owned.dashboard_access.tier }}</td>
                <td><a class="button" href="/admin?guild_id={{ owned.guild_id }}">Open</a></td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "automations" %}
    <section class="section-panel" id="automations">
      <div class="section-head">
        <div>
          <h2>Auto Messages & Embeds</h2>
          <p class="tool-note">Create messages the bot can use for rules, restarts, welcomes, events, shop notices, and staff announcements.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Embed & Timed Message Builder</h3>
          <form class="admin-form" data-route="/api/admin/embed-template">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Purpose
              <select name="name">
                <option value="timed-reminder">Timed reminder</option>
                <option value="server-rules">Server rules</option>
                <option value="restart-warning">Restart warning</option>
                <option value="event-announcement">Event announcement</option>
                <option value="shop-notice">Shop notice</option>
                <option value="staff-alert">Staff alert</option>
                <option value="giveaway">Giveaway</option>
                <option value="level-up">Level up notice</option>
                <option value="server-stats">Server stats panel</option>
                <option value="birthday">Birthday message</option>
                <option value="moderation">Moderation message</option>
                <option value="custom-command">Custom command response</option>
                <option value="custom-message">Custom message</option>
              </select>
            </label>
            <label>Message key <input name="template_id" value="server-rules" placeholder="unique name for this embed"></label>
            <label>Message type
              <select name="content_mode"><option value="embed">Embed</option><option value="text">Plain text</option><option value="both">Text + embed</option></select>
            </label>
            <label>Post to channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}">{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label>Title <input name="title" value="Server Rules"></label>
            <label>Colour <input name="colour" type="color" value="#8d963e"></label>
            <label>Author name <input name="author_name" placeholder="optional"></label>
            <label>Author icon URL <input name="author_icon_url" placeholder="https://..."></label>
            <label>Thumbnail URL <input name="thumbnail_url" placeholder="https://..."></label>
            <label>Large image URL <input name="image_url" placeholder="https://..."></label>
            <label>Footer text <input name="footer_text" value="Wandering Bot"></label>
            <label>Footer icon URL <input name="footer_icon_url" placeholder="https://..."></label>
            <label>Mention
              <select name="mention_mode"><option value="none">No mention</option><option value="everyone">@everyone</option><option value="here">@here</option><option value="role">Role mention</option></select>
            </label>
            <label>Role ID to mention <input name="mention_role_id" placeholder="optional role id"></label>
            <label>Schedule / trigger
              <select name="schedule_type">
                <option value="manual">Manual / save only</option>
                <option value="timer">Timer</option>
                <option value="daily">Daily at time</option>
                <option value="weekly">Weekly at time</option>
                <option value="interval">Repeat every X minutes</option>
                <option value="member_join">Member joins</option>
                <option value="member_leave">Member leaves</option>
                <option value="level_up">Level up</option>
                <option value="birthday">Member birthday</option>
                <option value="stats_refresh">Server stats refresh</option>
                <option value="player_kill">Player kills another player</option>
                <option value="player_death">Player dies</option>
                <option value="zombie_death">Player killed by infected</option>
                <option value="animal_death">Player killed by animal</option>
                <option value="longshot">Longshot recorded</option>
                <option value="flag_raise">Territory flag raised</option>
                <option value="flag_lower">Territory flag lowered</option>
                <option value="player_join_server">Player joins DayZ server</option>
                <option value="player_leave_server">Player leaves DayZ server</option>
                <option value="chat_keyword">Discord message contains keyword</option>
                <option value="wallet_change">Wallet balance changes</option>
                <option value="shop_purchase">Shop purchase queued</option>
                <option value="quest_complete">PVE quest completed</option>
                <option value="radar_enter">Player enters radar zone</option>
                <option value="safe_zone_enter">Player enters safe zone</option>
              </select>
            </label>
            <label>Time / day <input name="schedule_time" placeholder="10:00, Monday 18:00, etc."></label>
            <label>Player/event filter <input name="event_filter" placeholder="keyword, player name, weapon, zone, any"></label>
            <label>Minimum value <input name="event_minimum" type="number" value="0" placeholder="distance, kills, amount, etc."></label>
            <label>Interval minutes <input name="interval_minutes" type="number" value="60"></label>
            <label>Timezone <input name="timezone" value="Europe/London"></label>
            <label>Button label <input name="button_label" placeholder="optional link button"></label>
            <label>Button URL <input name="button_url" placeholder="https://..."></label>
            <label class="full">Message <textarea name="body">Respect the server, no exploits, and keep it fair.</textarea></label>
            <label class="full">Embed fields <textarea name="fields_lines">Server Rule | No exploits, duping, or glitch abuse. | false
Respect | Keep chat and gameplay fair. | false</textarea></label>
            <div class="full embed-preview">
              <strong>Embed preview shape</strong>
              <span>Title, description, colour, author, thumbnail/image, footer, custom fields, link button and trigger settings are saved together.</span>
              <small>Fields use: Name | Value | inline true/false</small>
            </div>
            <div class="full"><button type="submit">Save Message</button> <span class="result muted"></span></div>
          </form>
          <div class="stack" style="margin-top:.75rem">
            {% for template in (server.embed_templates if server else []) %}
            <div class="notification"><strong>{{ template.template_id }}</strong><span>{{ template.name }} -> {{ template.schedule.type if template.schedule else 'manual' }}</span></div>
            {% else %}
            <p class="muted">No saved embed templates for this server yet.</p>
            {% endfor %}
          </div>
        </article>
        <article class="admin-panel">
          <h3>Welcome, Goodbye & Birthday</h3>
          <form class="admin-form" data-route="/api/admin/welcome-automation">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>When should it send?
              <select name="name">
                <option value="new-survivor-welcome">New survivor joins Discord</option>
                <option value="member-goodbye">Member leaves Discord</option>
                <option value="birthday">Member birthday</option>
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
            <label>Assign birthday role ID <input name="birthday_role_id" placeholder="optional role id"></label>
            <label>Send hour <input name="send_hour" value="10:00"></label>
            <label class="full">Message <textarea name="message">Welcome survivor. Read the rules, link your gamer tag, and good luck out there.</textarea></label>
            <div class="full"><button type="submit">Save Welcome</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Utilities & Server Growth</h3>
          <form class="admin-form" data-route="/api/admin/utility-config">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Module
              <select name="module">
                <option value="server_stats">Server statistics counters</option>
                <option value="leveling">Leveling and XP</option>
                <option value="profile_card">Custom profile/rank card</option>
                <option value="giveaways">Giveaways</option>
                <option value="birthdays">Birthday notifications</option>
                <option value="custom_commands">Custom commands</option>
                <option value="moderation">Moderation helpers</option>
                <option value="invite_tracker">Invite tracker</option>
                <option value="transcripts">Ticket transcripts</option>
              </select>
            </label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Output channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}">{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label>Limit / max count <input name="limit" type="number" value="10"></label>
            <label>XP per message <input name="xp_per_message" type="number" value="15"></label>
            <label>Cooldown seconds <input name="cooldown_seconds" type="number" value="60"></label>
            <label>Card accent colour <input name="card_colour" type="color" value="#8d963e"></label>
            <label>Background image URL <input name="background_url" placeholder="https://..."></label>
            <label class="full">Settings note <textarea name="notes">Configure this module for this server.</textarea></label>
            <div class="full"><button type="submit">Save Utility</button> <span class="result muted"></span></div>
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

    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "factions" %}
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
            <label>Colour <input name="colour" type="color" value="#8d963e"></label>
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
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "zones" %}
    <section class="section-panel" id="zones">
      <div class="section-head">
        <div>
          <h2>Zones</h2>
          <p class="tool-note">Create and manage safe zones, PVP zones, radar ping zones, faction territory, and action rules. Existing radar zones created with Discord commands are shown here too.</p>
        </div>
        <span class="pill">{{ server.zones|length if server else 0 }} zones</span>
      </div>
      <div class="panel-grid">
        <article class="admin-panel full">
          <h3>Interactive Zone Builder</h3>
          <form class="admin-form zone-builder-form" data-route="/api/admin/zone">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock full"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Zone name <input name="name" value="North West Airfield"></label>
            <label>Zone type
              <select name="zone_type"><option value="radar">Radar ping zone</option><option value="safe">Safe zone</option><option value="pvp">PVP zone</option><option value="faction">Faction territory</option><option value="custom">Custom marker</option></select>
            </label>
            <label>X coordinate <input name="x" type="number" value="7500"></label>
            <label>Y coordinate <input name="y" type="number" value="7500"></label>
            <label>Radius meters <input name="radius" type="number" value="250"></label>
            <label>Ping / report channel
              <select name="channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}" {% if channel.key == 'radar' or channel.key == 'pvp_intel' %}selected{% endif %}>{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label>Ping role ID <input name="role_id" placeholder="optional Discord role id"></label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Action on violation
              <select name="action"><option value="none">Notify only</option><option value="manhunt">Start manhunt</option><option value="ban">Ban through Nitrado</option></select>
            </label>
            <label>Ban type <select name="ban_type"><option value="temp">Temp ban</option><option value="perm">Perm ban</option></select></label>
            <label>Temp ban minutes <input name="ban_duration_minutes" type="number" value="1440"></label>
            <label>Trigger territory <select name="trigger_territory"><option value="inside">Inside zone</option><option value="outside">Outside zone</option></select></label>
            <label class="full">Triggers <input name="triggers" value="detection,login,kill,build" placeholder="detection, login, kill, build, flag_raise"></label>
            <label class="full">Ignored gamertags <input name="ignored_gamertags" placeholder="comma-separated names that should not ping radar"></label>
            <div class="full zone-map" data-zone-map data-map-size="{{ server.map_size if server else 15360 }}">
              {% for zone in (server.zones if server else []) %}
              <span class="zone-dot {{ zone.zone_type }}" title="{{ zone.name }}" style="left: {{ zone.x_percent }}%; top: {{ zone.y_percent }}%; width: {{ zone.dot_size }}px; height: {{ zone.dot_size }}px;">{{ loop.index }}</span>
              {% endfor %}
            </div>
            <div class="full"><button type="submit">Save Zone</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel full">
          <h3>Existing Zones</h3>
          <table class="item-table">
            <thead><tr><th>#</th><th>Name</th><th>Type</th><th>Center</th><th>Radius</th><th>Action</th><th>Channel</th></tr></thead>
            <tbody>
              {% for zone in (server.zones if server else []) %}
              <tr><td>{{ loop.index }}</td><td>{{ zone.name }}</td><td>{{ zone.zone_type }}</td><td>{{ zone.x }}, {{ zone.y }}</td><td>{{ zone.radius }}m</td><td>{{ zone.action or 'notify' }}</td><td>{{ zone.channel_key or zone.alert_channel_id or zone.report_channel_id or 'default' }}</td></tr>
              {% else %}
              <tr><td colspan="7">No zones saved yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "heatmaps" %}
    <section class="section-panel" id="heatmaps">
      <div class="section-head">
        <div>
          <h2>Heatmaps</h2>
          <p class="tool-note">See the busiest PVP, PVE, infected, animal, build, and movement zones the bot has collected from ADM activity.</p>
        </div>
        <span class="pill">{{ server.heatmap.total if server else 0 }} events</span>
      </div>
      <div class="panel-grid">
        {% for mode_name, heat in (server.heatmap.modes.items() if server else []) %}
        <article class="admin-panel">
          <h3>{{ mode_name|upper }} Heat</h3>
          <div class="heat-list">
            {% for zone in heat %}
            <div>
              <div class="heat-row"><span>{{ zone.name }}</span><strong>{{ zone.count }}</strong></div>
              <div class="bar"><span style="width: {{ zone.percent }}%"></span></div>
            </div>
            {% else %}
            <p class="muted">No heat recorded for this mode yet.</p>
            {% endfor %}
          </div>
        </article>
        {% else %}
        <article class="admin-panel"><h3>No Heatmap Data</h3><p class="muted">The bot will fill this once ADM events are processed.</p></article>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "pve" %}
    <section class="section-panel" id="pve-workshop">
      <div class="section-head">
        <div>
          <h2>PVE Quests & Workshop</h2>
          <p class="tool-note">Track active quests, AI campaigns, scheduled workshop posts, and reward delivery information from the dashboard.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Active Quest Board</h3>
          <table class="item-table">
            <thead><tr><th>Quest</th><th>Difficulty</th><th>Reward</th></tr></thead>
            <tbody>
              {% for quest in (server.pve.active[:10] if server else []) %}
              <tr><td>{{ quest.title }}</td><td>{{ quest.difficulty }}</td><td>{{ quest.reward_pennies }}</td></tr>
              {% else %}
              <tr><td colspan="3">No active PVE quests found yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
        <article class="admin-panel">
          <h3>Quest Workshop</h3>
          <div class="mini-grid">
            <div class="mini-card"><span class="muted">Campaigns</span><strong>{{ server.pve.campaigns if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Schedules</span><strong>{{ server.pve.schedules if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Rewards</span><strong>{{ server.pve.reward_types|length if server else 0 }}</strong></div>
            <div class="mini-card"><span class="muted">Quest channels</span><strong>{{ server.pve.quest_channels if server else 0 }}</strong></div>
          </div>
          <p class="tool-note" style="margin-top:.75rem">Use the Discord quest-workshop channel for AI generation. This dashboard shows the state and lets you control whether each guild has the module enabled.</p>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "economy" %}
    <section class="section-panel" id="economy">
      <div class="section-head">
        <div>
          <h2>Economy</h2>
          <p class="tool-note">Control wallets, recurring wages, and reward or punishment rules without touching raw JSON.</p>
        </div>
      </div>
      <div class="panel-grid">
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
        <article class="admin-panel">
          <h3>Reward / Punishment Rule</h3>
          <form class="admin-form" data-route="/api/admin/economy-rule">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>When this happens
              <select name="event_type">
                <option value="chat_keyword">Chat keyword</option>
                <option value="kill">Player kill</option>
                <option value="death">Player death</option>
                <option value="zombie_kill">Infected kill</option>
                <option value="animal_kill">Animal kill</option>
                <option value="longshot">Longshot</option>
              </select>
            </label>
            <label>Reward or punish
              <select name="kind"><option value="reward">Reward pennies</option><option value="punishment">Remove pennies</option></select>
            </label>
            <label>Keyword / condition <input name="keyword" placeholder="e.g. gg, kill, longshot"></label>
            <label>Amount <input name="amount" type="number" value="100"></label>
            <div class="full"><button type="submit">Save Rule</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "shop" %}
    <section class="section-panel" id="shop-control">
      <div class="section-head">
        <div>
          <h2>Shop Control</h2>
          <p class="tool-note">Items imported from types.xml appear here already grouped by category. Admins can set prices, enable/disable items, add limits, and restrict items by Discord role or player.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Edit Shop Item</h3>
          <form class="admin-form" data-route="/api/admin/shop-item" id="shop-edit-form">
            <label>Item name <input name="item_name" value="NailsBox"></label>
            <label>Price <input name="price" type="number" value="100"></label>
            <label>Category
              <select name="category">
                <option value="Building">Building</option>
                <option value="Weapons">Weapons</option>
                <option value="Medical">Medical</option>
                <option value="Food">Food</option>
                <option value="Tools">Tools</option>
                <option value="Clothing">Clothing</option>
                <option value="General">General</option>
              </select>
            </label>
            <label>Available <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Daily purchase limit <input name="daily_limit" type="number" value="0" placeholder="0 = server default"></label>
            <label>Role IDs allowed <input name="allowed_role_ids" placeholder="optional comma-separated role IDs"></label>
            <label class="full">Blocked player IDs <input name="blocked_user_ids" placeholder="optional comma-separated Discord user IDs"></label>
            <div class="full"><button type="submit">Save Item</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel full">
          <h3>All Shop Items</h3>
          <div class="shop-toolbar">
            <label>Search items <input data-shop-search placeholder="type item/category/status"></label>
            <span class="pill">{{ shop_items|length }} items</span>
          </div>
          <table class="item-table">
            <thead><tr><th>Item</th><th>Category</th><th>Price</th><th>Status</th><th>Limit</th><th>Edit</th></tr></thead>
            <tbody>
              {% for item in shop_items %}
              <tr data-shop-row data-search="{{ item.name|lower }} {{ item.category|lower }} {{ 'on' if item.enabled else 'off' }}">
                <td>{{ item.name }}</td>
                <td>{{ item.category }}</td>
                <td>{{ item.price }}</td>
                <td>{{ 'On' if item.enabled else 'Off' }}</td>
                <td>{{ item.daily_limit if item.daily_limit else 'default' }}</td>
                <td><button type="button" data-shop-edit data-item="{{ item.name }}" data-price="{{ item.price }}" data-category="{{ item.category }}" data-enabled="{{ 'true' if item.enabled else 'false' }}" data-limit="{{ item.daily_limit }}" data-roles="{{ item.allowed_role_ids|join(',') }}" data-blocked="{{ item.blocked_user_ids|join(',') }}">Edit</button></td>
              </tr>
              {% else %}
              <tr><td colspan="6">No shop items available.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
        {% for category, items in shop_categories.items() %}
        <article class="admin-panel">
          <h3>{{ category }}</h3>
          <table class="item-table">
            <thead><tr><th>Item</th><th>Price</th><th>Status</th></tr></thead>
            <tbody>
              {% for item in items[:12] %}
              <tr><td>{{ item.name }}</td><td>{{ item.price }}</td><td>{{ 'On' if item.enabled else 'Off' }}</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </article>
        {% else %}
        <article class="admin-panel"><h3>No Shop Items</h3><p class="muted">Import types.xml in Discord with `/tools importtypesxml`, then manage the items here.</p></article>
        {% endfor %}
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "server-rules" %}
    <section class="section-panel" id="server-rules">
      <div class="section-head">
        <div>
          <h2>Server Rules & Nitrado Control</h2>
          <p class="tool-note">Control Discord-link enforcement, automatic Nitrado bans, immediate restart-on-ban, and DayZ on-screen messages. File changes take effect after a server restart.</p>
        </div>
      </div>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Discord Link Enforcement</h3>
          <form class="admin-form" data-route="/api/admin/link-enforcement">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>Grace minutes after join <input name="grace_minutes" type="number" value="30" min="1"></label>
            <label>Action if still unlinked
              <select name="action">
                <option value="notify">Notify staff only</option>
                <option value="kick">Kick request / notify</option>
                <option value="temp_ban">Temp ban through Nitrado</option>
                <option value="perm_ban">Perm ban through Nitrado</option>
              </select>
            </label>
            <label>Temp ban minutes <input name="temp_ban_minutes" type="number" value="60" min="1"></label>
            <label>Restart after ban <select name="restart_on_ban"><option value="true">Yes, immediately</option><option value="false">No</option></select></label>
            <label>Notify channel
              <select name="notification_channel_key">
                {% for channel in (server.channels if server else []) %}<option value="{{ channel.key }}" {% if channel.key == 'public_shame' or channel.key == 'admin_logs' %}selected{% endif %}>{{ channel.key }}</option>{% endfor %}
              </select>
            </label>
            <label class="full">Player message / reason <textarea name="reason">You must join this Discord and link your gamertag with /linkgamer to play on this server.</textarea></label>
            <div class="full"><button type="submit">Save Enforcement</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>On-Screen Messages</h3>
          <form class="admin-form" data-route="/api/admin/on-screen-message">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Server</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Message key <input name="message_id" value="discord-required"></label>
            <label>Enabled <select name="enabled"><option value="true">On</option><option value="false">Off</option></select></label>
            <label>When to show
              <select name="trigger">
                <option value="server_restart">After restart</option>
                <option value="player_join">Player joins</option>
                <option value="discord_required">Discord link reminder</option>
                <option value="scheduled">Timed schedule</option>
                <option value="custom">Custom</option>
              </select>
            </label>
            <label>Start delay seconds <input name="delay_seconds" type="number" value="30" min="0"></label>
            <label>Repeat minutes <input name="repeat_minutes" type="number" value="30" min="0"></label>
            <label>Display seconds <input name="display_seconds" type="number" value="10" min="1"></label>
            <label>Colour <input name="colour" type="color" value="#d5b45f"></label>
            <label class="full">Message text <textarea name="text">Join the Discord and link your gamertag with /linkgamer to keep playing.</textarea></label>
            <div class="full embed-preview">
              <strong>Restart required</strong>
              <span>DayZ reads messages.xml on server start. The bot stores this for the server file workflow, then the change applies after the next restart.</span>
            </div>
            <div class="full"><button type="submit">Save On-Screen Message</button> <span class="result muted"></span></div>
          </form>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode in ["admin", "owner"] and active_section == "access" %}
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
                <label class="check"><input type="checkbox" name="feature_heatmaps" checked> Heatmaps</label>
                <label class="check"><input type="checkbox" name="feature_pve_quests" checked> PVE quests</label>
                <label class="check"><input type="checkbox" name="feature_quest_workshop" checked> Quest workshop</label>
                <label class="check"><input type="checkbox" name="feature_shop" checked> Shop control</label>
                <label class="check"><input type="checkbox" name="feature_wages" checked> Economy wages</label>
              </div>
            </div>
            <div class="full"><button type="submit">Save Access</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Link Another Server</h3>
          <form class="admin-form" data-route="/api/admin/link-server">
            <input class="hidden-field" name="guild_id" value="{{ server.guild_id if server else '' }}">
            <div class="server-lock"><span>Current dashboard group</span><input value="{{ server.guild_name if server else 'No server selected' }}" readonly></div>
            <label>Other dashboard ID <input name="dashboard_id" autocomplete="off" placeholder="private dashboard id"></label>
            <label>Other dashboard password <input name="password" type="password" autocomplete="new-password" placeholder="private dashboard password"></label>
            <div class="full"><button type="submit">Link Server</button> <span class="result muted"></span></div>
          </form>
          <p class="tool-note" style="margin-top:.75rem">This verifies the other server's private dashboard login before it appears in this dashboard group.</p>
        </article>
      </div>
    </section>
    {% endif %}

    {% if mode == "owner" and active_section == "overview" %}
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

    {% if active_section == "overview" %}
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
    {% endif %}
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
    document.querySelectorAll("[data-shop-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const form = document.getElementById("shop-edit-form");
        if (!form) return;
        form.elements.item_name.value = button.dataset.item || "";
        form.elements.price.value = button.dataset.price || 0;
        form.elements.category.value = button.dataset.category || "General";
        form.elements.enabled.value = button.dataset.enabled || "true";
        form.elements.daily_limit.value = button.dataset.limit || 0;
        form.elements.allowed_role_ids.value = button.dataset.roles || "";
        form.elements.blocked_user_ids.value = button.dataset.blocked || "";
        form.scrollIntoView({behavior: "smooth", block: "center"});
        form.elements.price.focus();
      });
    });
    document.querySelectorAll("[data-shop-search]").forEach((input) => {
      input.addEventListener("input", () => {
        const query = input.value.trim().toLowerCase();
        document.querySelectorAll("[data-shop-row]").forEach((row) => {
          row.style.display = !query || row.dataset.search.includes(query) ? "" : "none";
        });
      });
    });
    document.querySelectorAll("[data-zone-map]").forEach((map) => {
      map.addEventListener("click", (event) => {
        const form = map.closest("form");
        if (!form) return;
        const size = Number(map.dataset.mapSize || 15360);
        const rect = map.getBoundingClientRect();
        const x = Math.round(((event.clientX - rect.left) / rect.width) * size);
        const y = Math.round((1 - ((event.clientY - rect.top) / rect.height)) * size);
        form.elements.x.value = Math.max(0, Math.min(size, x));
        form.elements.y.value = Math.max(0, Math.min(size, y));
      });
    });
  </script>
</body>
</html>
"""

ADMIN_ROUTES = [
    "/api/admin/embed-template",
    "/api/admin/welcome-automation",
    "/api/admin/utility-config",
    "/api/admin/reaction-role-panel",
    "/api/admin/shop-item",
    "/api/admin/economy-rule",
    "/api/admin/link-server",
    "/api/admin/zone",
    "/api/admin/link-enforcement",
    "/api/admin/on-screen-message",
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


def linked_guild_ids_for_config(config: dict[str, Any], primary_guild_id: str) -> list[str]:
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    linked = dashboard.get("linked_guild_ids", []) if isinstance(dashboard, dict) else []
    if not isinstance(linked, list):
        linked = []
    guild_ids = [str(primary_guild_id)]
    for linked_id in linked:
        linked_id = str(linked_id).strip()
        if linked_id and linked_id not in guild_ids:
            guild_ids.append(linked_id)
    return guild_ids


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
        "guild_ids": linked_guild_ids_for_config(config, guild_id),
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
        allowed_guild_ids = [str(item) for item in auth.get("guild_ids", [auth["guild_id"]])]
        requested_guild_id = str(payload.get("guild_id") or auth["guild_id"])
        payload["guild_id"] = requested_guild_id if requested_guild_id in allowed_guild_ids else auth["guild_id"]
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


def csv_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def public_channels(channels: Any) -> list[dict[str, str]]:
    if not isinstance(channels, dict):
        return []
    return [{"key": str(key), "id": str(value)} for key, value in sorted(channels.items()) if value]


def is_shop_sellable_item(item_name: Any, category: Any = "") -> bool:
    name = str(item_name or "").strip()
    lower = name.lower()
    category_lower = str(category or "").lower()
    if not name:
        return False
    blocked_prefixes = (
        "animal_",
        "zmb",
        "land_wreck",
        "land_wreck_",
        "land_misc_wreck",
        "wreck_",
        "static_",
    )
    blocked_fragments = (
        "wreck",
        "doors_",
        "door_",
        "hood_",
        "trunk_",
        "wheel_ruined",
        "zombie",
        "infected",
    )
    vehicle_classes = (
        "civilian",
        "civsedan",
        "hatchback",
        "offroadhatchback",
        "sedan",
        "truck",
        "bus",
        "ada",
        "olga",
        "sarka",
        "gunter",
        "humvee",
        "boat",
    )
    if lower.startswith(blocked_prefixes):
        return False
    if any(fragment in lower for fragment in blocked_fragments):
        return False
    if category_lower in {"vehicles", "vehicle", "animals", "infected", "zombies"}:
        return False
    if any(lower.startswith(vehicle) for vehicle in vehicle_classes):
        return False
    return True


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
                "time_online_seconds": safe_int(stats.get("time_online_seconds")),
                "multikill_best": safe_int(stats.get("multikill_best")),
                "kill_streak": safe_int(stats.get("best_spree") or stats.get("kill_streak")),
                "longest_shot_distance": safe_int(stats.get("longest_shot_distance")),
                "flags_raised": safe_int(stats.get("flags_raised")),
                "animal_deaths": safe_int(stats.get("animal_deaths")),
                "zombie_deaths": safe_int(stats.get("zombie_deaths")),
            }
        )
    return sorted(players, key=lambda item: (-item["kills"], item["deaths"], item["name"].lower()))


def format_seconds(seconds: Any) -> str:
    total = safe_int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def medal_class(index: int) -> str:
    return {1: "gold", 2: "silver", 3: "bronze"}.get(index, "")


def stat_board(title: str, players: list[dict[str, Any]], key: str, suffix: str, limit: int = 10) -> dict[str, Any]:
    rows = [player for player in players if safe_int(player.get(key)) > 0]
    rows.sort(key=lambda item: (-safe_int(item.get(key)), str(item.get("name", "")).lower()))
    return {
        "title": title,
        "rows": [
            {"name": row["name"], "value": f"{safe_int(row.get(key))} {suffix}".strip(), "medal": medal_class(index)}
            for index, row in enumerate(rows[:limit], start=1)
        ],
    }


def time_board(players: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [player for player in players if safe_int(player.get("time_online_seconds")) > 0]
    rows.sort(key=lambda item: (-safe_int(item.get("time_online_seconds")), str(item.get("name", "")).lower()))
    return {
        "title": "⏱️ Most Time Played",
        "rows": [
            {"name": row["name"], "value": format_seconds(row.get("time_online_seconds")), "medal": medal_class(index)}
            for index, row in enumerate(rows[:10], start=1)
        ],
    }


def longshot_board(players: list[dict[str, Any]], longshot_records: Any, guild_id: str) -> dict[str, Any]:
    best: dict[str, int] = {}
    for player in players:
        distance = safe_int(player.get("longest_shot_distance"))
        if distance > 0:
            best[player["name"]] = max(best.get(player["name"], 0), distance)
    records = guild_block(longshot_records, guild_id, [])
    for record in list_records(records):
        if not isinstance(record, dict):
            continue
        name = str(record.get("killer") or record.get("player") or "Unknown")
        distance = safe_int(record.get("distance") or record.get("meters"))
        if distance > 0:
            best[name] = max(best.get(name, 0), distance)
    rows = sorted(best.items(), key=lambda item: (-item[1], item[0].lower()))[:10]
    return {
        "title": "🎯 Longest Shot",
        "rows": [
            {"name": name, "value": f"{distance}m", "medal": medal_class(index)}
            for index, (name, distance) in enumerate(rows, start=1)
        ],
    }


def swear_board(swear_jar: Any, players: list[dict[str, Any]]) -> dict[str, Any]:
    known_names = {str(player.get("discord_id", "")): player["name"] for player in players if player.get("discord_id")}
    rows = []
    if isinstance(swear_jar, dict):
        for key, entry in swear_jar.items():
            if isinstance(entry, dict):
                count = safe_int(entry.get("count") or entry.get("swears") or entry.get("total"))
                name = str(entry.get("name") or known_names.get(str(key)) or key)
            else:
                count = safe_int(entry)
                name = str(known_names.get(str(key)) or key)
            if count > 0:
                rows.append({"name": name, "count": count})
    rows.sort(key=lambda item: (-item["count"], item["name"].lower()))
    return {
        "title": "🤬 Most Swearing",
        "rows": [
            {"name": row["name"], "value": f"{row['count']} swears", "medal": medal_class(index)}
            for index, row in enumerate(rows[:10], start=1)
        ],
    }


def leaderboard_categories(players: list[dict[str, Any]], swear_jar: Any, longshot_records: Any, guild_id: str) -> list[dict[str, Any]]:
    return [
        stat_board("☠️ Most Kills", players, "kills", "kills"),
        stat_board("💀 Most Deaths", players, "deaths", "deaths"),
        time_board(players),
        stat_board("🔨 Most Built", players, "builds", "parts"),
        stat_board("🔫 Highest Kill Streak", players, "kill_streak", "kills w/o dying"),
        longshot_board(players, longshot_records, guild_id),
        swear_board(swear_jar, players),
        stat_board("🚩 Most Flags Raised", players, "flags_raised", "flags"),
        stat_board("🐺 Most Deaths By Animal", players, "animal_deaths", "deaths"),
        stat_board("🧟 Most Deaths By Zombies", players, "zombie_deaths", "deaths"),
    ]


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
            "heatmaps": bool(features.get("heatmaps", False)),
            "leaderboards": bool(features.get("leaderboards", True)),
            "pve_quests": bool(features.get("pve_quests", False)),
            "quest_workshop": bool(features.get("quest_workshop", False)),
            "safe_zones": bool(features.get("safe_zones", False)),
            "shop": bool(features.get("shop", False)),
            "wages": bool(features.get("wages", False)),
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


def list_records(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def dashboard_admin_records(dashboard_admin: Any, section: str, guild_id: str) -> list[dict[str, Any]]:
    if not isinstance(dashboard_admin, dict):
        return []
    section_data = dashboard_admin.get(section, {})
    if not isinstance(section_data, dict):
        return []
    return [item for item in list_records(section_data.get(guild_id, {})) if isinstance(item, dict)]


def shop_category_map(shop: Any) -> dict[str, list[dict[str, Any]]]:
    categories: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(shop, dict):
        return categories
    for item_name, data in sorted(shop.items(), key=lambda item: str(item[0]).lower()):
        if not isinstance(data, dict):
            data = {}
        category = str(data.get("category") or "General")
        if not is_shop_sellable_item(item_name, category):
            continue
        categories.setdefault(category, []).append(
            {
                "name": str(item_name),
                "price": safe_int(data.get("price")),
                "enabled": bool(data.get("enabled", True)),
                "daily_limit": safe_int(data.get("daily_limit")),
                "allowed_role_ids": [str(item) for item in data.get("allowed_role_ids", [])] if isinstance(data.get("allowed_role_ids"), list) else [],
                "blocked_user_ids": [str(item) for item in data.get("blocked_user_ids", [])] if isinstance(data.get("blocked_user_ids"), list) else [],
            }
        )
    return dict(sorted(categories.items(), key=lambda item: item[0].lower()))


def flat_shop_items(shop: Any) -> list[dict[str, Any]]:
    items = []
    for category_items in shop_category_map(shop).values():
        items.extend(category_items)
    return sorted(items, key=lambda item: (str(item.get("category", "")).lower(), str(item.get("name", "")).lower()))


def map_size_for(server_map: str) -> int:
    name = str(server_map or "").strip().lower()
    if "livonia" in name or name == "enoch":
        return 12800
    return 15360


def normalized_zones(config: dict[str, Any], server_map: str) -> list[dict[str, Any]]:
    map_size = map_size_for(server_map)
    zones = []
    for zone in list_records(config.get("zones", [])):
        if isinstance(zone, dict):
            zones.append(dict(zone))
    for zone in list_records(config.get("safe_zones", [])):
        if isinstance(zone, dict):
            zone = dict(zone)
            zone.setdefault("zone_type", "safe")
            zones.append(zone)
    for zone in list_records(config.get("radar_zones", [])):
        if isinstance(zone, dict):
            zone = dict(zone)
            zone.setdefault("zone_type", "radar")
            zones.append(zone)
    normalized = []
    seen = set()
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        x = max(0, min(map_size, safe_int(zone.get("x") or zone.get("center_x") or zone.get("pos_x"))))
        y = max(0, min(map_size, safe_int(zone.get("y") or zone.get("center_y") or zone.get("pos_y"))))
        radius = max(25, safe_int(zone.get("radius") or zone.get("radius_m") or 250))
        zone_type = str(zone.get("zone_type") or zone.get("type") or "radar").lower()
        if zone_type not in {"safe", "pvp", "radar", "faction", "custom"}:
            zone_type = "custom"
        zone_id = str(zone.get("id") or zone.get("name") or f"zone-{len(normalized) + 1}")
        dedupe_key = (zone_type, zone_id, x, y, radius)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "id": zone_id,
                "name": str(zone.get("name") or zone.get("label") or "Unnamed zone"),
                "zone_type": zone_type,
                "x": x,
                "y": y,
                "radius": radius,
                "channel_key": str(zone.get("channel_key") or ""),
                "alert_channel_id": str(zone.get("alert_channel_id") or ""),
                "report_channel_id": str(zone.get("report_channel_id") or ""),
                "role_id": str(zone.get("role_id") or ""),
                "mention_role_id": str(zone.get("mention_role_id") or ""),
                "action": str(zone.get("action") or "none"),
                "enabled": bool(zone.get("enabled", True)),
                "x_percent": round((x / map_size) * 100, 2) if map_size else 0,
                "y_percent": round(100 - ((y / map_size) * 100), 2) if map_size else 0,
                "dot_size": max(14, min(56, int((radius / map_size) * 320))),
            }
        )
    return normalized


def heatmap_summary(heatmap: Any, guild_id: str) -> dict[str, Any]:
    raw = guild_block(heatmap, guild_id, {}) if isinstance(heatmap, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    modes = raw.get("__modes__", {}) if isinstance(raw.get("__modes__"), dict) else {}
    pvp = {key: value for key, value in raw.items() if not str(key).startswith("__") and isinstance(value, int)}
    if pvp:
        modes = dict(modes)
        modes.setdefault("pvp", pvp)
    if not modes:
        modes = {"all": pvp}
    summary_modes = {}
    total = 0
    for mode, counts in modes.items():
        if not isinstance(counts, dict):
            continue
        rows = sorted(
            ({"name": str(zone), "count": safe_int(count)} for zone, count in counts.items()),
            key=lambda item: item["count"],
            reverse=True,
        )[:8]
        max_count = max([row["count"] for row in rows] or [1])
        for row in rows:
            row["percent"] = max(5, min(100, int((row["count"] / max_count) * 100))) if row["count"] else 0
        total += sum(row["count"] for row in rows)
        summary_modes[str(mode)] = rows
    return {"total": total, "modes": summary_modes}


def pve_summary(challenges: Any, campaigns: Any, schedules: Any, guild_id: str, channels: list[dict[str, str]]) -> dict[str, Any]:
    active = []
    for quest in list_records(guild_block(challenges, guild_id, [])):
        if not isinstance(quest, dict):
            continue
        active.append(
            {
                "title": str(quest.get("title") or quest.get("name") or quest.get("quest_code") or "Untitled quest"),
                "difficulty": str(quest.get("difficulty") or quest.get("tier") or "Normal"),
                "reward_pennies": safe_int(quest.get("reward_pennies") or quest.get("reward")),
                "reward_type": str(quest.get("reward_type") or "pennies"),
            }
        )
    campaign_records = list_records(guild_block(campaigns, guild_id, []))
    schedule_records = list_records(guild_block(schedules, guild_id, []))
    reward_types = sorted({quest["reward_type"] for quest in active if quest.get("reward_type")})
    quest_channels = len([channel for channel in channels if "pve" in channel.get("key", "") or "quest" in channel.get("key", "")])
    return {
        "active": active,
        "campaigns": len(campaign_records),
        "schedules": len(schedule_records),
        "reward_types": reward_types,
        "quest_channels": quest_channels,
    }


def owner_notifications(servers: list[dict[str, Any]], delivery_queue: Any, dashboard_admin: Any) -> list[dict[str, str]]:
    notes = []
    for server in servers:
        if not server.get("active"):
            notes.append({"title": f"{server.get('guild_name')} inactive", "body": "The bot is marked as removed or inactive for this guild."})
        if not server.get("dashboard_access", {}).get("enabled"):
            notes.append({"title": f"{server.get('guild_name')} dashboard locked", "body": "Dashboard access is currently disabled for this server."})
    queued = count_records(delivery_queue)
    if queued:
        notes.append({"title": "Shop deliveries waiting", "body": f"{queued} delivery records are queued for the next restart."})
    if isinstance(dashboard_admin, dict):
        saved_messages = sum(count_records(block) for block in dashboard_admin.get("embed_templates", {}).values()) if isinstance(dashboard_admin.get("embed_templates"), dict) else 0
        if saved_messages:
            notes.append({"title": "Saved embed templates", "body": f"{saved_messages} auto-message/embed templates are configured across dashboards."})
    return notes[:10]


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
    heatmap = runtime_state.get("territory_heat") or runtime_state.get("heatmap") or load_store("heatmap", {})
    pve_challenges = runtime_state.get("pve_challenges") or load_store("pve_challenges", {})
    pve_ai_campaigns = runtime_state.get("pve_ai_campaigns") or load_store("pve_ai_campaigns", {})
    pve_workshop_schedules = runtime_state.get("pve_workshop_schedules") or load_store("pve_workshop_schedules", {})
    swear_jar = runtime_state.get("swear_jar") or load_store("swear_jar", {})
    longshot_records = runtime_state.get("longshot_records") or load_store("longshot_records", {})
    shop_categories = shop_category_map(shop)
    shop_items = flat_shop_items(shop)

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
        server_map = str(config.get("server_map") or config.get("map") or "chernarus")
        zones = normalized_zones(config, server_map)
        safe_zones = config.get("safe_zones") or []
        if not isinstance(safe_zones, list):
            safe_zones = []
        server_factions = guild_block(factions, guild_id, {})
        server_wages = guild_block(wages, guild_id, [])
        channels = public_channels(config.get("channels", {}))
        server_heatmap = heatmap_summary(heatmap, guild_id)
        server_pve = pve_summary(pve_challenges, pve_ai_campaigns, pve_workshop_schedules, guild_id, channels)
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
                "map": server_map,
                "map_size": map_size_for(server_map),
                "online": online,
                "leaders": players,
                "leaderboards": leaderboard_categories(players, swear_jar, longshot_records, guild_id),
                "channels": channels,
                "totals": totals,
                "safe_zones": redact(safe_zones),
                "zones": redact(zones),
                "dashboard_access": access,
                "factions": redact(server_factions),
                "wages": redact(server_wages),
                "chat_rules": redact(config.get("chat_rules", [])),
                "embed_templates": redact(dashboard_admin_records(dashboard_admin, "embed_templates", guild_id)),
                "heatmap": server_heatmap,
                "pve": server_pve,
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
            "heatmap_points": sum(server.get("heatmap", {}).get("total", 0) for server in servers),
            "pve_active": sum(count_records(server.get("pve", {}).get("active")) for server in servers),
            "pve_campaigns": sum(safe_int(server.get("pve", {}).get("campaigns")) for server in servers),
        },
        "servers": servers,
        "shop": redact(shop),
        "shop_items": redact(shop_items),
        "shop_categories": redact(shop_categories),
        "wallets": redact(wallets),
        "delivery_queue": redact(delivery_queue),
        "dashboard_admin": redact(dashboard_admin),
        "owner_notifications": owner_notifications(servers, delivery_queue, dashboard_admin),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }


def filter_state_for_auth(state: dict[str, Any], auth: dict[str, Any]) -> dict[str, Any]:
    if auth["kind"] == "owner":
        return state
    allowed_guild_ids = [str(item) for item in auth.get("guild_ids", [auth["guild_id"]])]
    servers = [server for server in state["servers"] if str(server.get("guild_id")) in allowed_guild_ids]
    summary = dict(state["summary"])
    if servers:
        summary.update(
            {
                "guilds": len(servers),
                "online": sum(len(server.get("online", [])) for server in servers),
                "players": sum(safe_int(server.get("totals", {}).get("players")) for server in servers),
                "kills": sum(safe_int(server.get("totals", {}).get("kills")) for server in servers),
                "dashboard_enabled": sum(1 for server in servers if server.get("dashboard_access", {}).get("enabled")),
                "factions": sum(count_records(server.get("factions")) for server in servers),
                "wages": sum(count_records(server.get("wages")) for server in servers),
                "heatmap_points": sum(server.get("heatmap", {}).get("total", 0) for server in servers),
                "pve_active": sum(count_records(server.get("pve", {}).get("active")) for server in servers),
                "pve_campaigns": sum(safe_int(server.get("pve", {}).get("campaigns")) for server in servers),
            }
        )
    else:
        summary.update({"guilds": 0, "online": 0, "players": 0, "kills": 0, "dashboard_enabled": 0, "factions": 0, "wages": 0, "heatmap_points": 0, "pve_active": 0, "pve_campaigns": 0})
    scoped = dict(state)
    scoped["summary"] = summary
    scoped["servers"] = servers
    return scoped


def page(mode: str, auth: dict[str, Any]):
    state = load_dashboard_state()
    state = filter_state_for_auth(state, auth)
    active_section = str(request.args.get("section") or "overview").strip().lower()
    valid_sections = {"overview", "leaderboards", "automations", "factions", "zones", "heatmaps", "pve", "economy", "shop", "server-rules", "access", "owner"}
    if active_section not in valid_sections:
        active_section = "overview"
    focused_guild_id = str(request.args.get("guild_id") or "").strip()
    if focused_guild_id and mode in {"admin", "overview"}:
        state = dict(state)
        focused = [server for server in state["servers"] if str(server.get("guild_id")) == focused_guild_id]
        others = [server for server in state["servers"] if str(server.get("guild_id")) != focused_guild_id]
        if focused:
            state["servers"] = focused + others
    return render_template_string(
        PAGE_TEMPLATE,
        mode=mode,
        active_section=active_section,
        view_title={"overview": "Operations Dashboard", "admin": "Admin Control Panel", "owner": "Owner Console"}[mode],
        auth=auth,
        refresh_seconds=DASHBOARD_REFRESH_SECONDS,
        summary=state["summary"],
        servers=state["servers"],
        shop_items=state.get("shop_items", []),
        shop_categories=state.get("shop_categories", {}),
        owner_notifications=state.get("owner_notifications", []),
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


def parse_embed_fields(lines: Any) -> list[dict[str, Any]]:
    fields = []
    for raw_line in str(lines or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            continue
        fields.append(
            {
                "name": parts[0][:256],
                "value": parts[1][:1024],
                "inline": str(parts[2]).lower() in {"true", "yes", "1", "inline"} if len(parts) > 2 else False,
            }
        )
    return fields[:25]


def normalize_embed_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload or {})
    fields = parse_embed_fields(payload.pop("fields_lines", ""))
    payload["embed"] = {
        "title": str(payload.get("title") or "")[:256],
        "description": str(payload.get("body") or payload.get("description") or "")[:4000],
        "colour": str(payload.get("colour") or payload.get("color") or "#8d963e"),
        "author": {
            "name": str(payload.get("author_name") or ""),
            "icon_url": str(payload.get("author_icon_url") or ""),
        },
        "thumbnail_url": str(payload.get("thumbnail_url") or ""),
        "image_url": str(payload.get("image_url") or ""),
        "footer": {
            "text": str(payload.get("footer_text") or ""),
            "icon_url": str(payload.get("footer_icon_url") or ""),
        },
        "fields": fields,
    }
    payload["delivery"] = {
        "content_mode": str(payload.get("content_mode") or "embed"),
        "channel_key": str(payload.get("channel_key") or ""),
        "mention_mode": str(payload.get("mention_mode") or "none"),
        "mention_role_id": str(payload.get("mention_role_id") or ""),
        "button_label": str(payload.get("button_label") or ""),
        "button_url": str(payload.get("button_url") or ""),
    }
    payload["schedule"] = {
        "type": str(payload.get("schedule_type") or "manual"),
        "time": str(payload.get("schedule_time") or ""),
        "interval_minutes": safe_int(payload.get("interval_minutes"), 0),
        "timezone": str(payload.get("timezone") or "Europe/London"),
        "event_filter": str(payload.get("event_filter") or ""),
        "event_minimum": safe_int(payload.get("event_minimum"), 0),
    }
    payload["trigger"] = {
        "type": payload["schedule"]["type"],
        "filter": payload["schedule"]["event_filter"],
        "minimum": payload["schedule"]["event_minimum"],
    }
    payload["enabled"] = bool(payload.get("enabled", True))
    return payload


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
    record = save_dashboard_admin("embed_templates", normalize_embed_payload(payload or {}), "template_id")
    return jsonify({"ok": True, "template": record})


@APP.post("/api/admin/welcome-automation")
def api_welcome_automation():
    payload, error = require_admin()
    if error:
        return error
    record = save_dashboard_admin("welcome_automations", payload or {}, "automation_id")
    return jsonify({"ok": True, "automation": record})


@APP.post("/api/admin/utility-config")
def api_utility_config():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    module = str(payload.get("module") or payload.get("name") or "utility").strip()
    payload["module"] = module
    payload["name"] = module
    record = save_dashboard_admin("utility_configs", payload, "module")
    return jsonify({"ok": True, "utility": record})


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
    if not is_shop_sellable_item(item_name, payload.get("category")):
        return jsonify({"ok": False, "error": "that class is not a shop item"}), 400
    shop = load_store("shop", {})
    if not isinstance(shop, dict):
        shop = {}
    existing = shop.get(item_name, {}) if isinstance(shop.get(item_name), dict) else {}
    existing.update(
        {
            "price": safe_int(payload.get("price", existing.get("price", 0))),
            "category": str(payload.get("category") or existing.get("category") or "General"),
            "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
            "daily_limit": safe_int(payload.get("daily_limit", existing.get("daily_limit", 0))),
            "allowed_role_ids": csv_list(payload.get("allowed_role_ids", existing.get("allowed_role_ids", []))),
            "blocked_user_ids": csv_list(payload.get("blocked_user_ids", existing.get("blocked_user_ids", []))),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    shop[item_name] = existing
    save_store("shop", shop)
    return jsonify({"ok": True, "item": {item_name: existing}})


@APP.post("/api/admin/economy-rule")
def api_economy_rule():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    keyword = str(payload.get("keyword") or payload.get("condition") or "").strip().lower()
    event_type = str(payload.get("event_type") or "chat_keyword").strip().lower()
    kind = str(payload.get("kind") or "reward").strip().lower()
    amount = safe_int(payload.get("amount"))
    if kind not in {"reward", "punishment"}:
        return jsonify({"ok": False, "error": "kind must be reward or punishment"}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "amount must be above 0"}), 400
    if not keyword:
        keyword = event_type
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    rules = config.setdefault("chat_rules", [])
    if not isinstance(rules, list):
        rules = []
        config["chat_rules"] = rules
    rule = {
        "kind": kind,
        "keyword": keyword,
        "event_type": event_type,
        "amount": amount,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    rules.append(rule)
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "rule": rule})


@APP.post("/api/admin/link-server")
def api_link_server():
    auth = current_auth()
    if not auth:
        return jsonify({"ok": False, "error": "dashboard login required"}), 401
    payload = request_payload()
    dashboard_id = str(payload.get("dashboard_id") or "").strip()
    password = str(payload.get("password") or "")
    target_guild_id, target_config = find_guild_by_dashboard_id(dashboard_id)
    if not target_guild_id or not isinstance(target_config, dict):
        return jsonify({"ok": False, "error": "dashboard ID or password is incorrect"}), 401
    credentials = target_config.get("dashboard_credentials")
    if not isinstance(credentials, dict):
        credentials = target_config.get("dashboard_login")
    if not isinstance(credentials, dict) or not verify_dashboard_password(password, credentials):
        return jsonify({"ok": False, "error": "dashboard ID or password is incorrect"}), 401
    if auth["kind"] == "owner":
        return jsonify({"ok": True, "linked_guild_id": target_guild_id, "message": "owner already has access to every server"})
    primary_guild_id = str(auth["guild_id"])
    if target_guild_id == primary_guild_id:
        return jsonify({"ok": True, "linked_guild_id": target_guild_id, "message": "server already belongs to this dashboard"})
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        return jsonify({"ok": False, "error": "guild config store is unavailable"}), 500
    primary_config = guild_configs.get(primary_guild_id)
    if not isinstance(primary_config, dict):
        return jsonify({"ok": False, "error": "current dashboard config is missing"}), 404
    dashboard = primary_config.setdefault("dashboard", {})
    if not isinstance(dashboard, dict):
        dashboard = {}
        primary_config["dashboard"] = dashboard
    linked = dashboard.setdefault("linked_guild_ids", [])
    if not isinstance(linked, list):
        linked = []
        dashboard["linked_guild_ids"] = linked
    if target_guild_id not in [str(item) for item in linked]:
        linked.append(target_guild_id)
    dashboard["linked_updated_at"] = datetime.now(UTC).isoformat()
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "linked_guild_id": target_guild_id, "server": str(target_config.get("guild_name") or target_guild_id)})


@APP.post("/api/admin/zone")
def api_zone():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "zone name is required"}), 400
    zone_type = str(payload.get("zone_type") or payload.get("type") or "radar").strip().lower()
    if zone_type not in {"safe", "pvp", "radar", "faction", "custom"}:
        return jsonify({"ok": False, "error": "zone_type must be safe, pvp, radar, faction, or custom"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    map_size = map_size_for(str(config.get("server_map") or config.get("map") or "chernarus"))
    x = max(0, min(map_size, safe_int(payload.get("x"))))
    y = max(0, min(map_size, safe_int(payload.get("y"))))
    radius = max(1, safe_int(payload.get("radius"), 250))
    zone_id = str(payload.get("zone_id") or payload.get("id") or name.lower().replace(" ", "-"))
    channels = config.get("channels", {}) if isinstance(config.get("channels"), dict) else {}
    channel_key = str(payload.get("channel_key") or "")
    channel_id = channels.get(channel_key)
    role_id = str(payload.get("role_id") or "").strip()
    record = {
        "id": zone_id,
        "name": name,
        "zone_type": zone_type,
        "x": x,
        "y": y,
        "radius": radius,
        "channel_key": channel_key,
        "alert_channel_id": channel_id if zone_type == "radar" else None,
        "report_channel_id": channel_id if zone_type in {"safe", "pvp"} else None,
        "role_id": role_id,
        "mention_role_id": role_id,
        "triggers": csv_list(payload.get("triggers", ["detection", "login"])) if zone_type == "radar" else csv_list(payload.get("triggers", ["kill", "build", "trespass"])),
        "ignored_gamertags": csv_list(payload.get("ignored_gamertags", [])),
        "trigger_territory": str(payload.get("trigger_territory") or "inside"),
        "action": str(payload.get("action") or ("none" if zone_type == "radar" else "ban")),
        "ban_type": str(payload.get("ban_type") or "temp"),
        "ban_duration_minutes": max(1, safe_int(payload.get("ban_duration_minutes"), 1440)),
        "escalate_to_perm_after": max(1, safe_int(payload.get("escalate_to_perm_after"), 3)),
        "enabled": bool(payload.get("enabled", True)),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if zone_type == "radar":
        radar_record = dict(record)
        radar_record["cooldown_seconds"] = max(1, safe_int(payload.get("cooldown_seconds"), 600))
        target = config.setdefault("radar_zones", [])
    elif zone_type in {"safe", "pvp"}:
        radar_record = dict(record)
        radar_record["shape"] = "circle"
        if zone_type == "pvp" and radar_record["action"] == "none":
            radar_record["action"] = "ban"
        target = config.setdefault("safe_zones", [])
    else:
        radar_record = dict(record)
        target = config.setdefault("zones", [])
    if not isinstance(target, list):
        target = []
        if zone_type == "radar":
            config["radar_zones"] = target
        elif zone_type in {"safe", "pvp"}:
            config["safe_zones"] = target
        else:
            config["zones"] = target
    replaced = False
    for index, zone in enumerate(target):
        if isinstance(zone, dict) and str(zone.get("id") or zone.get("name")) == zone_id:
            target[index] = radar_record
            replaced = True
            break
    if not replaced:
        target.append(radar_record)
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "zone": radar_record})


@APP.post("/api/admin/link-enforcement")
def api_link_enforcement():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    action = str(payload.get("action") or "notify").strip().lower()
    if action not in {"notify", "kick", "temp_ban", "perm_ban"}:
        return jsonify({"ok": False, "error": "action must be notify, kick, temp_ban, or perm_ban"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    record = {
        "enabled": bool(payload.get("enabled", False)),
        "grace_minutes": max(1, safe_int(payload.get("grace_minutes"), 30)),
        "action": action,
        "temp_ban_minutes": max(1, safe_int(payload.get("temp_ban_minutes"), 60)),
        "restart_on_ban": bool(payload.get("restart_on_ban", True)),
        "notification_channel_key": str(payload.get("notification_channel_key") or "public_shame"),
        "reason": str(payload.get("reason") or "Discord membership and gamertag link required.")[:500],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    config["discord_link_enforcement"] = record
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "enforcement": record})


@APP.post("/api/admin/on-screen-message")
def api_on_screen_message():
    payload, error = require_admin()
    if error:
        return error
    payload = payload or {}
    guild_id = normalize_guild_id(payload.get("guild_id"))
    message_id = str(payload.get("message_id") or payload.get("name") or "").strip()
    if not message_id:
        return jsonify({"ok": False, "error": "message_id is required"}), 400
    guild_configs = load_store("guild_configs", {})
    if not isinstance(guild_configs, dict):
        guild_configs = {}
    config = guild_configs.setdefault(guild_id, {"channels": {}})
    messages = config.setdefault("onscreen_messages", {})
    if not isinstance(messages, dict):
        messages = {}
        config["onscreen_messages"] = messages
    record = {
        "message_id": message_id,
        "enabled": bool(payload.get("enabled", True)),
        "trigger": str(payload.get("trigger") or "scheduled"),
        "delay_seconds": max(0, safe_int(payload.get("delay_seconds"), 30)),
        "repeat_minutes": max(0, safe_int(payload.get("repeat_minutes"), 30)),
        "display_seconds": max(1, safe_int(payload.get("display_seconds"), 10)),
        "colour": str(payload.get("colour") or "#d5b45f"),
        "text": str(payload.get("text") or "")[:1000],
        "requires_restart": True,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    messages[message_id] = record
    pending = config.setdefault("pending_server_file_changes", [])
    if isinstance(pending, list) and "messages.xml" not in pending:
        pending.append("messages.xml")
    save_store("guild_configs", guild_configs)
    return jsonify({"ok": True, "message": record, "note": "messages.xml changes take effect after a server restart"})


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
