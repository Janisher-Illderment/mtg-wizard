"""Pure synergy-scoring helpers. No AI, no I/O — just functions over data."""

from __future__ import annotations

from wizard.models import CollectionCard, ScryfallCard

# Map CLI-facing format names to Scryfall legality keys.
_FORMAT_TO_SCRYFALL_KEY: dict[str, str] = {
    "Commander": "commander",
    "Standard": "standard",
    "Modern": "modern",
    "Pioneer": "pioneer",
    "Legacy": "legacy",
    "Vintage": "vintage",
    "Pauper": "pauper",
}


def _format_key(format_name: str) -> str:
    """Return the Scryfall legalities key for a user-facing format name."""
    return _FORMAT_TO_SCRYFALL_KEY.get(format_name, format_name.lower())


def score_format_legal(card: ScryfallCard, format_name: str) -> bool:
    """Return True if `card` is legal in the given `format_name`."""
    key = _format_key(format_name)
    return card.legalities.get(key) == "legal"


def _edhrec_component(rank: int | None) -> float:
    """Map an EDHREC rank (lower = more popular) to a 0..1 popularity score."""
    if rank is None or rank <= 0:
        return 0.0
    # Rank 1 ≈ 1.0, rank 1000 ≈ 0.5, rank 20000 ≈ ~0.05.
    import math

    return 1.0 / (1.0 + math.log10(max(rank, 1)))


def _keyword_overlap_component(
    card: ScryfallCard,
    collection: list[ScryfallCard],
) -> float:
    """Fraction of the card's keywords that also appear in the rest of the collection."""
    card_kw = {k.lower() for k in card.keywords}
    if not card_kw:
        return 0.0
    collection_kw: set[str] = set()
    for other in collection:
        if other.scryfall_id == card.scryfall_id:
            continue
        collection_kw.update(k.lower() for k in other.keywords)
    if not collection_kw:
        return 0.0
    overlap = card_kw & collection_kw
    return len(overlap) / len(card_kw)


def compute_synergy_score(card: ScryfallCard, collection: list[ScryfallCard]) -> float:
    """Score a card's fit with the rest of the collection in [0, 1]."""
    keyword = _keyword_overlap_component(card, collection)
    popularity = _edhrec_component(card.edhrec_rank)
    # Weights: keyword overlap is the stronger signal for synergy; EDHREC
    # rank is a weaker "is this a generically good card?" prior.
    score = 0.65 * keyword + 0.35 * popularity
    return max(0.0, min(1.0, score))


def _color_identity_compatible(
    card: ScryfallCard,
    color_identity: list[str] | None,
) -> bool:
    """True if the card's color identity fits within the allowed colors."""
    if color_identity is None:
        return True
    allowed = {c.upper() for c in color_identity}
    return set(card.color_identity).issubset(allowed)


def rank_collection_for_format(
    collection: list[tuple[CollectionCard, ScryfallCard]],
    format_name: str,
    color_identity: list[str] | None = None,
) -> list[tuple[CollectionCard, ScryfallCard, float]]:
    """Filter the collection by legality + colors and rank by synergy score."""
    # First: filter for legality and color identity.
    eligible: list[tuple[CollectionCard, ScryfallCard]] = [
        (coll, sc)
        for coll, sc in collection
        if score_format_legal(sc, format_name)
        and _color_identity_compatible(sc, color_identity)
    ]
    # Score each against the set of eligible ScryfallCards (so synergy is
    # measured among cards that could actually share a deck).
    pool = [sc for _, sc in eligible]
    ranked = [
        (coll, sc, compute_synergy_score(sc, pool))
        for coll, sc in eligible
    ]
    ranked.sort(key=lambda triple: triple[2], reverse=True)
    return ranked
