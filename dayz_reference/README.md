DayZ vanilla mission references for Wandering Bot.

Source: user-provided DayZ 1.29 vanilla mission zips for:
- dayzOffline.chernarusplus
- dayzOffline.enoch
- dayzOffline.sakhal

These files are used as read-only layout/classname references for CE XML,
gameplay JSON, environment territories, map groups, event groups, and loot
tables. The large binary areaflags.map files are intentionally excluded because
they are not XML/JSON/config layout sources and would bloat the repository.

Verification:
- The stored references match the supplied 1.29 mission archives after normalising Windows/Linux line endings and the optional final newline.
- Every bundled XML and JSON reference is checked by the automated test suite for valid syntax and the expected DayZ file root/schema before release.
- The AI may use a selected matching-map reference as a complete draft base, but it must validate every output and never automatically upload it to a live server.
