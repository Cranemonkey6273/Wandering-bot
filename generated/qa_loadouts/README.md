# QA full loadouts

These are offline draft files for the requested Chernarus kits. They are not
uploaded or linked to a live server.

- `QA_Red_NVG_Assault.json`: black kit, red boonie and red DryBag, M4A1 with
  optic/handguard/stock/suppressor and STANAG magazine, three 5.56 ammo boxes,
  second magazine, two bandages, map, two bacon cans, fire axe, belt with
  sheath/knife/canteen and two 9V batteries.
- `QA_Orange_NVG_Assault.json`: same kit, but orange boonie/orange DryBag,
  AKM with Kobra/handguard/stock/suppressor and AKM magazine, three 7.62x39
  ammo boxes, second magazine, two bandages, map, two spaghetti cans, fire axe,
  belt with sheath/knife/canteen and two 9V batteries.

## Important headgear caveat

The requested boonie + NVG headstrap combination depends on the target
platform's attachment-slot rules. These drafts keep the boonie in `Headgear`
and the NVG headstrap/goggles in the `Eyewear` set so the JSON remains explicit,
but the complete merged file should be checked in-game. If the platform rejects
both in those slots, use the NVG headstrap as the headgear item and carry the
boonie in the backpack; do not silently upload a conflicting slot layout.

Before use, validate the complete JSON, then add each path to the existing
`cfggameplay.json` under `PlayerData.spawnGearPresetFiles` (for example
`./custom/QA_Red_NVG_Assault.json`). Keep the existing paths; do not replace
the whole gameplay file with these presets.
