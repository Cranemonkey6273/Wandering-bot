# Wandering Bot App Store Checklist

This is the production checklist for the real Android and iPhone apps.

Prepared store copy and truthful production-access answers are in:

```text
mobile/PLAY_STORE_LISTING.md
mobile/PRODUCTION_ACCESS_ANSWERS.md
```

## Android

1. Keep the package name as `com.dayzwanderingbot.app` unless you want a permanent different ID before first release.
2. Build and upload the first release bundle in Google Play Console.
3. In Play Console, open `Setup > App integrity`.
4. Copy the `SHA-256 certificate fingerprint` from the app signing certificate.
5. Set this Railway variable on the website service:

```text
WANDERING_ANDROID_SHA256_FINGERPRINTS=AA:BB:CC:...
```

6. Set the public support email:

```text
WANDERING_SUPPORT_EMAIL=dayzwanderingbot@gmail.com
```

7. Check this URL returns JSON with your fingerprint:

```text
https://dayzwanderingbot.com/.well-known/assetlinks.json
```

Use the SHA-256 fingerprint from Google Play's **App signing key certificate**,
not the upload/debug certificate. The Android manifest verifies only the apex
`dayzwanderingbot.com` host; `www.dayzwanderingbot.com` is deliberately excluded
unless it is later given working DNS, HTTPS and its own association response.

8. Paste the reviewed copy from `PLAY_STORE_LISTING.md` into the Play listing and upload final screenshots with matching captions.
   The ready-to-upload portrait phone screenshots are in `mobile/store-assets/phone/`.
9. Use `PRODUCTION_ACCESS_ANSWERS.md` when the production-access questionnaire opens. Keep every answer factual for the build being submitted.
10. Confirm the first-use tour, dashboard review form, Google Play rating link and support links work in the uploaded closed-test build.
11. Upload Android version `1.0.4` (version code `5`) so the In-Game QR entry and newest offline guides reach existing users.

The Android Play build opens:

```text
https://dayzwanderingbot.com/app?source=native_android
```

That source flag hides Stripe checkout and upgrade buttons inside the native app. Keep plan purchases on the website unless Google Play Billing is added later.

## iPhone

1. iOS builds need macOS, Xcode and an Apple Developer account.
2. Use bundle ID `com.dayzwanderingbot.app` unless you choose a different permanent ID before first release.
3. In Apple Developer, create the app identifier and enable Associated Domains.
4. Set this Railway variable after you know the Apple Team ID:

```text
WANDERING_IOS_APP_ID=TEAMID.com.dayzwanderingbot.app
```

5. Check this URL returns JSON with the app ID:

```text
https://dayzwanderingbot.com/.well-known/apple-app-site-association
```

## Store Listing Links

Use these public links in Google Play and App Store review:

```text
https://dayzwanderingbot.com/privacy
https://dayzwanderingbot.com/terms
https://dayzwanderingbot.com/support
```

## What The App Does

The installed app opens the secure Wandering Bot mobile dashboard. Server secrets, Nitrado tokens, Discord bot credentials, Stripe secrets and XML writes stay on the backend.
