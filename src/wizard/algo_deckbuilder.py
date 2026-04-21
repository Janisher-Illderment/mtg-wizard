"""Pure-algorithmic deck builder — no external API required.

Constructs a valid deck by greedily selecting the highest-synergy cards
from the pre-ranked collection, applying format rules locally.
"""

from __future__ import annotations

from collections import Counter

from wizard.deckbuilder import _validate_deck
from wizard.errors import DeckValidationError
from wizard.models import CollectionCard, DeckCard, DeckSuggestion, ScryfallCard

_BASIC_LAND_NAMES: frozenset[str] = frozenset(
    {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
)

_COLOR_TO_BASIC: dict[str, str] = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}

_SIXTY_CARD_FORMATS: frozenset[str] = frozenset(
    {"Standard", "Modern", "Pioneer", "Legacy", "Vintage", "Pauper"}
)


def _is_land(sc: ScryfallCard) -> bool:
    return "Land" in sc.type_line


def _is_legendary_creature(sc: ScryfallCard) -> bool:
    return "Legendary" in sc.type_line and "Creature" in sc.type_line


def _fill_basics(count: int, color_identity: list[str] | None) -> list[DeckCard]:
    """Return DeckCards for `count` basic lands distributed evenly by color."""
    if count <= 0:
        return []
    if color_identity is None:
        colors: list[str] = list(_COLOR_TO_BASIC.keys())
    else:
        colors = color_identity
    basics = [_COLOR_TO_BASIC[c] for c in colors if c in _COLOR_TO_BASIC]
    if not basics:
        # Colorless identity (empty list) — Wastes is the colorless basic land.
        basics = ["Wastes"]
    per = count // len(basics)
    remainder = count % len(basics)
    result: list[DeckCard] = []
    for i, name in enumerate(basics):
        qty = per + (1 if i < remainder else 0)
        if qty > 0:
            result.append(DeckCard(quantity=qty, name=name))
    return result


def _top_keywords(
    ranked: list[tuple[CollectionCard, ScryfallCard, float]],
    n: int = 3,
) -> list[str]:
    counter: Counter[str] = Counter()
    for _, sc, _ in ranked:
        counter.update(kw.lower() for kw in sc.keywords)
    return [kw for kw, _ in counter.most_common(n)]


def _dedupe_by_name(
    cards: list[tuple[CollectionCard, ScryfallCard, float]],
) -> list[tuple[CollectionCard, ScryfallCard, float]]:
    seen: set[str] = set()
    result: list[tuple[CollectionCard, ScryfallCard, float]] = []
    for item in cards:
        name = item[1].name
        if name not in seen:
            seen.add(name)
            result.append(item)
    return result


def _adjust_to_total(
    mainboard: list[DeckCard],
    target: int,
    color_identity: list[str] | None,
) -> list[DeckCard]:
    """Trim or pad the mainboard to exactly `target` cards using basic lands."""
    total = sum(c.quantity for c in mainboard)
    if total < target:
        extra = _fill_basics(target - total, color_identity)
        return mainboard + extra
    if total > target:
        excess = total - target
        result = list(mainboard)
        while excess > 0 and result:
            last = result[-1]
            if last.quantity > excess:
                result[-1] = DeckCard(
                    quantity=last.quantity - excess,
                    name=last.name,
                    set_code=last.set_code,
                    collector_number=last.collector_number,
                )
                excess = 0
            else:
                excess -= last.quantity
                result.pop()
        return result
    return mainboard


def _build_commander_deck(
    ranked: list[tuple[CollectionCard, ScryfallCard, float]],
    color_identity: list[str] | None,
    commander_hint: str | None,
) -> DeckSuggestion:
    TARGET_LANDS = 38
    TOTAL_CARDS = 100

    # Select commander: prefer hint, else top-ranked legendary creature
    commander_name: str | None = None
    commander_idx: int = -1

    if commander_hint:
        for i, (_, sc, _) in enumerate(ranked):
            if sc.name.lower() == commander_hint.lower():
                commander_name = sc.name
                commander_idx = i
                break

    if commander_name is None and color_identity:
        # Prefer a commander whose color identity exactly matches the request
        # so that e.g. a WB request doesn't silently pick a colorless commander.
        ci_set = set(color_identity)
        for i, (_, sc, _) in enumerate(ranked):
            if _is_legendary_creature(sc) and sc.name not in _BASIC_LAND_NAMES:
                if set(sc.color_identity) == ci_set:
                    commander_name = sc.name
                    commander_idx = i
                    break

    if commander_name is None:
        for i, (_, sc, _) in enumerate(ranked):
            if _is_legendary_creature(sc) and sc.name not in _BASIC_LAND_NAMES:
                commander_name = sc.name
                commander_idx = i
                break

    # Derive effective color identity from the commander's own Scryfall data.
    # The user's --colors flag may be broader (e.g. WB) but a colorless commander
    # still constrains the deck to colorless only. Commander rules 903.4b.
    commander_sc = ranked[commander_idx][1] if commander_idx >= 0 else None
    effective_ci: list[str] = commander_sc.color_identity if commander_sc is not None else (color_identity or [])
    allowed_ci: set[str] = set(effective_ci)

    pool = [
        (c, sc, s)
        for i, (c, sc, s) in enumerate(ranked)
        if i != commander_idx and set(sc.color_identity).issubset(allowed_ci)
    ]

    pool_spells = _dedupe_by_name(
        [(c, sc, s) for c, sc, s in pool if not _is_land(sc) and sc.name not in _BASIC_LAND_NAMES]
    )
    pool_nb_lands = _dedupe_by_name(
        [(c, sc, s) for c, sc, s in pool if _is_land(sc) and sc.name not in _BASIC_LAND_NAMES]
    )

    # 1 commander + 61 spells + 38 lands = 100
    spell_slots = TOTAL_CARDS - 1 - TARGET_LANDS
    nb_land_slots = min(len(pool_nb_lands), TARGET_LANDS)
    basic_land_count = TARGET_LANDS - nb_land_slots

    chosen_spells = [
        DeckCard(quantity=1, name=sc.name, set_code=sc.set_code, collector_number=sc.collector_number)
        for _, sc, _ in pool_spells[:spell_slots]
    ]
    chosen_nb_lands = [
        DeckCard(quantity=1, name=sc.name, set_code=sc.set_code, collector_number=sc.collector_number)
        for _, sc, _ in pool_nb_lands[:nb_land_slots]
    ]
    basic_land_cards = _fill_basics(basic_land_count, effective_ci)

    commander_entry = [DeckCard(quantity=1, name=commander_name or "Unknown")]
    mainboard: list[DeckCard] = commander_entry + chosen_spells + chosen_nb_lands + basic_land_cards
    mainboard = _adjust_to_total(mainboard, TOTAL_CARDS, effective_ci)

    ci_str = "".join(effective_ci) if effective_ci else "C"
    return DeckSuggestion(
        deck_name=f"{ci_str} {commander_name or 'Commander'} (Auto)",
        format="Commander",
        commander=commander_name,
        mainboard=mainboard,
        sideboard=[],
        strategy=(
            f"Algorithmically generated Commander deck built around "
            f"{commander_name or 'the top commander'}. "
            "Cards selected by synergy score from your collection."
        ),
        key_synergies=_top_keywords(ranked[:50]),
    )


def _build_sixty_card_deck(
    ranked: list[tuple[CollectionCard, ScryfallCard, float]],
    format_name: str,
    color_identity: list[str] | None,
) -> DeckSuggestion:
    TARGET_MAIN = 60
    TARGET_LANDS = 24
    MAX_COPIES = 4
    SPELL_SLOTS = TARGET_MAIN - TARGET_LANDS  # 36

    pool_spells = _dedupe_by_name(
        [(c, sc, s) for c, sc, s in ranked if not _is_land(sc) and sc.name not in _BASIC_LAND_NAMES]
    )
    pool_nb_lands = _dedupe_by_name(
        [(c, sc, s) for c, sc, s in ranked if _is_land(sc) and sc.name not in _BASIC_LAND_NAMES]
    )

    # Fill spell slots (max 4 copies, capped by owned quantity)
    name_copies: dict[str, int] = {}
    chosen_spells: list[DeckCard] = []
    spell_total = 0

    for coll, sc, _ in pool_spells:
        if spell_total >= SPELL_SLOTS:
            break
        can_add = min(coll.quantity, MAX_COPIES, SPELL_SLOTS - spell_total)
        if can_add <= 0:
            continue
        chosen_spells.append(
            DeckCard(quantity=can_add, name=sc.name, set_code=sc.set_code, collector_number=sc.collector_number)
        )
        name_copies[sc.name] = can_add
        spell_total += can_add

    # Fill land slots: up to half non-basic, rest basic
    nb_land_target = min(len(pool_nb_lands), TARGET_LANDS // 2)
    chosen_nb_lands = [
        DeckCard(quantity=1, name=sc.name, set_code=sc.set_code, collector_number=sc.collector_number)
        for _, sc, _ in pool_nb_lands[:nb_land_target]
    ]
    basic_cards = _fill_basics(TARGET_LANDS - nb_land_target, color_identity)

    mainboard: list[DeckCard] = chosen_spells + chosen_nb_lands + basic_cards
    mainboard = _adjust_to_total(mainboard, TARGET_MAIN, color_identity)

    # Sideboard: next-best cards, respecting combined 4-copy limit across main+side
    sideboard: list[DeckCard] = []
    side_total = 0

    for coll, sc, _ in pool_spells:
        if side_total >= 15:
            break
        main_copies = name_copies.get(sc.name, 0)
        available = coll.quantity - main_copies
        can_add = min(available, MAX_COPIES - main_copies, 15 - side_total)
        if can_add <= 0:
            continue
        sideboard.append(DeckCard(quantity=can_add, name=sc.name))
        side_total += can_add

    if 0 < side_total < 15:
        sideboard.extend(_fill_basics(15 - side_total, color_identity))
        side_total = 15

    ci_str = "".join(color_identity or [])
    prefix = f"{ci_str} " if ci_str else ""

    return DeckSuggestion(
        deck_name=f"{prefix}{format_name} (Auto)",
        format=format_name,
        commander=None,
        mainboard=mainboard,
        sideboard=sideboard if side_total == 15 else [],
        strategy=(
            f"Algorithmically generated {format_name} deck using the "
            "highest-synergy cards from your collection."
        ),
        key_synergies=_top_keywords(ranked[:50]),
    )


def suggest_deck_algo(
    format_name: str,
    ranked_cards: list[tuple[CollectionCard, ScryfallCard, float]],
    color_identity: list[str] | None = None,
    commander_hint: str | None = None,
) -> DeckSuggestion:
    """Build a deck algorithmically from the pre-ranked collection.

    Raises DeckValidationError if the result violates format rules (should
    not happen in normal use — indicates a bug in the algorithm).
    """
    if format_name == "Commander":
        deck = _build_commander_deck(ranked_cards, color_identity, commander_hint)
    else:
        deck = _build_sixty_card_deck(ranked_cards, format_name, color_identity)

    violations = _validate_deck(deck)
    if violations:
        raise DeckValidationError(violations)
    return deck
