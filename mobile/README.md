# Wandering Bot Mobile App

This folder is the real iPhone/Android app project shell for Wandering Bot.

It uses Capacitor so the installed app can run on Android and iOS while still loading the secure Wandering Bot backend at:

`https://dayzwanderingbot.com/app`

That is intentional. Nitrado tokens, Stripe secrets, Discord bot credentials, restart controls, XML writes, and billing checks must stay on the server. The phone app is the native shell and the server remains the source of truth.

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
