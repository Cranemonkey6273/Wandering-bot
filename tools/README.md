# Wandering-bot tools

Diagnostic CLI utilities that complement the in-bot CE XML generator.

## `validate_ce_xml.py`

Cross-file validator for the live Wandering-bot DayZ CE XML set. Run it after
each dashboard `Retry / Save` and **before** issuing a DayZ server restart to
confirm the live mission folder is internally consistent.

```bash
python tools/validate_ce_xml.py /path/to/dayzOffline.enoch
```

The folder must contain:

- `db/events.xml`
- `cfgeventspawns.xml`
- `cfgeventgroups.xml`
- `mapgroupproto.xml`
- `cfgspawnabletypes.xml`

The tool walks the cross-file relationships and reports any mismatch that
would cause DayZ to load an event definition but refuse to spawn it.

Exit codes:

- `0` ? clean (no errors, no warnings)
- `1` ? warnings only (with `--strict`)
- `2` ? at least one validation error

Run the unit tests with:

```bash
python -m unittest discover -s tests -v
```
