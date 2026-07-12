# Wandering Bot Mobile App Plan

## Product Goal

Build Wandering Bot into a phone-friendly control app for DayZ server owners and trusted admins while keeping dangerous server actions on the backend.

The app should let an owner check server status, feeds, restarts, billing/access, and common dashboard tools from a phone. It must not put Nitrado tokens, FTP credentials, Stripe secrets, XML upload logic, or Discord bot tokens inside an iPhone or Android app.

## Recommended Path

Start with the dashboard as an installable web app, then wrap the same backend in native iOS and Android shells once the mobile experience is stable.

This fits the current codebase because the dashboard is a Flask/server-rendered app with existing login, permission checks, billing plans, server profiles, and tool pages. Rebuilding all of that as a separate native app first would duplicate risky logic and make bugs harder to control.

## Phase 1 - Installable Web App

Scope:

- Add a valid web app manifest.
- Keep all sensitive actions server-side.
- Make login, server switcher, start page, live feeds, billing/upgrade, and core admin sections comfortable on mobile.
- Make the dashboard usable from iPhone and Android home screens.

Acceptance criteria:

- `/manifest.webmanifest` returns valid manifest JSON.
- Login/public/checkout/dashboard pages include the manifest and mobile theme metadata.
- Main dashboard sections remain reachable without horizontal layout breakage.
- No secrets are exposed in the manifest or client-side code.

## Phase 2 - App-Focused Dashboard Views

Scope:

- Add an app landing/home section for owners after login.
- Add compact mobile cards for:
  - active server profile
  - DayZ online count
  - Nitrado/FTP/ADM status
  - latest feed activity
  - next restart
  - raid weekend state
  - event upload warnings
  - billing/access state
- Keep full tools in the dashboard, but give mobile users a fast overview first.

Core owner workflows:

- Recent feeds: show the latest killfeed, build feed, placed item feed, flag feed, connect/disconnect feed, radar ping, heatmap and event alerts by server profile.
- Shop editing: allow quick edits for shop categories, stock, prices, trader items and enabled/disabled state.
- Global economy editing: allow safe edits for player balances, item pricing, wages, rewards and economy settings.
- Restart schedules: show active restart schedule, next restart time, reminder messages and audit status.
- Vehicle reset schedules: show next vehicle reset, reset preparation state, reset completion state and whether a second cleanup restart is still needed.
- Base damage controls: show raid weekend state, base damage, container damage and the next scheduled toggle.
- Member moderation: allow server-scoped ban, unban, warning, linked-gamertag lookup, role/access review and staff notes.
- Customer access: show plan/tier state, private/manual payment reference, expiry, trial end and which dashboard modules are unlocked.
- Preset server files: offer safe ready-made downloads for common server-owner needs such as vanilla reference files, unlimited stamina `cfggameplay.json`, build-anywhere `cfggameplay.json`, boosted food/drink `types.xml`, boosted weapons/ammo `types.xml`, boosted full economy starter packs and map-specific Chernarus/Livonia variants.
- Guide library: add short help pages for beginners, file definitions, helpful tools, making events, animal spawns, zombie spawns, loot in buildings, custom categories, usage tags, definitions and map loot tiers.
- Direct preset apply: later, allow a preset to be applied directly only through the backend with target server confirmation, live-file backup, diff preview, validation, audit entry and one-click rollback.

Mobile should not include the full XML Workshop. A phone screen is fine for choosing a tested preset or downloading a file, but full arbitrary XML editing should stay desktop-only.

Acceptance criteria:

- Owner can quickly see which server they are managing.
- Multi-server dashboards clearly show Cherno/Livo/profile context.
- Actions still post through existing Flask forms/API routes with existing permission checks.
- Every write action clearly shows the target DayZ server profile before submit.
- Every destructive action writes an audit entry with actor, target server, action, old value and new value.

Mobile navigation:

- Home
- Feeds
- Economy
- Events
- Presets
- Controls
- Members
- Billing
- Guides

The desktop dashboard can keep the full tool layout, but mobile should group the same tools around what the owner is trying to do instead of copying every desktop tab exactly.

## Phase 3 - Native iOS and Android Wrapper

Recommended stack:

- Capacitor or a similar native wrapper around the hosted dashboard.
- Native shell handles app icon, splash screen, in-app browser/webview, and optional push notifications.
- Backend remains Flask/Railway.

Why this route:

- One dashboard remains the source of truth.
- Less risk of breaking billing, Discord permissions, Nitrado actions, preset file downloads, or server-file workflows.
- Faster route to a real app-store style product.

Acceptance criteria:

- iOS and Android open the hosted dashboard safely.
- App login uses the same secure session/auth flow as the web dashboard.
- Native app contains no Nitrado, Discord, Stripe secret, FTP, or owner-only tokens.

## Phase 4 - App API and Push Notifications

Scope:

- Add read-only mobile API endpoints for app home/status cards.
- Add push notification support for server-critical events:
  - server offline
  - restart failed
  - ADM/feed stale
  - event upload failed
  - billing/payment action needed
  - raid weekend reminders

Acceptance criteria:

- Mobile API endpoints are permission-scoped by dashboard login and server access.
- Notifications only go to users with access to the affected server/profile.
- Every push event has an audit trail in the dashboard.

## Security Rules

- Never store Nitrado API tokens in the mobile app.
- Never store FTP passwords in the mobile app.
- Never store Stripe secret keys in the mobile app.
- Never let the app write raw DayZ XML directly.
- Direct server-file apply must go through the backend preset flow with backup, diff, validation, audit and rollback.
- Never let the app bypass dashboard feature access or owner restrictions.
- Every destructive action must still be backend checked and auditable.

## First Implementation Slice

1. Add `/manifest.webmanifest`.
2. Verify public/login/dashboard pages reference the manifest.
3. Add a short mobile-app plan to the repo.
4. Test the manifest endpoint locally.
5. Then review mobile layout for the dashboard start page and upgrade flow.
