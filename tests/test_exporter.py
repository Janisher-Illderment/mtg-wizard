"""Tests for the ManaBox deck-text exporter."""

from __future__ import annotations

from pathlib import Path

from wizard.exporter import render_deck, write_deck
from wizard.models import DeckCard, DeckSuggestion


def _deck(
    *,
    commander: str | None = None,
    mainboard: list[DeckCard] | None = None,
    sideboard: list[DeckCard] | None = None,
    strategy: str = "Win through aggression.",
    format_name: str = "Commander",
) -> DeckSuggestion:
    return DeckSuggestion(
        deck_name="Test Deck",
        format=format_name,
        commander=commander,
        mainboard=mainboard
        or [
            DeckCard(quantity=4, name="Lightning Bolt", set_code="lea", collector_number="177"),
            DeckCard(quantity=20, name="Mountain"),
        ],
        sideboard=sideboard or [],
        strategy=strategy,
        key_synergies=[],
    )


def test_header_line_contains_deck_name_and_format() -> None:
    text = render_deck(_deck())
    assert "// Test Deck [Commander]" in text


def test_strategy_line_flattens_whitespace() -> None:
    text = render_deck(_deck(strategy="Win\n  through   aggression."))
    # Strategy must be a single `//` line — no embedded newlines.
    strategy_lines = [line for line in text.splitlines() if line.startswith("// Strategy:")]
    assert strategy_lines == ["// Strategy: Win through aggression."]


def test_commander_section_rendered_when_commander_set() -> None:
    text = render_deck(_deck(commander="Krenko, Mob Boss"))
    assert "Commander\n1 Krenko, Mob Boss" in text


def test_commander_section_absent_when_no_commander() -> None:
    text = render_deck(_deck(commander=None))
    # No bare "Commander" header should appear when the commander field is None.
    assert "\nCommander\n" not in text


def test_mainboard_with_set_and_collector_number() -> None:
    text = render_deck(_deck())
    assert "4 Lightning Bolt (LEA) 177" in text


def test_mainboard_without_set_falls_back_to_plain_line() -> None:
    text = render_deck(_deck())
    assert "20 Mountain" in text
    # A basic land with no set_code must NOT have trailing parentheses.
    assert "20 Mountain (" not in text


def test_set_code_is_uppercased() -> None:
    deck = _deck(
        mainboard=[DeckCard(quantity=1, name="Sol Ring", set_code="cmr", collector_number="472")]
    )
    text = render_deck(deck)
    assert "(CMR)" in text
    assert "(cmr)" not in text


def test_sideboard_section_rendered_when_present() -> None:
    deck = _deck(sideboard=[DeckCard(quantity=2, name="Smash to Smithereens")])
    text = render_deck(deck)
    assert "Sideboard\n2 Smash to Smithereens" in text


def test_sideboard_section_absent_when_empty() -> None:
    text = render_deck(_deck(sideboard=[]))
    assert "Sideboard" not in text


def test_output_ends_with_newline() -> None:
    text = render_deck(_deck())
    assert text.endswith("\n")


def test_write_deck_creates_parent_dirs_and_writes_file(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deck.txt"
    deck = _deck(commander="Krenko, Mob Boss")
    written = write_deck(deck, target)
    assert written == target
    content = target.read_text(encoding="utf-8")
    assert "// Test Deck [Commander]" in content
    assert "1 Krenko, Mob Boss" in content


def test_partial_set_info_omitted() -> None:
    # If only one of set_code / collector_number is present, the parentheses
    # block must be omitted entirely (matches the spec).
    deck = _deck(
        mainboard=[
            DeckCard(quantity=1, name="A", set_code="lea", collector_number=None),
            DeckCard(quantity=1, name="B", set_code=None, collector_number="42"),
        ]
    )
    text = render_deck(deck)
    assert "1 A\n" in text
    assert "1 B\n" in text
    assert "(LEA)" not in text
    assert "(lea)" not in text
