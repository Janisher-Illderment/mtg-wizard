# mtg-wizard

Build Magic: The Gathering decks from your ManaBox collection using Claude AI.

## Quick start

```bash
pip install -e ".[dev]"
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
wizard sync            # download Scryfall oracle_cards bulk data
wizard import-collection path/to/manabox.csv
wizard build --format Commander --colors WUB
```

## Commands

- `wizard sync` — download / refresh Scryfall oracle bulk cache (12h cooldown).
- `wizard import-collection <path>` — parse a ManaBox CSV.
  - `--mode replace` (default) wipes the existing collection first.
  - `--mode append` keeps existing rows.
  - `--yes` skips the replace confirmation.
  - `--verbose` prints parse warnings.
  - `--strict` aborts before insert if any warnings are produced.
- `wizard collection` — show collection statistics.
- `wizard build --format <fmt>` — ask Claude to build a deck.

## Configuration

All settings come from the environment (`.env` is loaded automatically).

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | *(required for `build`)* | Claude API key. |
| `WIZARD_DB_PATH` | `~/.wizard/cards.db` | SQLite cache path. |
| `WIZARD_MODEL` | `claude-sonnet-4-6` | Model for deck suggestions. |
| `WIZARD_MAX_OUTPUT_TOKENS` | `8192` | `max_tokens` passed to the API. |

## Migrations

### v0.2: FTS5 virtual table removed

The `cards_fts` full-text search virtual table was created but never queried
(YAGNI). It was removed to shrink the DB and speed up bulk upserts.

**If you already have a `~/.wizard/cards.db`**, delete it and re-sync:

```bash
rm ~/.wizard/cards.db   # or: del %USERPROFILE%\.wizard\cards.db on Windows
wizard sync
```

(New installs are unaffected.)
