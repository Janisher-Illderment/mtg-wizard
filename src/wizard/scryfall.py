"""Scryfall bulk-data download + per-card enrichment for the collection."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

from wizard.database import (
    bulk_upsert_cards,
    get_card_by_name,
    get_card_by_scryfall_id,
    get_cache_meta,
    init_db,
    set_cache_meta,
)
from wizard.models import CollectionCard, ScryfallCard

BULK_INDEX_URL = "https://api.scryfall.com/bulk-data"
BULK_TYPE_ORACLE = "oracle_cards"
CACHE_KEY_LAST_SYNC = "bulk_last_sync"
CACHE_KEY_BULK_TYPE = "bulk_type"
MIN_SYNC_INTERVAL_SECONDS = 12 * 60 * 60  # 12 hours


def _fetch_bulk_index(timeout: float = 30.0) -> dict:
    """Fetch the Scryfall bulk-data index and return the `oracle_cards` entry."""
    resp = requests.get(BULK_INDEX_URL, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    for entry in payload.get("data", []):
        if entry.get("type") == BULK_TYPE_ORACLE:
            return entry
    raise RuntimeError(f"Scryfall bulk-data index has no '{BULK_TYPE_ORACLE}' entry")


def _download_json(url: str, timeout: float = 300.0) -> list[dict]:
    """Stream-download a Scryfall bulk JSON file and parse it into a list."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError("Scryfall bulk file did not contain a JSON array")
    return data


def _seconds_since(ts_iso: str) -> float:
    """Return seconds elapsed since an ISO-8601 UTC timestamp string."""
    try:
        ts = datetime.fromisoformat(ts_iso)
    except ValueError:
        return float("inf")
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def download_bulk_data(db_path: Path, force: bool = False) -> int:
    """Download Scryfall oracle cards into the DB; returns card count written.

    Skips the download when the last sync was less than 12 hours ago unless
    `force=True`.
    """
    conn = init_db(db_path)
    try:
        last_sync = get_cache_meta(conn, CACHE_KEY_LAST_SYNC)
        if not force and last_sync and _seconds_since(last_sync) < MIN_SYNC_INTERVAL_SECONDS:
            # Return the current card count rather than re-downloading.
            cur = conn.execute("SELECT COUNT(*) AS n FROM cards")
            row = cur.fetchone()
            return int(row["n"]) if row is not None else 0

        index_entry = _fetch_bulk_index()
        download_uri = index_entry.get("download_uri")
        if not download_uri:
            raise RuntimeError("Scryfall bulk index entry is missing download_uri")
        cards = _download_json(download_uri)
        written = bulk_upsert_cards(conn, cards)
        set_cache_meta(conn, CACHE_KEY_LAST_SYNC, datetime.now(timezone.utc).isoformat())
        set_cache_meta(conn, CACHE_KEY_BULK_TYPE, BULK_TYPE_ORACLE)
        return written
    finally:
        conn.close()


def _row_to_scryfall_card(row: dict) -> ScryfallCard:
    """Convert a DB `cards` row dict into a ScryfallCard dataclass."""
    return ScryfallCard(
        scryfall_id=row["scryfall_id"],
        name=row["name"],
        set_code=row.get("set_code") or "",
        collector_number=row.get("collector_number") or "",
        mana_cost=row.get("mana_cost") or "",
        colors=json.loads(row.get("colors") or "[]"),
        color_identity=json.loads(row.get("color_identity") or "[]"),
        type_line=row.get("type_line") or "",
        oracle_text=row.get("oracle_text") or "",
        keywords=json.loads(row.get("keywords") or "[]"),
        legalities=json.loads(row.get("legalities") or "{}"),
        edhrec_rank=row.get("edhrec_rank"),
        penny_rank=row.get("penny_rank"),
        prices=json.loads(row.get("prices") or "{}"),
        raw_json=row.get("raw_json") or "{}",
    )


def enrich_collection(
    conn: sqlite3.Connection,
    collection: list[CollectionCard],
) -> list[tuple[CollectionCard, ScryfallCard | None]]:
    """Join the collection against the Scryfall cache; miss → None."""
    enriched: list[tuple[CollectionCard, ScryfallCard | None]] = []
    for card in collection:
        row: dict | None = None
        if card.scryfall_id:
            row = get_card_by_scryfall_id(conn, card.scryfall_id)
        if row is None and card.name:
            row = get_card_by_name(conn, card.name)
        enriched.append((card, _row_to_scryfall_card(row) if row else None))
    return enriched
