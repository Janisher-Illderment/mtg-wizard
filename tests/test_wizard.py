"""Tests for the Claude wizard integration. All network calls are mocked."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from wizard.models import CollectionCard, ScryfallCard
from wizard.wizard import SUGGEST_DECK_TOOL, SYSTEM_PROMPT, suggest_deck


def _sc(name: str, sid: str = "id-1") -> ScryfallCard:
    return ScryfallCard(
        scryfall_id=sid,
        name=name,
        set_code="tst",
        collector_number="1",
        mana_cost="{R}",
        colors=["R"],
        color_identity=["R"],
        type_line="Instant",
        oracle_text="",
        keywords=["Haste"],
        legalities={"commander": "legal"},
        edhrec_rank=10,
        penny_rank=None,
        prices={},
        raw_json="{}",
    )


def _coll(name: str) -> CollectionCard:
    return CollectionCard(
        name=name,
        set_code="tst",
        set_name="Test",
        collector_number="1",
        foil=False,
        rarity="Common",
        quantity=4,
        manabox_id="",
        scryfall_id="",
        purchase_price=None,
        misprint=False,
        altered=False,
        condition="Near Mint",
        language="English",
        currency="EUR",
    )


def _fake_tool_use_response(deck_payload: dict) -> SimpleNamespace:
    """Construct a fake Anthropic response containing one tool_use block."""
    tool_use = SimpleNamespace(
        type="tool_use",
        name="suggest_deck",
        id="toolu_abc123",
        input=deck_payload,
    )
    return SimpleNamespace(content=[tool_use], stop_reason="tool_use")


def test_suggest_deck_parses_tool_use() -> None:
    client = MagicMock()
    client.messages.create.return_value = _fake_tool_use_response(
        {
            "deck_name": "Mono-Red Aggro",
            "format": "Modern",
            "commander": None,
            "mainboard": [
                {"quantity": 4, "name": "Lightning Bolt", "set_code": "lea", "collector_number": "177"},
                {"quantity": 20, "name": "Mountain", "set_code": None, "collector_number": None},
            ],
            "sideboard": [{"quantity": 2, "name": "Smash to Smithereens"}],
            "strategy": "Fast damage, efficient removal.",
            "key_synergies": ["low curve", "burn"],
        }
    )

    ranked = [(_coll("Lightning Bolt"), _sc("Lightning Bolt"), 0.9)]
    result = suggest_deck(client, "Modern", ranked, color_identity=["R"])

    assert result.deck_name == "Mono-Red Aggro"
    assert result.format == "Modern"
    assert result.commander is None
    assert len(result.mainboard) == 2
    assert result.mainboard[0].name == "Lightning Bolt"
    assert result.mainboard[0].quantity == 4
    assert result.sideboard[0].name == "Smash to Smithereens"
    assert "burn" in result.key_synergies


def test_suggest_deck_sends_cache_control_and_tool_choice() -> None:
    client = MagicMock()
    client.messages.create.return_value = _fake_tool_use_response(
        {
            "deck_name": "Test",
            "format": "Commander",
            "commander": "Krenko, Mob Boss",
            "mainboard": [{"quantity": 1, "name": "Krenko, Mob Boss"}],
            "sideboard": [],
            "strategy": "s",
            "key_synergies": [],
        }
    )

    ranked = [(_coll("Krenko"), _sc("Krenko, Mob Boss"), 0.8)]
    suggest_deck(client, "Commander", ranked, color_identity=["R"])

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"
    # System prompt is a list with cache_control for prompt caching.
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["system"][0]["text"] == SYSTEM_PROMPT
    # Tool_choice forces the suggest_deck tool.
    assert kwargs["tool_choice"] == {"type": "tool", "name": "suggest_deck"}
    assert kwargs["tools"][0]["name"] == "suggest_deck"
    # User message mentions the format and the card.
    user_content = kwargs["messages"][0]["content"]
    assert "Commander" in user_content
    assert "Krenko, Mob Boss" in user_content


def test_suggest_deck_raises_without_tool_use() -> None:
    client = MagicMock()
    # A plain text response with no tool_use block.
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I refuse.")],
        stop_reason="end_turn",
    )
    with pytest.raises(RuntimeError, match="suggest_deck"):
        suggest_deck(client, "Modern", [(_coll("x"), _sc("x"), 0.1)])


def test_suggest_deck_tool_schema_shape() -> None:
    # Sanity-check the tool schema to catch accidental regressions.
    schema = SUGGEST_DECK_TOOL["input_schema"]
    assert schema["type"] == "object"
    assert "deck_name" in schema["properties"]
    assert "mainboard" in schema["properties"]
    assert schema["properties"]["format"]["enum"][0] == "Commander"


def test_suggest_deck_custom_model() -> None:
    client = MagicMock()
    client.messages.create.return_value = _fake_tool_use_response(
        {
            "deck_name": "Test",
            "format": "Modern",
            "commander": None,
            "mainboard": [{"quantity": 1, "name": "x"}],
            "sideboard": [],
            "strategy": "s",
            "key_synergies": [],
        }
    )
    suggest_deck(
        client,
        "Modern",
        [(_coll("x"), _sc("x"), 0.1)],
        model="claude-opus-4-6",
    )
    assert client.messages.create.call_args.kwargs["model"] == "claude-opus-4-6"


@patch("wizard.wizard.anthropic.Anthropic")
def test_wizard_does_not_call_api_at_import(mock_client_cls: MagicMock) -> None:
    # Ensure importing wizard.py does not instantiate a client (important for
    # tests that should run fully offline).
    import importlib

    import wizard.wizard as mod

    importlib.reload(mod)
    mock_client_cls.assert_not_called()
