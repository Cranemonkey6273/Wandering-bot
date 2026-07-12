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

- Production icon and splash assets are in `mobile/resources/` and generated into the Android project.
- Android release signing variables are wired in `mobile/android/app/build.gradle`; create the private upload key outside the repo before release.
- `/.well-known/assetlinks.json` is available, but it will only publish a valid Android App Links file after `WANDERING_ANDROID_SHA256_FINGERPRINTS` is set to the release/upload certificate SHA-256 fingerprint.
- Privacy policy URL: `https://dayzwanderingbot.com/privacy`.
- Support URL: `https://dayzwanderingbot.com/support`.
- Terms URL: `https://dayzwanderingbot.com/terms`.
- Add screenshots for phone and tablet.
- Add native push notifications.
- Add native file download/share support for preset XML/JSON files.
- Add biometric unlock after the first dashboard login.
- Add app review-safe wording: this is a server-owner management tool, not a gambling or paid loot service.

Full Play Store prep notes are in `docs/play_store_readiness.md`.
