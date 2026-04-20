"""SQLite storage for Scryfall card cache and the player's collection."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from wizard.models import CollectionCard

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS cards (
        scryfall_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        set_code TEXT,
        collector_number TEXT,
        mana_cost TEXT,
        colors TEXT,
        color_identity TEXT,
        type_line TEXT,
        oracle_text TEXT,
        keywords TEXT,
        legalities TEXT,
        edhrec_rank INTEGER,
        penny_rank INTEGER,
        prices TEXT,
        raw_json TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
        name,
        oracle_text,
        type_line,
        content='cards',
        content_rowid='rowid'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS collection (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scryfall_id TEXT REFERENCES cards(scryfall_id),
        name TEXT NOT NULL,
        set_code TEXT,
        collector_number TEXT,
        quantity INTEGER NOT NULL DEFAULT 1,
        foil INTEGER NOT NULL DEFAULT 0,
        condition TEXT,
        language TEXT,
        imported_at TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cache_meta (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name)",
    "CREATE INDEX IF NOT EXISTS idx_collection_scryfall ON collection(scryfall_id)",
    "CREATE INDEX IF NOT EXISTS idx_collection_name ON collection(name)",
)


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create (if needed) and open the wizard SQLite database at `db_path`."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for statement in SCHEMA:
        conn.execute(statement)
    conn.commit()
    return conn


def _now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _card_row_from_scryfall(card: dict) -> tuple:
    """Serialize a raw Scryfall JSON card dict into a DB row tuple."""
    return (
        card.get("id"),
        card.get("name"),
        card.get("set"),
        card.get("collector_number"),
        card.get("mana_cost", ""),
        json.dumps(card.get("colors", []), sort_keys=True),
        json.dumps(card.get("color_identity", []), sort_keys=True),
        card.get("type_line", ""),
        card.get("oracle_text", ""),
        json.dumps(card.get("keywords", []), sort_keys=True),
        json.dumps(card.get("legalities", {}), sort_keys=True),
        card.get("edhrec_rank"),
        card.get("penny_rank"),
        json.dumps(card.get("prices", {}), sort_keys=True),
        json.dumps(card, sort_keys=True),
        _now_iso(),
    )


def bulk_upsert_cards(conn: sqlite3.Connection, cards: list[dict]) -> int:
    """Upsert a batch of Scryfall card dicts; returns the number written."""
    rows = [_card_row_from_scryfall(c) for c in cards if c.get("id")]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO cards (
            scryfall_id, name, set_code, collector_number, mana_cost,
            colors, color_identity, type_line, oracle_text, keywords,
            legalities, edhrec_rank, penny_rank, prices, raw_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scryfall_id) DO UPDATE SET
            name = excluded.name,
            set_code = excluded.set_code,
            collector_number = excluded.collector_number,
            mana_cost = excluded.mana_cost,
            colors = excluded.colors,
            color_identity = excluded.color_identity,
            type_line = excluded.type_line,
            oracle_text = excluded.oracle_text,
            keywords = excluded.keywords,
            legalities = excluded.legalities,
            edhrec_rank = excluded.edhrec_rank,
            penny_rank = excluded.penny_rank,
            prices = excluded.prices,
            raw_json = excluded.raw_json,
            updated_at = excluded.updated_at
        """,
        rows,
    )
    # Rebuild FTS index so searches reflect the new rows.
    conn.execute("INSERT INTO cards_fts(cards_fts) VALUES('rebuild')")
    conn.commit()
    return len(rows)


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert a sqlite3.Row into a plain dict (or None if empty)."""
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def get_card_by_scryfall_id(conn: sqlite3.Connection, scryfall_id: str) -> dict | None:
    """Look up a single card by Scryfall UUID; returns None if absent."""
    cur = conn.execute("SELECT * FROM cards WHERE scryfall_id = ?", (scryfall_id,))
    return _row_to_dict(cur.fetchone())


def get_card_by_name(conn: sqlite3.Connection, name: str) -> dict | None:
    """Look up a single card by exact name (case-insensitive)."""
    cur = conn.execute(
        "SELECT * FROM cards WHERE LOWER(name) = LOWER(?) LIMIT 1",
        (name,),
    )
    return _row_to_dict(cur.fetchone())


def insert_collection(conn: sqlite3.Connection, cards: list[CollectionCard]) -> int:
    """Insert CollectionCard rows; returns the number inserted."""
    rows = [
        (
            card.scryfall_id or None,
            card.name,
            card.set_code or None,
            card.collector_number or None,
            card.quantity,
            1 if card.foil else 0,
            card.condition or None,
            card.language or None,
        )
        for card in cards
    ]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO collection (
            scryfall_id, name, set_code, collector_number,
            quantity, foil, condition, language
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_collection(conn: sqlite3.Connection) -> list[dict]:
    """Return every row in the collection table as a list of dicts."""
    cur = conn.execute("SELECT * FROM collection ORDER BY name")
    return [_row_to_dict(row) or {} for row in cur.fetchall()]


def get_cache_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Read a scalar value from the cache_meta table."""
    cur = conn.execute("SELECT value FROM cache_meta WHERE key = ?", (key,))
    row = cur.fetchone()
    return row["value"] if row is not None else None


def set_cache_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Write (upsert) a scalar value into the cache_meta table."""
    conn.execute(
        """
        INSERT INTO cache_meta(key, value, updated_at) VALUES (?, ?, datetime('now'))
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = datetime('now')
        """,
        (key, value),
    )
    conn.commit()
