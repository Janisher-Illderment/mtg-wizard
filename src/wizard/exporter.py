"""Convert a DeckSuggestion into ManaBox-importable plain-text deck lists."""

from __future__ import annotations

from pathlib import Path

from wizard.models import DeckCard, DeckSuggestion


def _format_card_line(card: DeckCard) -> str:
    """Render one deck entry. Omit set_code/collector_number if either is blank."""
    if card.set_code and card.collector_number:
        return (
            f"{card.quantity} {card.name} "
            f"({card.set_code.upper()}) {card.collector_number}"
        )
    return f"{card.quantity} {card.name}"


def render_deck(deck: DeckSuggestion) -> str:
    """Render a DeckSuggestion to a ManaBox-importable plain-text string.

    Layout:
        // <deck_name> [<format>]
        // Strategy: <strategy>

        Commander
        1 <commander>

        Mainboard
        <quantity> <name> (<set_code>) <collector_number>
        ...

        Sideboard
        <quantity> <name>
        ...
    """
    lines: list[str] = []

    # Header comments — ManaBox ignores `//` lines on import but they document
    # the deck for humans reading the file.
    lines.append(f"// {deck.deck_name} [{deck.format}]")
    if deck.strategy:
        # Flatten any newlines in the strategy so the header stays a single line.
        strategy_single_line = " ".join(deck.strategy.split())
        lines.append(f"// Strategy: {strategy_single_line}")
    lines.append("")

    # Commander section (only for Commander decks).
    if deck.commander:
        lines.append("Commander")
        lines.append(f"1 {deck.commander}")
        lines.append("")

    # Mainboard section is always present — even if empty, it anchors the file.
    lines.append("Mainboard")
    for card in deck.mainboard:
        lines.append(_format_card_line(card))

    if deck.sideboard:
        lines.append("")
        lines.append("Sideboard")
        for card in deck.sideboard:
            lines.append(_format_card_line(card))

    # Trailing newline keeps POSIX tooling and ManaBox importer happy.
    return "\n".join(lines) + "\n"


def write_deck(deck: DeckSuggestion, path: Path) -> Path:
    """Write `deck` to `path` as ManaBox-importable text. Returns the path written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_deck(deck), encoding="utf-8")
    return path
