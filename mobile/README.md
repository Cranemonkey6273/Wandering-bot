# Wandering Bot Mobile App

This folder is the real iPhone/Android app project shell for Wandering Bot.

It uses Capacitor so the installed app can run on Android and iOS while still loading the secure Wandering Bot backend at:

`https://dayzwanderingbot.com/app`

That is intentional. Nitrado tokens, Stripe secrets, Discord bot credentials, restart controls, XML writes, and billing checks must stay on the server. The phone app is the native shell and the server remains the source of truth.

## What Links

- The installed app opens `https://dayzwanderingbot.com/app`.
- The app allows Wandering Bot dashboard pages, Stripe Checkout, Discord, and Wandering Bot subdomains.
- Android deep links are registered for `wanderingbot://`, `/app`, `/login`, `/admin`, and `/owner`.
- Full verified Android App Links still need a release signing certificate and `/.well-known/assetlinks.json` on the website before Play Store release.

## Setup

Install Node.js 20 or newer first.

```powershell
cd C:\Users\Crane\Documents\Codex\wandering-bot-mapfix-clean-20260621113251\mobile
npm install
```

## Android

```powershell
npm run add:android
npm run sync
npm run open:android
```

Android Studio can then build a debug APK or a release AAB for Google Play.

Build a debug APK:

```powershell
npm run build:android:debug
```

The debug APK is created at:

```text
mobile\android\app\build\outputs\apk\debug\app-debug.apk
```

Build a release bundle:

```powershell
npm run build:android:release
```

The Play Store release bundle still needs a real signing key, privacy policy URL, support URL, screenshots, and final store listing text.

## iPhone / iPad

iOS builds require macOS, Xcode, and an Apple Developer account.

On a Mac:

```bash
cd mobile
npm install
npm run add:ios
npm run sync
npm run open:ios
```

Use Xcode to set signing, bundle ID, app icon, capabilities, and TestFlight/App Store upload.

## App ID

Current bundle/package ID:

`com.dayzwanderingbot.app`

Change this in `capacitor.config.json` before the first store submission if you want a different permanent ID.

## Important

The native app currently wraps the secure mobile dashboard. That is the correct first production path because the dashboard already owns logins, permissions, billing, server profiles, and sensitive actions.

To make it more store-ready later, add native-only features such as push notifications, saved device sessions, biometric unlock, native file downloads, and app notification badges.

## Assets

Production source assets live in `resources/`:

- `resources/icon.png` at 1024x1024.
- `resources/splash.png` at 2732x2732.

Generated Android launcher and splash images are committed under `android/app/src/main/res/`. If the source files change later, regenerate the Android images before building again.
