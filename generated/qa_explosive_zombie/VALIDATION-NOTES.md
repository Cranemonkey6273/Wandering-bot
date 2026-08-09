# Explosive/flash-zombie draft — validation notes

This is the safe output from the QA scenario. It is a merge-only XML block,
not a complete replacement file. Merge it into the existing
`cfgspawnabletypes.xml` record for `ZmbM_priestPopSkinny`.

## What this does

- Keeps the existing `foodHermit` cargo preset.
- Adds one `FlashGrenade` with a 100% cargo chance to that zombie type.
- Uses matching XML start/end tags and no trailing-comma style errors.

## What it does not do

Putting a grenade in zombie cargo does **not** make it detonate automatically
when the zombie dies. On vanilla console this file can provide carried/cargo
items only. An on-death explosion needs a supported script/mod mechanism (and
must be checked against the target platform); do not promise that behaviour
from `cfgspawnabletypes.xml` alone.

## Dependency check

- `db/types.xml`: no edit required; `FlashGrenade` already exists in the
  bundled DayZ 1.29 Chernarus reference (`category="explosives"`).
- `db/events.xml`: no edit required when using the existing
  `InfectedReligious` event, because it already spawns
  `ZmbM_priestPopSkinny`.
- `cfgeventspawns.xml`: no edit required for the existing event.
- If a different zombie classname or a new event is requested, re-check the
  selected map/version reference and keep the event name/classname links
  exact before producing any additional files.

## Safe application order

1. Back up the complete live `cfgspawnabletypes.xml`.
2. Merge the block into the existing `<type name="ZmbM_priestPopSkinny">`.
3. Validate the complete merged XML and confirm there is only one matching
   `<type>` record.
4. Review the diff; only then consider a guarded upload and restart.
