"""Parse a ManaBox CSV collection export into CollectionCard objects."""

from __future__ import annotations

import csv
from pathlib import Path

from wizard.models import CollectionCard

# The 15-column ManaBox header, in order.
EXPECTED_COLUMNS: tuple[str, ...] = (
    "Name",
    "Set code",
    "Set name",
    "Collector number",
    "Foil",
    "Rarity",
    "Quantity",
    "ManaBox ID",
    "Scryfall ID",
    "Purchase price",
    "Misprint",
    "Altered",
    "Condition",
    "Language",
    "Purchase price currency",
)


def _parse_bool(raw: str) -> bool:
    """Parse ManaBox boolean strings ('Yes'/'No', case-insensitive)."""
    return raw.strip().lower() in {"yes", "true", "1", "foil"}


def _parse_optional_float(raw: str) -> float | None:
    """Parse an optional float, returning None on blank or invalid input."""
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _parse_int(raw: str, default: int = 0) -> int:
    """Parse an int, falling back to `default` on blank/invalid input."""
    stripped = raw.strip()
    if not stripped:
        return default
    try:
        return int(stripped)
    except ValueError:
        return default


def parse_manabox_csv(path: Path) -> list[CollectionCard]:
    """Parse a ManaBox export CSV at `path` into a list of CollectionCard."""
    # utf-8-sig transparently strips a BOM if present.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        cards: list[CollectionCard] = []
        for row in reader:
            # Skip fully blank rows (all values empty or whitespace).
            if not any((v or "").strip() for v in row.values()):
                continue
            name = (row.get("Name") or "").strip()
            if not name:
                # Rows without a card name are not meaningful.
                continue
            cards.append(
                CollectionCard(
                    name=name,
                    set_code=(row.get("Set code") or "").strip(),
                    set_name=(row.get("Set name") or "").strip(),
                    collector_number=(row.get("Collector number") or "").strip(),
                    foil=_parse_bool(row.get("Foil") or ""),
                    rarity=(row.get("Rarity") or "").strip(),
                    quantity=_parse_int(row.get("Quantity") or "", default=1),
                    manabox_id=(row.get("ManaBox ID") or "").strip(),
                    scryfall_id=(row.get("Scryfall ID") or "").strip(),
                    purchase_price=_parse_optional_float(row.get("Purchase price") or ""),
                    misprint=_parse_bool(row.get("Misprint") or ""),
                    altered=_parse_bool(row.get("Altered") or ""),
                    condition=(row.get("Condition") or "").strip(),
                    language=(row.get("Language") or "").strip(),
                    currency=(row.get("Purchase price currency") or "").strip(),
                )
            )
        return cards
