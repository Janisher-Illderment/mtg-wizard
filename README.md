# mtg-wizard

Build Magic: The Gathering decks from your ManaBox collection — with or without an AI API key.

Supports three deck-building backends:
- **algorithmic** — fully offline, no API key needed
- **ollama** — local LLM via [Ollama](https://ollama.com) (free, private)
- **anthropic** — Claude AI (requires `ANTHROPIC_API_KEY`)

---

## Requirements

- Python 3.11+
- A [ManaBox](https://manabox.app) collection export (CSV)

---

## Installation

### Linux / WSL (recommended)

```bash
# 1. Install venv if missing (Ubuntu/Debian)
sudo apt install python3.12-venv -y

# 2. Clone and set up
git clone https://github.com/Janisher-Illderment/mtg-wizard.git
cd mtg-wizard
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 3. Configure (copy template and edit if needed)
cp .env.example .env
```

### Windows (PowerShell)

```powershell
git clone https://github.com/Janisher-Illderment/mtg-wizard.git
cd mtg-wizard
python -m venv .venv
.venv\Scripts\activate
pip install -e .
cp .env.example .env
```

> **Note:** The venv must be active (`source .venv/bin/activate`) every time you open a new terminal.

---

## Quick start

```bash
# Step 1 — Download Scryfall card data (~450 MB, cached locally, runs once)
wizard sync

# Step 2 — Import your ManaBox collection
wizard import-collection /path/to/your_collection.csv

# Step 3 — Build a deck (no API key needed)
wizard build --format Modern --colors R --backend algorithmic
```

To save the deck as a file you can import back into ManaBox:

```bash
wizard build --format Commander --colors WUB --backend algorithmic --output my_deck.txt
```

---

## Backends

### Algorithmic (default when no API key is set)

No internet connection required after `wizard sync`. Uses synergy scoring from your collection.

```bash
wizard build --format Modern --backend algorithmic
```

### Ollama (local LLM)

Requires [Ollama](https://ollama.com/download) installed and running.

```bash
# Install a model
ollama pull llama3.1

# Start Ollama (if not already running)
ollama serve

# Build a deck with the local LLM
wizard build --format Modern --backend ollama
```

### Anthropic / Claude (cloud AI)

Add your API key to `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

```bash
wizard build --format Commander --colors RG --backend anthropic
```

When `WIZARD_BACKEND=auto` (the default), the wizard automatically uses Anthropic if the key is present, otherwise falls back to algorithmic.

---

## All commands

| Command | Description |
|---|---|
| `wizard sync` | Download / refresh Scryfall oracle data (12h cooldown; use `--force` to override) |
| `wizard import-collection <path>` | Import a ManaBox CSV into the local database |
| `wizard collection` | Show collection statistics |
| `wizard build` | Build a deck from your collection |

### `wizard build` options

| Option | Default | Description |
|---|---|---|
| `--format` | *(prompted)* | `Commander`, `Standard`, `Modern`, `Pioneer`, `Legacy`, `Pauper` |
| `--colors` | any | Color identity, e.g. `WUB`, `RG`, `WUBRG` |
| `--commander` | — | Preferred commander name (Commander format only) |
| `--backend` | `auto` | `auto`, `algorithmic`, `ollama`, `anthropic` |
| `--output` | — | Save deck as `.txt` for ManaBox import |

### `wizard import-collection` options

| Option | Description |
|---|---|
| `--mode replace` | (default) Wipe existing collection before import |
| `--mode append` | Keep existing rows |
| `--yes` | Skip replace confirmation |
| `--verbose` | Print parse warnings |
| `--strict` | Abort if any parse warnings are produced |

---

## Configuration

All settings are loaded from `.env` (copy from `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required only for `--backend anthropic` |
| `WIZARD_DB_PATH` | `~/.wizard/cards.db` | SQLite cache location |
| `WIZARD_MODEL` | `claude-sonnet-4-6` | Claude model for Anthropic backend |
| `WIZARD_MAX_OUTPUT_TOKENS` | `8192` | Max tokens for Claude response |
| `WIZARD_BACKEND` | `auto` | Default backend (`auto`, `algorithmic`, `ollama`, `anthropic`) |
| `WIZARD_OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `WIZARD_OLLAMA_MODEL` | `llama3.1` | Model to use with Ollama |

---

## Migrations

### v0.2: FTS5 virtual table removed

If you have an existing `~/.wizard/cards.db`, delete it and re-sync:

```bash
rm ~/.wizard/cards.db
wizard sync
```
