# Wandering Bot application emoji pack

This pack contains 111 static PNG application emojis and 12 bespoke animated GIF application emojis.

- `discord_static/`: 128 x 128 transparent PNG files.
- `premium_animated/`: transparent looping GIFs for the six adult reactions and six DayZ food/drink emojis.
- `animation_keyframes/`: high-resolution four-pose source sheets for the premium animations.
- `static/`: high-resolution source masters; these are not the files to upload to Discord.
- `emoji-manifest.json`: stable IDs, Discord-safe names, categories, and file paths.
- `wandering-emoji-contact-sheet.png`: visual index of the full set.

Every upload-ready file is below Discord's 256 KiB application-emoji limit. Animated files and application names use the `_a` suffix, so the 111 static and 12 animated emojis can be installed together without name collisions.

The collection includes reactions, DayZ survival gear, feeds and moderation symbols, Chernarus/Livonia/Sakhal sunglass reflections, six adult reaction bonuses, and six DayZ food bonuses: Tactical Bacon, baked beans, canned peaches, sardines, water bottle, and cooked steak.

Run `python tools/build_wandering_emoji_pack.py` from the repository root to rebuild the optimized static exports. Run `python tools/build_premium_wandering_animations.py` to rebuild, verify and package the 12 bespoke animations from their four-pose keyframe sheets.

The high-resolution `static/` masters and `animation_keyframes/` working sheets are intentionally kept out of the production Git repository so Railway and Vercel deployments do not download hundreds of megabytes of source artwork. The build scripts use those local working directories; the checked-in `discord_static/` and `premium_animated/` folders are the authoritative upload-ready assets.
