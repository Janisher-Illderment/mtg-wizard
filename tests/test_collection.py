"""Tests for the ManaBox CSV parser."""

from __future__ import annotations

from pathlib import Path

from wizard.collection import parse_manabox_csv


def test_parses_all_rows(sample_collection_csv: Path) -> None:
    cards = parse_manabox_csv(sample_collection_csv)
    assert len(cards) == 4


def test_parses_first_row_fields(sample_collection_csv: Path) -> None:
    cards = parse_manabox_csv(sample_collection_csv)
    bolt = cards[0]
    assert bolt.name == "Lightning Bolt"
    assert bolt.set_code == "LEA"
    assert bolt.set_name == "Limited Edition Alpha"
    assert bolt.collector_number == "177"
    assert bolt.foil is False
    assert bolt.rarity == "Common"
    assert bolt.quantity == 3
    assert bolt.manabox_id == "12345"
    assert bolt.scryfall_id == "67890"
    assert bolt.purchase_price == 5.00
    assert bolt.misprint is False
    assert bolt.altered is False
    assert bolt.condition == "Near Mint"
    assert bolt.language == "English"
    assert bolt.currency == "EUR"


def test_parses_foil_yes(sample_collection_csv: Path) -> None:
    cards = parse_manabox_csv(sample_collection_csv)
    counterspell = next(c for c in cards if c.name == "Counterspell")
    assert counterspell.foil is True
    assert counterspell.quantity == 2


def test_parses_missing_price_as_none(sample_collection_csv: Path) -> None:
    cards = parse_manabox_csv(sample_collection_csv)
    sol_ring = next(c for c in cards if c.name == "Sol Ring")
    assert sol_ring.purchase_price is None


def test_handles_utf8_bom(tmp_path: Path) -> None:
    content = (
        "\ufeffName,Set code,Set name,Collector number,Foil,Rarity,Quantity,"
        "ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Condition,"
        "Language,Purchase price currency\n"
        "Lightning Bolt,LEA,Limited Edition Alpha,177,No,Common,1,1,2,1.00,"
        "No,No,Near Mint,English,EUR\n"
    )
    csv_path = tmp_path / "bom.csv"
    csv_path.write_text(content, encoding="utf-8")
    cards = parse_manabox_csv(csv_path)
    assert len(cards) == 1
    assert cards[0].name == "Lightning Bolt"


def test_skips_blank_rows(tmp_path: Path) -> None:
    content = (
        "Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,"
        "ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Condition,"
        "Language,Purchase price currency\n"
        "Lightning Bolt,LEA,Limited Edition Alpha,177,No,Common,1,1,2,1.00,"
        "No,No,Near Mint,English,EUR\n"
        ",,,,,,,,,,,,,,\n"
        "Sol Ring,CMR,Commander Legends,472,No,Uncommon,1,3,4,,No,No,Near Mint,English,EUR\n"
    )
    csv_path = tmp_path / "blanks.csv"
    csv_path.write_text(content, encoding="utf-8")
    cards = parse_manabox_csv(csv_path)
    assert [c.name for c in cards] == ["Lightning Bolt", "Sol Ring"]


def test_handles_missing_optional_fields(tmp_path: Path) -> None:
    content = (
        "Name,Set code,Set name,Collector number,Foil,Rarity,Quantity,"
        "ManaBox ID,Scryfall ID,Purchase price,Misprint,Altered,Condition,"
        "Language,Purchase price currency\n"
        "Lightning Bolt,LEA,Limited Edition Alpha,,,,1,,,,,,,,\n"
    )
    csv_path = tmp_path / "sparse.csv"
    csv_path.write_text(content, encoding="utf-8")
    cards = parse_manabox_csv(csv_path)
    assert len(cards) == 1
    assert cards[0].collector_number == ""
    assert cards[0].rarity == ""
    assert cards[0].purchase_price is None
