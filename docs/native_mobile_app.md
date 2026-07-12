# Native Mobile App Plan

Wandering Bot now has a native-app scaffold in `mobile/`.

## What It Is

- Capacitor app shell for Android and iOS.
- Native package ID: `com.dayzwanderingbot.app`.
- Opens `https://dayzwanderingbot.com/app`.
- Android deep links are registered for the app, login, admin, and owner dashboard URLs.
- Keeps secrets and server actions on the backend.

## Why It Still Uses `/app`

The installed app should not contain Nitrado tokens, Discord bot credentials, Stripe secret keys, XML upload code, or restart logic. Those stay behind the authenticated dashboard backend.

The `/app` route is the secure mobile interface. The native app is the store-installable shell around it.

## Build Path

1. Install Node.js 20+.
2. Run `npm install` inside `mobile/`.
3. Run `npm run add:android` and `npm run sync`.
4. Open Android Studio with `npm run open:android`.
5. For iOS, repeat on macOS with `npm run add:ios`, `npm run sync`, and `npm run open:ios`.

## Store Readiness Checklist

- Replace temporary icon with 1024x1024 production icon.
- Add splash image.
- Add Android release signing key and Play Store bundle signing.
- Add `/.well-known/assetlinks.json` after the release signing certificate fingerprint exists, so Android can verify Wandering Bot links directly into the app.
- Add privacy policy URL.
- Add support URL.
- Add screenshots for phone and tablet.
- Add native push notifications.
- Add native file download/share support for preset XML/JSON files.
- Add biometric unlock after the first dashboard login.
- Add app review-safe wording: this is a server-owner management tool, not a gambling or paid loot service.
