"""Ollama-powered deck builder using a local Ollama instance.

Calls the Ollama /api/chat endpoint with JSON mode enabled.
Requires Ollama running locally (default: http://localhost:11434).
"""

from __future__ import annotations

import json

import requests

from wizard.deckbuilder import (
    SYSTEM_PROMPT,
    _build_user_prompt,
    _find_commander_ci,
    _parse_deck_suggestion,
    _validate_deck,
)
from wizard.errors import DeckValidationError, WizardAPIError
from wizard.models import CollectionCard, DeckSuggestion, ScryfallCard

_JSON_SCHEMA_HINT = (
    "\n\nYou MUST respond with ONLY a JSON object — no markdown, no prose — "
    "matching this schema exactly:\n"
    '{"deck_name": "string", "format": "Commander|Standard|Modern|Pioneer|Legacy|Vintage|Pauper", '
    '"commander": "string or null", '
    '"mainboard": [{"quantity": 1, "name": "string", "set_code": "string or null", "collector_number": "string or null"}], '
    '"sideboard": [{"quantity": 1, "name": "string"}], '
    '"strategy": "string", "key_synergies": ["string"]}'
)

_OLLAMA_SYSTEM = SYSTEM_PROMPT + _JSON_SCHEMA_HINT


def suggest_deck_ollama(
    format_name: str,
    ranked_cards: list[tuple[CollectionCard, ScryfallCard, float]],
    color_identity: list[str] | None = None,
    ollama_url: str = "http://localhost:11434",
    model: str = "llama3.1",
) -> DeckSuggestion:
    """Ask a local Ollama model to build a deck and return a typed DeckSuggestion."""
    user_prompt = _build_user_prompt(format_name, color_identity, ranked_cards)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _OLLAMA_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "format": "json",
        "stream": False,
    }

    try:
        resp = requests.post(
            f"{ollama_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=120,
        )
    except requests.ConnectionError as exc:
        raise WizardAPIError(
            f"Could not connect to Ollama at {ollama_url}. "
            "Make sure Ollama is running (`ollama serve`).",
            cause=exc,
        ) from exc
    except requests.Timeout as exc:
        raise WizardAPIError(
            "Ollama request timed out after 120 s. Try a smaller model.",
            cause=exc,
        ) from exc

    if not resp.ok:
        raise WizardAPIError(
            f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}",
        )

    try:
        data = resp.json()
        raw_content = data["message"]["content"]
        deck_payload = json.loads(raw_content)
    except (KeyError, json.JSONDecodeError, ValueError) as exc:
        raise WizardAPIError(
            f"Ollama response could not be parsed as a deck JSON: {exc}",
            cause=exc,
        ) from exc

    deck = _parse_deck_suggestion(deck_payload)
    commander_ci = _find_commander_ci(deck.commander, ranked_cards)
    violations = _validate_deck(deck, commander_color_identity=commander_ci)
    if violations:
        raise DeckValidationError(violations)
    return deck
