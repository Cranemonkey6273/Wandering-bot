# Wandering Bot — Changes by Emergent

**Original problem statement**
> "Fix my translation feature on the bot — it doesn't work the other way after I set it up.
> Expand the PVE quests with multiple themed progressive storylines (admin-gated, ticket-based completion)."

**Repository**: `Cranemonkey6273/Wandering-bot` (Python Discord bot)
**Working location in Emergent**: `/app/wandering-bot/`
**Feature branch**: `fix/translation-multirule-and-pve-campaigns`
**Patch file**: `/app/wandering-bot-changes.patch`

---

## What was implemented (Jan 2026)

### 1. Translation — multi-rule support (bug fix)
- Old behaviour: `config["translation"]` was a single dict, so every new
  `/translationconfig` call overwrote the previous one. Setting up A→B then
  B→A silently removed A→B.
- New behaviour: `config["translations"]` is a list. Every call **adds or
  updates** a rule. `maybe_translate_message` iterates all matching rules,
  so bidirectional/multi-channel translation just works.
- Legacy single-rule configs are migrated on first edit.
- New commands:
  - `/translationlist` — view all rules
  - `/translationremove rule_number:<n>` — delete one
  - `/translationclear` — wipe all
- `/translationconfig mode:off` with a `source_channel` removes only that rule;
  without one it wipes the server's rules entirely.

### 2. PVE quests — 5 new original themed campaigns (44 quests total)
All campaigns are appended to `PVE_CHALLENGE_BANK` under the `Quest Line` kind.

| Campaign | Quests | Theme |
| --- | --- | --- |
| Ashes of Chernarus | 8 | Abandoned-research-lab arc, moral closure |
| The Drifter's Ledger | 10 | Kindness/trade/redemption journey |
| Black Mountain Signal | 8 | Radio-tower mystery, paranoia, signal hunting |
| Tide Watchers | 8 | Coastal lighthouse keeper saga |
| Iron Convoy | 10 | Long-haul cargo / vehicle / convoy story |

Each quest has a unique title, escalating difficulty (Easy → Legendary),
narrative tips, and admin-chosen story rewards on top of base pennies.

### 3. PVE — Submit Completion button → auto-open ticket
- Every newly posted quest embed now carries a green **🎟️ Submit Completion** button.
- Clicking it creates a **private channel** under a `🎟️ PVE Quest Tickets` category,
  visible only to the requesting player, server admins, and the bot.
- Channel is pre-populated with the quest details and instructions for proof upload.
- Admins finalise with the existing `/pvecomplete quest_id:<...> member:@user` command
  inside the ticket — keeps the existing pay-out + chain-advance logic intact.
- Persistent custom_id (`pve_submit:<quest_code>`) handled by a new
  `on_interaction` listener — works across bot restarts.

---

## Next action items (handoff to user)
1. Review the diff in `/app/wandering-bot-changes.patch` (or `git log` on branch
   `fix/translation-multirule-and-pve-campaigns`).
2. Push the branch to GitHub yourself via Emergent's **Save to GitHub** feature
   (desktop browser) — main agent does **not** push with PATs.
3. Open the PR on GitHub from `fix/translation-multirule-and-pve-campaigns`
   → `main` and merge once you've reviewed.
4. After deploy, run `/translationconfig` twice with opposite source/target to
   verify the multi-rule fix, then run `/pvequestnow` to see the new ticket button.

## Backlog (deferred / future)
- P1: Add `/pvecampaigns` slash command to let players browse available
  campaigns and their progress.
- P1: Persist per-player quest progress so the bot only offers the **next**
  step of a campaign rather than random campaign quests.
- P2: Auto-archive ticket channels 24h after `/pvecomplete`.
- P2: Add quest-line completion badge / role reward.

## Known constraints
- Bot was developed outside Emergent; `/app/wandering-bot/` is a nested git
  repo. "Save to GitHub" pushes the **parent `/app` directory** to a repo —
  pushing changes back to `Cranemonkey6273/Wandering-bot` requires either:
  (a) using the patch file to apply on the user's local clone, or
  (b) treating the nested folder as the working dir for `git push`.
