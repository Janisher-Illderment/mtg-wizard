"""Tests for the pure-algorithmic deck builder."""

from __future__ import annotations

import pytest

from wizard.algo_deckbuilder import suggest_deck_algo
from wizard.errors import DeckValidationError
from wizard.models import CollectionCard, ScryfallCard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sc(
    name: str,
    *,
    sid: str = "id-x",
    type_line: str = "Instant",
    color_identity: list[str] | None = None,
    keywords: list[str] | None = None,
    legalities: dict[str, str] | None = None,
    edhrec_rank: int | None = 100,
) -> ScryfallCard:
    return ScryfallCard(
        scryfall_id=sid,
        name=name,
        set_code="tst",
        collector_number="1",
        mana_cost="{1}",
        colors=color_identity or [],
        color_identity=color_identity or [],
        type_line=type_line,
        oracle_text="",
        keywords=keywords or [],
        legalities=legalities or {"commander": "legal", "modern": "legal"},
        edhrec_rank=edhrec_rank,
        penny_rank=None,
        prices={},
        raw_json="{}",
    )


def _coll(name: str, quantity: int = 4) -> CollectionCard:
    return CollectionCard(
        name=name,
        set_code="tst",
        set_name="Test",
        collector_number="1",
        foil=False,
        rarity="Common",
        quantity=quantity,
        manabox_id="",
        scryfall_id="",
        purchase_price=None,
        misprint=False,
        altered=False,
        condition="Near Mint",
        language="English",
        currency="EUR",
    )


def _make_large_pool(
    n_spells: int = 80,
    n_lands: int = 10,
    format_name: str = "Modern",
) -> list[tuple[CollectionCard, ScryfallCard, float]]:
    """Create a ranked pool large enough to build a full deck."""
    result: list[tuple[CollectionCard, ScryfallCard, float]] = []
    for i in range(n_spells):
        name = f"Spell{i}"
        sc = _sc(name, sid=f"s{i}", type_line="Instant", color_identity=["R"])
        result.append((_coll(name, 4), sc, 1.0 - i * 0.01))
    for i in range(n_lands):
        name = f"Land{i}"
        sc = _sc(name, sid=f"l{i}", type_line="Land", color_identity=[])
        result.append((_coll(name, 1), sc, 0.5 - i * 0.01))
    return result


def _make_commander_pool(
    n_spells: int = 80,
    n_lands: int = 10,
) -> list[tuple[CollectionCard, ScryfallCard, float]]:
    result: list[tuple[CollectionCard, ScryfallCard, float]] = []
    # Add one legendary creature as commander candidate
    sc_cmd = _sc(
        "Krenko, Mob Boss",
        sid="cmd-1",
        type_line="Legendary Creature — Goblin Warrior",
        color_identity=["R"],
    )
    result.append((_coll("Krenko, Mob Boss", 1), sc_cmd, 0.99))
    for i in range(n_spells):
        name = f"Spell{i}"
        sc = _sc(name, sid=f"s{i}", type_line="Sorcery", color_identity=["R"])
        result.append((_coll(name, 1), sc, 0.9 - i * 0.01))
    for i in range(n_lands):
        name = f"Land{i}"
        sc = _sc(name, sid=f"l{i}", type_line="Land", color_identity=[])
        result.append((_coll(name, 1), sc, 0.4))
    return result


# ---------------------------------------------------------------------------
# 60-card format tests
# ---------------------------------------------------------------------------

class TestSixtyCardFormat:
    def test_mainboard_total_exactly_60(self) -> None:
        pool = _make_large_pool()
        deck = suggest_deck_algo("Modern", pool, color_identity=["R"])
        total = sum(c.quantity for c in deck.mainboard)
        assert total == 60

    def test_no_non_basic_exceeds_4_copies(self) -> None:
        pool = _make_large_pool()
        deck = suggest_deck_algo("Modern", pool, color_identity=["R"])
        basics = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
        for card in deck.mainboard:
            if card.name not in basics:
                assert card.quantity <= 4, f"{card.name} has {card.quantity} copies"

    def test_sideboard_exactly_15_or_empty(self) -> None:
        pool = _make_large_pool()
        deck = suggest_deck_algo("Modern", pool, color_identity=["R"])
        side_total = sum(c.quantity for c in deck.sideboard)
        assert side_total in (0, 15)

    def test_small_collection_still_produces_valid_deck(self) -> None:
        """Collection with fewer cards than ideal — basics fill the gap."""
        pool = _make_large_pool(n_spells=5, n_lands=0)
        deck = suggest_deck_algo("Standard", pool, color_identity=["R"])
        total = sum(c.quantity for c in deck.mainboard)
        assert total == 60

    def test_format_stored_correctly(self) -> None:
        pool = _make_large_pool()
        deck = suggest_deck_algo("Pioneer", pool)
        assert deck.format == "Pioneer"
        assert deck.commander is None

    def test_deck_name_includes_format(self) -> None:
        pool = _make_large_pool()
        deck = suggest_deck_algo("Modern", pool, color_identity=["R"])
        assert "Modern" in deck.deck_name

    def test_deck_passes_validation(self) -> None:
        """suggest_deck_algo raises DeckValidationError on its own output only if buggy."""
        pool = _make_large_pool()
        # Should not raise.
        deck = suggest_deck_algo("Modern", pool, color_identity=["R"])
        assert deck is not None


# ---------------------------------------------------------------------------
# Commander format tests
# ---------------------------------------------------------------------------

class TestCommanderFormat:
    def test_mainboard_total_exactly_100(self) -> None:
        pool = _make_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["R"])
        total = sum(c.quantity for c in deck.mainboard)
        assert total == 100, f"Expected 100, got {total}"

    def test_commander_field_is_set(self) -> None:
        pool = _make_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["R"])
        assert deck.commander is not None
        assert deck.commander.strip() != ""

    def test_commander_hint_respected(self) -> None:
        pool = _make_commander_pool()
        deck = suggest_deck_algo(
            "Commander",
            pool,
            color_identity=["R"],
            commander_hint="Krenko, Mob Boss",
        )
        assert deck.commander == "Krenko, Mob Boss"

    def test_no_non_basic_exceeds_1_copy(self) -> None:
        pool = _make_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["R"])
        basics = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
        for card in deck.mainboard:
            if card.name not in basics:
                assert card.quantity == 1, f"{card.name} has {card.quantity} copies"

    def test_sideboard_is_empty(self) -> None:
        pool = _make_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["R"])
        assert deck.sideboard == []

    def test_small_collection_pads_to_100(self) -> None:
        pool = _make_commander_pool(n_spells=10, n_lands=2)
        deck = suggest_deck_algo("Commander", pool, color_identity=["R"])
        total = sum(c.quantity for c in deck.mainboard)
        assert total == 100

    def test_deck_passes_validation(self) -> None:
        pool = _make_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["R"])
        assert deck is not None
