"""Tests for _check_commander_color_identity in cli.py."""

from __future__ import annotations

import pytest

from wizard.cli import _check_commander_color_identity
from wizard.models import DeckCard, DeckSuggestion, ScryfallCard


def _sc(name: str, color_identity: list[str]) -> ScryfallCard:
    return ScryfallCard(
        scryfall_id=f"id-{name}",
        name=name,
        set_code="tst",
        collector_number="1",
        mana_cost="",
        colors=color_identity,
        color_identity=color_identity,
        type_line="Creature",
        oracle_text="",
        keywords=[],
        legalities={"commander": "legal"},
        edhrec_rank=None,
        penny_rank=None,
        prices={},
        raw_json="{}",
    )


def _deck(commander: str, mainboard_names: list[str], format: str = "Commander") -> DeckSuggestion:
    return DeckSuggestion(
        deck_name="Test",
        format=format,
        commander=commander,
        mainboard=[DeckCard(quantity=1, name=n) for n in mainboard_names],
    )


def _lookup(*cards: ScryfallCard) -> dict[str, ScryfallCard]:
    return {c.name.lower(): c for c in cards}


# --- colorless commander ---

def test_colorless_commander_colored_card_is_violation() -> None:
    triade = _sc("Triade Marcial", [])
    plains = _sc("Plains", ["W"])
    lookup = _lookup(triade, plains)
    deck = _deck("Triade Marcial", ["Triade Marcial", "Plains"])
    violations = _check_commander_color_identity(deck, lookup)
    assert any("Plains" in v for v in violations)


def test_colorless_commander_colorless_card_is_ok() -> None:
    triade = _sc("Triade Marcial", [])
    sol_ring = _sc("Sol Ring", [])
    lookup = _lookup(triade, sol_ring)
    deck = _deck("Triade Marcial", ["Triade Marcial", "Sol Ring"])
    assert _check_commander_color_identity(deck, lookup) == []


def test_colorless_commander_wb_cards_are_violations() -> None:
    triade = _sc("Triade Marcial", [])
    go_blank = _sc("Go Blank", ["B"])
    swords = _sc("Swords to Plowshares", ["W"])
    lookup = _lookup(triade, go_blank, swords)
    deck = _deck("Triade Marcial", ["Triade Marcial", "Go Blank", "Swords to Plowshares"])
    violations = _check_commander_color_identity(deck, lookup)
    assert len(violations) == 2


# --- colored commander ---

def test_wb_commander_wb_card_is_ok() -> None:
    edgar = _sc("Edgar Markov", ["W", "B", "R"])
    child = _sc("Vampire Nighthawk", ["B"])
    lookup = _lookup(edgar, child)
    deck = _deck("Edgar Markov", ["Edgar Markov", "Vampire Nighthawk"])
    assert _check_commander_color_identity(deck, lookup) == []


def test_wb_commander_green_card_is_violation() -> None:
    teysa = _sc("Teysa, Orzhov Scion", ["W", "B"])
    llanowar = _sc("Llanowar Elves", ["G"])
    lookup = _lookup(teysa, llanowar)
    deck = _deck("Teysa, Orzhov Scion", ["Teysa, Orzhov Scion", "Llanowar Elves"])
    violations = _check_commander_color_identity(deck, lookup)
    assert any("Llanowar Elves" in v for v in violations)


def test_multicolor_card_within_identity_is_ok() -> None:
    atraxa = _sc("Atraxa", ["W", "U", "B", "G"])
    simic = _sc("Simic Card", ["U", "G"])
    lookup = _lookup(atraxa, simic)
    deck = _deck("Atraxa", ["Atraxa", "Simic Card"])
    assert _check_commander_color_identity(deck, lookup) == []


# --- commander itself is excluded from check ---

def test_commander_itself_not_flagged() -> None:
    triade = _sc("Triade Marcial", [])
    # The only card is the commander itself — should never flag itself.
    lookup = _lookup(triade)
    deck = _deck("Triade Marcial", ["Triade Marcial"])
    assert _check_commander_color_identity(deck, lookup) == []


# --- unknown cards (not in lookup) are skipped ---

def test_unknown_card_skipped() -> None:
    triade = _sc("Triade Marcial", [])
    lookup = _lookup(triade)
    # "Mystery Card" is not in the Scryfall lookup — can't validate, skip it.
    deck = _deck("Triade Marcial", ["Triade Marcial", "Mystery Card"])
    assert _check_commander_color_identity(deck, lookup) == []


def test_commander_not_in_lookup_skips_all() -> None:
    # If the commander itself can't be found, we can't determine allowed colors.
    sol_ring = _sc("Sol Ring", [])
    lookup = _lookup(sol_ring)
    deck = _deck("Unknown Commander", ["Unknown Commander", "Sol Ring"])
    assert _check_commander_color_identity(deck, lookup) == []


# --- non-Commander format ---

def test_non_commander_format_always_empty() -> None:
    bolt = _sc("Lightning Bolt", ["R"])
    island = _sc("Island", ["U"])
    lookup = _lookup(bolt, island)
    deck = _deck("", ["Lightning Bolt", "Island"], format="Modern")
    assert _check_commander_color_identity(deck, lookup) == []


def test_missing_commander_field_always_empty() -> None:
    bolt = _sc("Lightning Bolt", ["R"])
    lookup = _lookup(bolt)
    deck = DeckSuggestion(
        deck_name="Test",
        format="Commander",
        commander=None,
        mainboard=[DeckCard(quantity=1, name="Lightning Bolt")],
    )
    assert _check_commander_color_identity(deck, lookup) == []
