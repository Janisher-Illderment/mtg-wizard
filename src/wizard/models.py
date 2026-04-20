"""Typed dataclasses used across the wizard package."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CollectionCard:
    """A single physical card owned by the player (a ManaBox CSV row)."""

    name: str
    set_code: str
    set_name: str
    collector_number: str
    foil: bool
    rarity: str
    quantity: int
    manabox_id: str
    scryfall_id: str
    purchase_price: float | None
    misprint: bool
    altered: bool
    condition: str
    language: str
    currency: str


@dataclass
class ScryfallCard:
    """Enriched card metadata loaded from the Scryfall oracle bulk dump."""

    scryfall_id: str
    name: str
    set_code: str
    collector_number: str
    mana_cost: str
    colors: list[str]
    color_identity: list[str]
    type_line: str
    oracle_text: str
    keywords: list[str]
    legalities: dict[str, str]
    edhrec_rank: int | None
    penny_rank: int | None
    prices: dict[str, str | None]
    raw_json: str


@dataclass
class DeckCard:
    """A single entry in a deck list (mainboard or sideboard)."""

    quantity: int
    name: str
    set_code: str | None = None
    collector_number: str | None = None


@dataclass
class DeckSuggestion:
    """A complete deck suggestion returned by the Wizard."""

    deck_name: str
    format: str
    commander: str | None
    mainboard: list[DeckCard]
    sideboard: list[DeckCard] = field(default_factory=list)
    strategy: str = ""
    key_synergies: list[str] = field(default_factory=list)
