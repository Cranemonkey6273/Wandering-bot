"""Flask dashboard for Wandering Bot.

The dashboard reads and writes the same JSON files used by ``bot.py``. It is
deliberately conservative: secrets are never rendered, and admin routes mutate
local JSON state only so the Discord bot can pick up changes on its next read.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from threading import Thread
from typing import Any

from flask import Flask, jsonify, render_template_string, request, send_file


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

APP = Flask(__name__)
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

PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="{{ refresh_seconds }}">
  <title>Wandering Bot Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050806;
      --panel: #111710;
      --panel-2: #192014;
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
    nav a, button, .button {
      border: 1px solid var(--line);
      border-radius: .5rem;
      background: var(--panel-2);
      color: var(--text);
      padding: .6rem .8rem;
      font-weight: 800;
      cursor: pointer;
    }
    main { max-width: 1440px; margin: 0 auto; padding: 1.1rem clamp(1rem, 4vw, 2rem) 2rem; display: grid; gap: 1rem; }
    .hero, .card, .wide {
      border: 1px solid var(--line);
      background: linear-gradient(180deg, rgba(243, 236, 217, .05), rgba(243, 236, 217, .015)), var(--panel);
      border-radius: .5rem;
      box-shadow: 0 1rem 2.5rem rgba(0, 0, 0, .3);
    }
    .hero { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1rem; align-items: center; padding: clamp(1rem, 4vw, 2rem); }
    h1 { margin: .2rem 0 .5rem; font-size: clamp(2rem, 5vw, 4.25rem); line-height: .95; text-transform: uppercase; letter-spacing: 0; }
    h2, h3, p { margin-top: 0; }
    .hero img { width: min(11rem, 35vw); aspect-ratio: 1; object-fit: cover; border-radius: 50%; border: 2px solid var(--gold); }
    .stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .75rem; }
    .stat, .card { padding: 1rem; }
    .stat { border: 1px solid var(--line); border-radius: .5rem; background: #0b100b; }
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
    .full { grid-column: 1 / -1; }
    .route-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .4rem; }
    .route-list code { display: block; overflow-wrap: anywhere; }
    .panel-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; }
    .admin-panel { border: 1px solid var(--line); border-radius: .5rem; padding: 1rem; background: #0b100b; }
    .admin-panel form { margin-top: .75rem; }
    .result { min-height: 1.25rem; }
    .owner-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
    .owner-tile { border: 1px solid var(--line); border-radius: .5rem; padding: .85rem; background: #0b100b; }
    .owner-tile strong { display: block; color: var(--gold); font-size: 1.35rem; }
    .table { width: 100%; border-collapse: collapse; margin-top: .75rem; }
    .table th, .table td { border-bottom: 1px solid var(--line); padding: .55rem; text-align: left; color: var(--muted); }
    .table th { color: var(--text); font-size: .8rem; text-transform: uppercase; }
    @media (max-width: 980px) {
      .hero, .grid, .columns, .stats, form, .route-list, .panel-grid, .owner-grid { grid-template-columns: 1fr; }
      nav { display: none; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <img src="/brand-image" alt="Wandering Bot logo">
      <div><strong>Wandering Bot</strong><span>{{ view_title }}</span></div>
    </div>
    <nav>
      <a href="/">Overview</a>
      <a href="/admin">Admin</a>
      <a href="/owner">Owner</a>
      <a href="/api/summary">API</a>
    </nav>
  </header>
  <main>
    <section class="hero">
      <div>
        <p class="muted">{{ generated_at }}</p>
        <h1>{{ view_title }}</h1>
        <p class="muted">Live readout for servers, feeds, economy, factions, wages, embeds, welcome automation and reaction-role panels.</p>
      </div>
      <img src="/brand-image" alt="Wandering Bot mark">
    </section>

    <section class="stats">
      <div class="stat"><span>Guilds</span><strong>{{ summary.guilds }}</strong></div>
      <div class="stat"><span>Online</span><strong>{{ summary.online }}</strong></div>
      <div class="stat"><span>Players</span><strong>{{ summary.players }}</strong></div>
      <div class="stat"><span>Shop</span><strong>{{ summary.shop_items }}</strong></div>
      <div class="stat"><span>Factions</span><strong>{{ summary.factions }}</strong></div>
    </section>

    {% if mode in ["admin", "owner"] %}
    <section class="wide card">
      <h2>Admin Control Panels</h2>
      <p class="muted">Pick a server, update the panel, and the dashboard writes the bot JSON files in the Railway volume.</p>
      <div class="panel-grid">
        <article class="admin-panel">
          <h3>Embed Template</h3>
          <form class="admin-form" data-route="/api/admin/embed-template">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>Template name <input name="name" value="server-rules"></label>
            <label>Title <input name="title" value="Server Rules"></label>
            <label>Colour <input name="colour" value="#8d963e"></label>
            <label class="full">Body <textarea name="body">Respect the server, no exploits, and keep it fair.</textarea></label>
            <div class="full"><button type="submit">Save Embed</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Welcome Automation</h3>
          <form class="admin-form" data-route="/api/admin/welcome-automation">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>Name <input name="name" value="new-survivor-welcome"></label>
            <label>Channel ID <input name="channel_id" placeholder="Discord channel id"></label>
            <label>Enabled <select name="enabled"><option value="true">true</option><option value="false">false</option></select></label>
            <label class="full">Message <textarea name="message">Welcome survivor. Read the rules, link your gamer tag, and good luck out there.</textarea></label>
            <div class="full"><button type="submit">Save Welcome</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Reaction Roles</h3>
          <form class="admin-form" data-route="/api/admin/reaction-role-panel">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>Panel name <input name="name" value="server-roles"></label>
            <label>Channel ID <input name="channel_id" placeholder="Discord channel id"></label>
            <label>Message ID <input name="message_id" placeholder="optional existing message"></label>
            <label class="full">Roles JSON <textarea name="roles">[{"emoji":"yes","role_id":"1234567890","label":"Verified"}]</textarea></label>
            <div class="full"><button type="submit">Save Panel</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Shop Item</h3>
          <form class="admin-form" data-route="/api/admin/shop-item">
            <label>Item name <input name="item_name" value="NailsBox"></label>
            <label>Price <input name="price" type="number" value="100"></label>
            <label>Category <input name="category" value="Building"></label>
            <label>Enabled <select name="enabled"><option value="true">true</option><option value="false">false</option></select></label>
            <div class="full"><button type="submit">Save Item</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Faction</h3>
          <form class="admin-form" data-route="/api/admin/faction">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>Name <input name="name" value="The Wanderers"></label>
            <label>Leader ID <input name="leader_id" placeholder="Discord user id"></label>
            <label>Role ID <input name="role_id" placeholder="Discord role id"></label>
            <label>Alert Channel ID <input name="alert_channel_id" placeholder="Discord channel id"></label>
            <label>Colour <input name="colour" value="#8d963e"></label>
            <div class="full"><button type="submit">Save Faction</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Faction Member</h3>
          <form class="admin-form" data-route="/api/admin/faction-member">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>Faction <input name="name" value="The Wanderers"></label>
            <label>Member ID <input name="member_id" placeholder="Discord user id"></label>
            <label>Action <select name="action"><option value="add">add</option><option value="remove">remove</option></select></label>
            <div class="full"><button type="submit">Update Member</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Wage</h3>
          <form class="admin-form" data-route="/api/admin/wage">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>Target type <select name="target_type"><option value="user">user</option><option value="role">role</option><option value="faction">faction</option></select></label>
            <label>Target ID <input name="target_id" placeholder="user, role, or faction"></label>
            <label>Amount <input name="amount" type="number" value="250"></label>
            <label>Cadence <select name="cadence"><option value="daily">daily</option><option value="weekly">weekly</option><option value="monthly">monthly</option></select></label>
            <label>Active <select name="active"><option value="true">true</option><option value="false">false</option></select></label>
            <div class="full"><button type="submit">Save Wage</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Wallet Adjustment</h3>
          <form class="admin-form" data-route="/api/admin/wallet-adjustment">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>User ID <input name="user_id" placeholder="Discord user id"></label>
            <label>Amount <input name="amount" type="number" value="100"></label>
            <label>Reason <input name="reason" value="dashboard adjustment"></label>
            <div class="full"><button type="submit">Adjust Wallet</button> <span class="result muted"></span></div>
          </form>
        </article>
        <article class="admin-panel">
          <h3>Dashboard Access</h3>
          <form class="admin-form" data-route="/api/admin/guild-access">
            <label>Guild ID <input name="guild_id" value="{{ servers[0].guild_id if servers else '' }}"></label>
            <label>Enabled <select name="enabled"><option value="true">true</option><option value="false">false</option></select></label>
            <label>Tier <select name="tier"><option value="owner">owner</option><option value="premium">premium</option><option value="trial">trial</option><option value="none">none</option></select></label>
            <label>Allowed role IDs <input name="allowed_role_ids" placeholder="123,456"></label>
            <label class="full">Features JSON <textarea name="features">{"leaderboards":true,"economy":true,"factions":true,"embeds":true,"safe_zones":true}</textarea></label>
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
        <thead><tr><th>Server</th><th>Guild ID</th><th>Map</th><th>Channels</th><th>Access</th></tr></thead>
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
      <article class="card"><h3>Embeds</h3><p class="muted">{{ summary.embed_templates }} templates, {{ summary.welcome_automations }} welcome automations and {{ summary.reaction_role_panels }} reaction-role panels.</p></article>
      <article class="card"><h3>Access</h3><p class="muted">{{ summary.dashboard_enabled }} guilds have dashboard access enabled.</p></article>
    </section>

    <section class="servers">
      {% for server in servers %}
      <article class="card">
        <div class="server-head">
          <div>
            <h2>{{ server.guild_name }}</h2>
            <div class="pills">
              <span class="pill">Guild {{ server.guild_id }}</span>
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
        result.textContent = "Saving...";
        const response = await fetch(form.dataset.route, {
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


def request_payload() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form.to_dict(flat=True)
    return dict(data or {})


def require_admin() -> tuple[dict[str, Any] | None, Any | None]:
    if ADMIN_TOKEN:
        provided = request.headers.get("X-Dashboard-Token") or request.args.get("token") or ""
        if not secrets.compare_digest(provided, ADMIN_TOKEN):
            return None, (jsonify({"ok": False, "error": "admin token required"}), 401)
    return request_payload(), None


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


def page(mode: str):
    state = load_dashboard_state()
    return render_template_string(
        PAGE_TEMPLATE,
        mode=mode,
        view_title={"overview": "Operations Dashboard", "admin": "Admin Control Panel", "owner": "Owner Console"}[mode],
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
    return page("overview")


@APP.get("/admin")
def admin():
    return page("admin")


@APP.get("/owner")
def owner():
    return page("owner")


@APP.get("/api/summary")
def api_summary():
    return jsonify(load_dashboard_state())


@APP.get("/api/admin")
def api_admin_index():
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
