"""Unit tests for the synergy scorer."""

from __future__ import annotations

from wizard.models import CollectionCard, ScryfallCard
from wizard.scorer import (
    compute_synergy_score,
    rank_collection_for_format,
    score_format_legal,
)


def _sc(
    scryfall_id: str,
    name: str,
    *,
    color_identity: list[str] | None = None,
    keywords: list[str] | None = None,
    legalities: dict[str, str] | None = None,
    edhrec_rank: int | None = None,
) -> ScryfallCard:
    return ScryfallCard(
        scryfall_id=scryfall_id,
        name=name,
        set_code="tst",
        collector_number="1",
        mana_cost="",
        colors=[],
        color_identity=color_identity or [],
        type_line="Creature",
        oracle_text="",
        keywords=keywords or [],
        legalities=legalities or {},
        edhrec_rank=edhrec_rank,
        penny_rank=None,
        prices={},
        raw_json="{}",
    )


def _coll(name: str, scryfall_id: str = "") -> CollectionCard:
    return CollectionCard(
        name=name,
        set_code="tst",
        set_name="Test",
        collector_number="1",
        foil=False,
        rarity="Common",
        quantity=1,
        manabox_id="",
        scryfall_id=scryfall_id,
        purchase_price=None,
        misprint=False,
        altered=False,
        condition="Near Mint",
        language="English",
        currency="EUR",
    )


def test_score_format_legal_true() -> None:
    c = _sc("1", "Bolt", legalities={"modern": "legal"})
    assert score_format_legal(c, "Modern") is True


def test_score_format_legal_false() -> None:
    c = _sc("1", "Bolt", legalities={"modern": "not_legal"})
    assert score_format_legal(c, "Modern") is False
    assert score_format_legal(c, "Standard") is False


def test_synergy_score_in_range() -> None:
    a = _sc("a", "A", keywords=["Flying"], edhrec_rank=100)
    b = _sc("b", "B", keywords=["Flying"])
    score = compute_synergy_score(a, [a, b])
    assert 0.0 <= score <= 1.0


def test_synergy_score_higher_with_overlap() -> None:
    flying_a = _sc("a", "A", keywords=["Flying"])
    flying_b = _sc("b", "B", keywords=["Flying"])
    haste = _sc("c", "C", keywords=["Haste"])
    with_overlap = compute_synergy_score(flying_a, [flying_a, flying_b])
    without_overlap = compute_synergy_score(haste, [haste, flying_a])
    assert with_overlap > without_overlap


def test_synergy_zero_for_no_keywords_and_no_rank() -> None:
    c = _sc("a", "A", keywords=[], edhrec_rank=None)
    assert compute_synergy_score(c, [c]) == 0.0


def test_rank_filters_by_legality() -> None:
    legal = _sc("1", "Legal", legalities={"modern": "legal"})
    banned = _sc("2", "Banned", legalities={"modern": "banned"})
    collection = [(_coll("Legal"), legal), (_coll("Banned"), banned)]
    ranked = rank_collection_for_format(collection, "Modern")
    assert [r[1].name for r in ranked] == ["Legal"]


def test_rank_filters_by_color_identity() -> None:
    mono_red = _sc(
        "1",
        "Red",
        color_identity=["R"],
        legalities={"commander": "legal"},
    )
    blue = _sc(
        "2",
        "Blue",
        color_identity=["U"],
        legalities={"commander": "legal"},
    )
    collection = [(_coll("Red"), mono_red), (_coll("Blue"), blue)]
    ranked = rank_collection_for_format(collection, "Commander", color_identity=["R"])
    assert [r[1].name for r in ranked] == ["Red"]


def test_rank_colorless_compatible_everywhere() -> None:
    colorless = _sc(
        "1",
        "Colorless",
        color_identity=[],
        legalities={"commander": "legal"},
    )
    collection = [(_coll("Colorless"), colorless)]
    ranked = rank_collection_for_format(collection, "Commander", color_identity=["R"])
    assert len(ranked) == 1


def test_rank_sorted_desc() -> None:
    high = _sc("1", "High", keywords=["Flying"], legalities={"commander": "legal"})
    partner = _sc(
        "2", "Partner", keywords=["Flying"], legalities={"commander": "legal"}
    )
    low = _sc("3", "Low", keywords=[], legalities={"commander": "legal"})
    collection = [(_coll("High"), high), (_coll("Partner"), partner), (_coll("Low"), low)]
    ranked = rank_collection_for_format(collection, "Commander")
    scores = [s for _, _, s in ranked]
    assert scores == sorted(scores, reverse=True)
