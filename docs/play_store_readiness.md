# Wandering Bot Google Play Readiness

## App Identity

- App name: `Wandering Bot`
- Android package name: `com.dayzwanderingbot.app`
- Website: `https://dayzwanderingbot.com`
- App start URL: `https://dayzwanderingbot.com/app`
- Privacy policy URL: `https://dayzwanderingbot.com/privacy`
- Support URL: `https://dayzwanderingbot.com/support`
- Terms URL: `https://dayzwanderingbot.com/terms`

## Store Listing Draft

Short description:

```text
DayZ server dashboard for killfeeds, feeds, events, restarts, shops and admin tools.
```

Full description:

```text
Wandering Bot is a DayZ server-owner dashboard for PC, PlayStation and Xbox communities.

Use the app to open your secure Wandering Bot dashboard from your phone, review live Discord feeds, check server status, manage shop and economy tools, open restart schedules, review airdrops and event queues, inspect zones and radar, and reach your full dashboard when deeper setup is needed.

Built for owners and trusted admins, Wandering Bot keeps sensitive actions on the backend. Nitrado tokens, FTP credentials, Discord bot credentials, Stripe secrets, restart controls and XML upload workflows are not stored inside the mobile app.

Main features:
- DayZ killfeed and ADM-style Discord feeds
- Live connect, disconnect, damage, building, placed item, flag and radar feed previews
- Server-owner dashboard access
- PC, PlayStation and Xbox DayZ community support
- Nitrado server workflow support
- Airdrops, animal drops, zombie hordes and live event tools
- Scheduled restarts, raid reminders and vehicle reset workflows
- Shop, economy, member and moderation tools
- Preset file and guide access for server owners

Wandering Bot is not affiliated with Bohemia Interactive, Discord, Nitrado, Stripe, Google or Apple.
```

## App Category

Recommended Google Play category:

```text
Tools
```

Secondary positioning:

```text
Productivity / Server owner utility
```

## Data Safety Notes

Use this as the starting point for the Play Console Data Safety form:

- Account/login data: used for dashboard authentication.
- User identifiers: Discord IDs, server IDs, role IDs and linked gamertags may be used to route dashboard access and server feeds.
- App activity: dashboard actions, feed routes and server control actions may be stored for audit and support.
- Payment info: payments are handled by Stripe or external checkout; Wandering Bot should not store raw card data.
- Diagnostics: errors, feed status, upload warnings and server status may be logged for support.

Sensitive credentials stay server-side:

- Nitrado API tokens
- FTP credentials
- Discord bot tokens
- Stripe secret keys
- XML upload logic

## Android Release Signing

Do not commit keystores or passwords.

Set these environment variables before building a signed release:

```powershell
$env:WANDERING_ANDROID_KEYSTORE="C:\secure\wandering-bot-upload.jks"
$env:WANDERING_ANDROID_KEYSTORE_PASSWORD="your-keystore-password"
$env:WANDERING_ANDROID_KEY_ALIAS="wandering-bot-upload"
$env:WANDERING_ANDROID_KEY_PASSWORD="your-key-password"
```

Then build:

```powershell
cd C:\Users\Crane\Documents\Codex\wandering-bot-mapfix-clean-20260621113251\mobile
npm run build:android:release
```

The output bundle is:

```text
mobile\android\app\build\outputs\bundle\release\app-release.aab
```

## Android App Links

The app has intent filters for:

- `https://dayzwanderingbot.com/app`
- `https://dayzwanderingbot.com/login`
- `https://dayzwanderingbot.com/admin`
- `https://dayzwanderingbot.com/owner`
- the same paths on `www.dayzwanderingbot.com`
- `wanderingbot://`

After the release or upload certificate SHA-256 fingerprint is known, set:

```text
WANDERING_ANDROID_SHA256_FINGERPRINTS=AA:BB:CC:...
```

The website will then serve:

```text
https://dayzwanderingbot.com/.well-known/assetlinks.json
```

Until that fingerprint is set, the endpoint returns a setup error instead of publishing an invalid verification file.

## Screenshot Checklist

Capture these from a phone-sized emulator before Play Store submission:

- Login screen
- Mobile app home
- Feeds tab
- Quick actions
- Server controls
- Upgrade/plans section
- Guides/preset downloads

Avoid showing private server IDs, passwords, tokens, live customer data or private Discord channels.
