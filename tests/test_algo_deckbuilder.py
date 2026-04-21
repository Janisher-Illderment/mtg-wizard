"""Tests for the pure-algorithmic deck builder."""

from __future__ import annotations

import pytest

from wizard.algo_deckbuilder import suggest_deck_algo
from wizard.deckbuilder import _validate_deck
from wizard.errors import DeckValidationError
from wizard.models import CollectionCard, DeckCard, DeckSuggestion, ScryfallCard


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


# ---------------------------------------------------------------------------
# Commander color identity enforcement tests
# ---------------------------------------------------------------------------

def _make_colorless_commander_pool() -> list[tuple[CollectionCard, ScryfallCard, float]]:
    """Pool with a colorless legendary commander and a mix of colorless + colored cards."""
    result: list[tuple[CollectionCard, ScryfallCard, float]] = []
    cmd = _sc(
        "The Warring Triad",
        sid="cmd-colorless",
        type_line="Legendary Artifact Creature — Construct",
        color_identity=[],
    )
    result.append((_coll("The Warring Triad", 1), cmd, 0.99))
    for i in range(40):
        sc = _sc(f"WhiteSpell{i}", sid=f"w{i}", type_line="Creature", color_identity=["W"])
        result.append((_coll(f"WhiteSpell{i}", 1), sc, 0.8 - i * 0.01))
    for i in range(40):
        sc = _sc(f"BlackSpell{i}", sid=f"b{i}", type_line="Creature", color_identity=["B"])
        result.append((_coll(f"BlackSpell{i}", 1), sc, 0.7 - i * 0.01))
    for i in range(20):
        sc = _sc(f"ColorlessSpell{i}", sid=f"c{i}", type_line="Artifact", color_identity=[])
        result.append((_coll(f"ColorlessSpell{i}", 1), sc, 0.6 - i * 0.01))
    for i in range(10):
        sc = _sc(f"WastesLand{i}", sid=f"wl{i}", type_line="Land", color_identity=[])
        result.append((_coll(f"WastesLand{i}", 1), sc, 0.3))
    return result


class TestCommanderColorIdentityEnforcement:
    def test_colorless_commander_no_colored_cards(self) -> None:
        """Colorless commander must produce an all-colorless deck even with WB --colors."""
        pool = _make_colorless_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["W", "B"])
        assert deck.commander == "The Warring Triad"
        colored = [
            c for c in deck.mainboard
            if c.name not in {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
            and c.name != deck.commander
            and any(x in c.name for x in ("White", "Black"))
        ]
        assert colored == [], f"Colored cards found in colorless deck: {[c.name for c in colored]}"

    def test_colorless_commander_deck_name_uses_commander_identity(self) -> None:
        pool = _make_colorless_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["W", "B"])
        # Deck name should reflect the commander's identity (C), not the user's --colors (WB).
        assert deck.deck_name.startswith("C ")

    def test_colorless_commander_total_still_100(self) -> None:
        pool = _make_colorless_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["W", "B"])
        total = sum(c.quantity for c in deck.mainboard)
        assert total == 100

    def test_colorless_commander_uses_wastes_not_colored_basics(self) -> None:
        """Colorless commander deck must use Wastes, never Plains/Swamp/etc."""
        pool = _make_colorless_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["W", "B"])
        colored_basics = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
        bad = [c for c in deck.mainboard if c.name in colored_basics]
        assert bad == [], f"Colored basic lands found in colorless deck: {[c.name for c in bad]}"

    def test_wb_request_picks_wb_commander_over_colorless(self) -> None:
        """When a WB commander is available, it should be preferred over a colorless one."""
        result: list[tuple[CollectionCard, ScryfallCard, float]] = []
        colorless_cmd = _sc(
            "Emrakul, the Aeons Torn",
            sid="cmd-c",
            type_line="Legendary Creature — Eldrazi",
            color_identity=[],
        )
        result.append((_coll("Emrakul, the Aeons Torn", 1), colorless_cmd, 0.999))
        wb_cmd = _sc(
            "Teysa Karlov",
            sid="cmd-wb",
            type_line="Legendary Creature — Human Advisor",
            color_identity=["W", "B"],
        )
        result.append((_coll("Teysa Karlov", 1), wb_cmd, 0.95))
        for i in range(80):
            sc = _sc(f"WBSpell{i}", sid=f"wb{i}", type_line="Creature", color_identity=["W", "B"])
            result.append((_coll(f"WBSpell{i}", 1), sc, 0.5 - i * 0.005))
        for i in range(10):
            sc = _sc(f"CL{i}", sid=f"cl{i}", type_line="Land", color_identity=[])
            result.append((_coll(f"CL{i}", 1), sc, 0.3))
        deck = suggest_deck_algo("Commander", result, color_identity=["W", "B"])
        assert deck.commander == "Teysa Karlov", (
            f"Expected WB commander but got: {deck.commander}"
        )

    def test_colored_commander_filters_correctly(self) -> None:
        """WB commander should exclude R/G/U cards from the pool."""
        result: list[tuple[CollectionCard, ScryfallCard, float]] = []
        cmd = _sc("Teysa Karlov", sid="cmd-wb", type_line="Legendary Creature — Human Advisor",
                  color_identity=["W", "B"])
        result.append((_coll("Teysa Karlov", 1), cmd, 0.99))
        for i in range(50):
            sc = _sc(f"WBSpell{i}", sid=f"wb{i}", type_line="Creature", color_identity=["W", "B"])
            result.append((_coll(f"WBSpell{i}", 1), sc, 0.8 - i * 0.01))
        for i in range(20):
            sc = _sc(f"GreenSpell{i}", sid=f"g{i}", type_line="Creature", color_identity=["G"])
            result.append((_coll(f"GreenSpell{i}", 1), sc, 0.9))  # higher score — should be excluded
        for i in range(10):
            sc = _sc(f"CL{i}", sid=f"cl{i}", type_line="Land", color_identity=[])
            result.append((_coll(f"CL{i}", 1), sc, 0.4))
        deck = suggest_deck_algo("Commander", result, color_identity=["W", "B"])
        green_in_deck = [c for c in deck.mainboard if "Green" in c.name]
        assert green_in_deck == [], f"Green cards leaked into WB deck: {[c.name for c in green_in_deck]}"


# ---------------------------------------------------------------------------
# _fill_basics / land distribution regression tests
# ---------------------------------------------------------------------------

class TestBasicLandDistribution:
    def test_colorless_commander_wastes_are_present(self) -> None:
        """Colorless deck must contain at least one Wastes entry."""
        pool = _make_colorless_commander_pool()
        deck = suggest_deck_algo("Commander", pool, color_identity=["W", "B"])
        wastes = [c for c in deck.mainboard if c.name == "Wastes"]
        assert wastes, "Expected Wastes in a colorless commander deck"

    def test_mono_color_commander_only_that_basic(self) -> None:
        """Mono-red commander: basic lands must be only Mountains."""
        pool = _make_commander_pool()  # Krenko (R) + red spells
        deck = suggest_deck_algo("Commander", pool, color_identity=["R"])
        basics = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
        wrong_basics = [
            c for c in deck.mainboard
            if c.name in basics and c.name != "Mountain"
        ]
        assert wrong_basics == [], f"Non-Mountain basics in mono-R deck: {[c.name for c in wrong_basics]}"

    def test_five_color_commander_uses_all_basic_types(self) -> None:
        """WUBRG commander: deck should include all five colored basic land types."""
        result: list[tuple[CollectionCard, ScryfallCard, float]] = []
        cmd = _sc(
            "Progenitus",
            sid="cmd-wubrg",
            type_line="Legendary Creature — Hydra Avatar",
            color_identity=["W", "U", "B", "R", "G"],
        )
        result.append((_coll("Progenitus", 1), cmd, 0.99))
        for i in range(80):
            sc = _sc(f"Spell{i}", sid=f"s{i}", type_line="Creature", color_identity=["W", "U", "B", "R", "G"])
            result.append((_coll(f"Spell{i}", 1), sc, 0.8 - i * 0.005))
        deck = suggest_deck_algo("Commander", result, color_identity=["W", "U", "B", "R", "G"])
        basic_names = {c.name for c in deck.mainboard if c.name in {"Plains", "Island", "Swamp", "Mountain", "Forest"}}
        assert basic_names == {"Plains", "Island", "Swamp", "Mountain", "Forest"}, (
            f"Expected all five basic types, got: {basic_names}"
        )
        wastes = [c for c in deck.mainboard if c.name == "Wastes"]
        assert wastes == [], "WUBRG deck should not contain Wastes"

    def test_commander_hint_colorless_overrides_color_preference(self) -> None:
        """Explicit colorless commander hint with --colors WB still builds a colorless deck."""
        result: list[tuple[CollectionCard, ScryfallCard, float]] = []
        colorless_cmd = _sc(
            "Emrakul, the Aeons Torn",
            sid="cmd-c",
            type_line="Legendary Creature — Eldrazi",
            color_identity=[],
        )
        result.append((_coll("Emrakul, the Aeons Torn", 1), colorless_cmd, 0.999))
        wb_cmd = _sc(
            "Teysa Karlov",
            sid="cmd-wb",
            type_line="Legendary Creature — Human Advisor",
            color_identity=["W", "B"],
        )
        result.append((_coll("Teysa Karlov", 1), wb_cmd, 0.95))
        for i in range(80):
            sc = _sc(f"ColorlessSpell{i}", sid=f"c{i}", type_line="Artifact", color_identity=[])
            result.append((_coll(f"ColorlessSpell{i}", 1), sc, 0.5 - i * 0.005))
        deck = suggest_deck_algo(
            "Commander",
            result,
            color_identity=["W", "B"],
            commander_hint="Emrakul, the Aeons Torn",
        )
        assert deck.commander == "Emrakul, the Aeons Torn"
        colored_basics = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
        bad = [c for c in deck.mainboard if c.name in colored_basics]
        assert bad == [], f"Colored basics in hinted colorless deck: {[c.name for c in bad]}"


# ---------------------------------------------------------------------------
# _validate_deck unit tests (colored-basics CR 903.5d check)
# ---------------------------------------------------------------------------

class TestValidateDeckColoredBasics:
    def _commander_deck(self, cards: list[DeckCard]) -> DeckSuggestion:
        return DeckSuggestion(
            deck_name="Test",
            format="Commander",
            commander="Test Commander",
            mainboard=cards,
            sideboard=[],
        )

    def test_colored_basic_in_colorless_deck_is_violation(self) -> None:
        cards = [DeckCard(quantity=1, name="Test Commander")]
        cards += [DeckCard(quantity=1, name=f"Artifact{i}") for i in range(60)]
        cards += [DeckCard(quantity=38, name="Plains")]
        # Pad to 100
        deck = self._commander_deck(cards[:1] + cards[1:62] + [DeckCard(quantity=38, name="Plains")])
        violations = _validate_deck(deck, commander_color_identity=[])
        assert any("Plains" in v and "CR 903.5d" in v for v in violations)

    def test_wastes_in_colorless_deck_is_not_a_violation(self) -> None:
        cards = [DeckCard(quantity=1, name="Test Commander")]
        cards += [DeckCard(quantity=1, name=f"Artifact{i}") for i in range(61)]
        cards += [DeckCard(quantity=38, name="Wastes")]
        deck = self._commander_deck(cards)
        violations = _validate_deck(deck, commander_color_identity=[])
        land_violations = [v for v in violations if "Wastes" in v and "CR 903.5d" in v]
        assert land_violations == []

    def test_colored_basic_without_commander_ci_not_flagged(self) -> None:
        """When commander_color_identity is not provided, no CR 903.5d check runs."""
        cards = [DeckCard(quantity=1, name="Test Commander")]
        cards += [DeckCard(quantity=1, name=f"Spell{i}") for i in range(61)]
        cards += [DeckCard(quantity=38, name="Plains")]
        deck = self._commander_deck(cards)
        violations = _validate_deck(deck)  # no commander_color_identity
        land_violations = [v for v in violations if "CR 903.5d" in v]
        assert land_violations == []
