"""Claude-powered deck builder.

The core `suggest_deck()` function:
  1. Builds a cached system prompt (deckbuilding rules + synergy principles).
  2. Summarizes the player's ranked, legal collection as the user message.
  3. Forces a single call to the `suggest_deck` tool so the model returns a
     strictly-typed JSON deck list.
  4. Parses the tool_use block back into a DeckSuggestion.

Signature note: the project brief lists this as `async def`, but the
`anthropic.Anthropic` client used here is synchronous — mixing the two would
silently swallow the response. Implemented as a regular function; escalated
to Tecle (see PR description / supervisor notes).
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from wizard.errors import DeckValidationError, WizardAPIError
from wizard.models import CollectionCard, DeckCard, DeckSuggestion, ScryfallCard

# Basic lands are the one card type allowed in arbitrary quantities in every
# format we support. Wastes is the colorless basic from Battle for Zendikar.
_BASIC_LANDS: frozenset[str] = frozenset(
    {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
)

# Formats that share the "60-card mainboard + 15-card sideboard + max 4 copies"
# deckbuilding rules. Everything else is either Commander or unknown.
_SIXTY_CARD_FORMATS: frozenset[str] = frozenset(
    {"Standard", "Modern", "Pioneer", "Legacy", "Vintage", "Pauper"}
)

# The suggest_deck tool JSON schema. This is stable across requests and
# contributes to the cached request prefix (tools → system → messages).
SUGGEST_DECK_TOOL: dict[str, Any] = {
    "name": "suggest_deck",
    "description": (
        "Output a complete structured MTG deck suggestion based on the "
        "player's collection"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "deck_name": {"type": "string"},
            "format": {
                "type": "string",
                "enum": [
                    "Commander",
                    "Standard",
                    "Modern",
                    "Pioneer",
                    "Legacy",
                    "Vintage",
                    "Pauper",
                ],
            },
            "commander": {
                "type": ["string", "null"],
                "description": "Commander card name for Commander format",
            },
            "mainboard": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "quantity": {"type": "integer", "minimum": 1},
                        "name": {"type": "string"},
                        "set_code": {"type": ["string", "null"]},
                        "collector_number": {"type": ["string", "null"]},
                    },
                    "required": ["quantity", "name"],
                },
            },
            "sideboard": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "quantity": {"type": "integer", "minimum": 1},
                        "name": {"type": "string"},
                    },
                    "required": ["quantity", "name"],
                },
            },
            "strategy": {"type": "string"},
            "key_synergies": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["deck_name", "format", "mainboard", "strategy"],
    },
}

# Stable system prompt — cached via cache_control.  Kept frozen (no dates,
# UUIDs, session IDs interpolated) so the prefix matches across requests.
SYSTEM_PROMPT = """You are an expert MTG deck builder. Your job is to create competitive, synergistic decks \
using ONLY cards the player already owns. You must call the suggest_deck tool to output your deck.

MTG Deck building rules:
- Commander: exactly 100 cards, 1 legendary commander, no duplicates (except basic lands)
- Standard/Modern/Pioneer: 60+ card mainboard, 15-card sideboard, max 4 copies of any non-basic
- Legal cards only for the requested format

Synergy principles:
- Prioritize cards with high keyword overlap
- Consider mana curve: aim for a bell curve centered around 2-3 CMC
- Include sufficient mana sources: ~24 lands for 60-card, ~38 for Commander
- For Commander: build around the commander's color identity and abilities
"""

# Cap the card list we send to Claude to keep the user turn small. Higher-ranked
# cards come first, so truncation at the tail loses only marginal options.
_MAX_CARDS_IN_PROMPT = 400


def _render_ranked_cards(
    ranked_cards: list[tuple[CollectionCard, ScryfallCard, float]],
) -> str:
    """Render the ranked collection as a compact text table for the prompt."""
    lines: list[str] = []
    for coll, sc, score in ranked_cards[:_MAX_CARDS_IN_PROMPT]:
        colors = "".join(sc.color_identity) or "C"
        type_line = sc.type_line.replace("\n", " ")
        lines.append(
            f"- {coll.quantity}x {sc.name} [{colors}] ({sc.mana_cost or '—'}) "
            f"[{type_line}] score={score:.2f}"
        )
    return "\n".join(lines)


def _build_user_prompt(
    format_name: str,
    color_identity: list[str] | None,
    ranked_cards: list[tuple[CollectionCard, ScryfallCard, float]],
) -> str:
    """Assemble the per-request user message with the ranked collection."""
    ci_text = ", ".join(color_identity) if color_identity else "any"
    return (
        f"Format: {format_name}\n"
        f"Color identity: {ci_text}\n"
        f"Total eligible cards: {len(ranked_cards)}\n\n"
        f"Player's ranked legal collection (synergy score 0-1, top "
        f"{min(len(ranked_cards), _MAX_CARDS_IN_PROMPT)} shown):\n"
        f"{_render_ranked_cards(ranked_cards)}\n\n"
        f"Build the best possible {format_name} deck using ONLY these cards. "
        f"Call the suggest_deck tool with your final deck list."
    )


def _parse_tool_use(content_blocks: list[Any]) -> dict[str, Any]:
    """Find the suggest_deck tool_use block and return its input dict."""
    for block in content_blocks:
        block_type = getattr(block, "type", None)
        if block_type == "tool_use" and getattr(block, "name", None) == "suggest_deck":
            raw = getattr(block, "input", None)
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, str):
                # Defensive: some SDK versions may hand back a JSON string.
                return json.loads(raw)
    raise RuntimeError(
        "Claude response did not contain a suggest_deck tool_use block"
    )


def _deck_card_from_dict(data: dict[str, Any]) -> DeckCard:
    """Build a DeckCard from a tool-output dict, tolerating missing fields."""
    return DeckCard(
        quantity=int(data.get("quantity", 1)),
        name=str(data.get("name", "")),
        set_code=data.get("set_code"),
        collector_number=data.get("collector_number"),
    )


def _parse_deck_suggestion(payload: dict[str, Any]) -> DeckSuggestion:
    """Convert the tool JSON payload into a DeckSuggestion dataclass."""
    mainboard = [_deck_card_from_dict(c) for c in payload.get("mainboard", [])]
    sideboard = [_deck_card_from_dict(c) for c in payload.get("sideboard", [])]
    return DeckSuggestion(
        deck_name=str(payload.get("deck_name", "Untitled Deck")),
        format=str(payload.get("format", "Commander")),
        commander=payload.get("commander"),
        mainboard=mainboard,
        sideboard=sideboard,
        strategy=str(payload.get("strategy", "")),
        key_synergies=list(payload.get("key_synergies", [])),
    )


def _validate_deck(deck: DeckSuggestion) -> list[str]:
    """Return a list of format-legality violations (empty = valid).

    Scope is deliberately limited to counts / quantities / commander presence.
    Card legality, color identity, and singleton-by-oracle-name rules are left
    to the scorer/collection layer because validating them here would require
    ScryfallCard lookups — which this module does not have.
    """
    violations: list[str] = []
    fmt = (deck.format or "").strip()
    fmt_title = fmt  # formats come in title-case from the tool schema enum

    main_total = sum(card.quantity for card in deck.mainboard)
    side_total = sum(card.quantity for card in deck.sideboard)

    # Copy-count rule is shared (basics excluded). Sideboard quantities count
    # toward the same 4-copy cap in the 60-card formats; Commander is stricter.
    def _each_non_basic_excess(cards: list[DeckCard], cap: int) -> list[str]:
        bad: list[str] = []
        for card in cards:
            if card.name in _BASIC_LANDS:
                continue
            if card.quantity > cap:
                bad.append(
                    f"{card.name}: {card.quantity} copies (max {cap} for non-basic-lands)"
                )
        return bad

    if fmt_title == "Commander":
        if not deck.commander or not deck.commander.strip():
            violations.append("Commander format requires a non-empty `commander` field.")
        if main_total != 100:
            violations.append(
                f"Commander requires exactly 100 mainboard cards; got {main_total}."
            )
        # Commander is singleton — every non-basic limited to 1 copy.
        violations.extend(_each_non_basic_excess(deck.mainboard, cap=1))
        violations.extend(_each_non_basic_excess(deck.sideboard, cap=1))
    elif fmt_title in _SIXTY_CARD_FORMATS:
        if main_total < 60:
            violations.append(
                f"{fmt_title} requires at least 60 mainboard cards; got {main_total}."
            )
        if deck.sideboard and side_total != 15:
            violations.append(
                f"{fmt_title} sideboard, when non-empty, must be exactly 15; got {side_total}."
            )
        violations.extend(_each_non_basic_excess(deck.mainboard, cap=4))
        violations.extend(_each_non_basic_excess(deck.sideboard, cap=4))
    # Unknown formats: no validation (keep the failure path minimal).
    return violations


def _call_anthropic(
    client: anthropic.Anthropic,
    **kwargs: Any,
) -> Any:
    """Invoke `client.messages.create` and re-raise SDK errors as WizardAPIError.

    The Anthropic SDK already handles connection/429 retries internally via
    the `max_retries=` client constructor argument. Exceptions reach us only
    after those retries have been exhausted, so the messages below describe
    the *final* state, not a single transient failure.
    """
    try:
        return client.messages.create(**kwargs)
    except anthropic.AuthenticationError as exc:
        raise WizardAPIError(
            "Your ANTHROPIC_API_KEY is invalid or revoked. Check .env.",
            cause=exc,
        ) from exc
    except anthropic.RateLimitError as exc:
        raise WizardAPIError(
            "Rate-limited by Anthropic after retries. Wait a minute and retry.",
            cause=exc,
        ) from exc
    except anthropic.BadRequestError as exc:
        # BadRequestError exposes `.message`; fall back to str(exc) defensively.
        msg = getattr(exc, "message", None) or str(exc)
        raise WizardAPIError(
            f"Request rejected by Anthropic: {msg}",
            cause=exc,
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise WizardAPIError(
            "Could not reach Anthropic API. Check your network.",
            cause=exc,
        ) from exc
    except anthropic.APIStatusError as exc:
        status = getattr(exc, "status_code", "?")
        msg = getattr(exc, "message", None) or str(exc)
        raise WizardAPIError(
            f"Anthropic API error {status}: {msg}",
            cause=exc,
        ) from exc


def suggest_deck(
    client: anthropic.Anthropic,
    format_name: str,
    ranked_cards: list[tuple[CollectionCard, ScryfallCard, float]],
    color_identity: list[str] | None = None,
    model: str = "claude-sonnet-4-6",
    max_output_tokens: int = 8192,
) -> DeckSuggestion:
    """Ask Claude to build a deck and return a typed DeckSuggestion."""
    user_prompt = _build_user_prompt(format_name, color_identity, ranked_cards)

    response = _call_anthropic(
        client,
        model=model,
        max_tokens=max_output_tokens,
        # cache_control on the last (only) system block caches tools + system
        # together — the prefix Claude sees for every wizard call.
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[SUGGEST_DECK_TOOL],
        tool_choice={"type": "tool", "name": "suggest_deck"},
        messages=[{"role": "user", "content": user_prompt}],
    )

    payload = _parse_tool_use(response.content)
    deck = _parse_deck_suggestion(payload)
    violations = _validate_deck(deck)
    if violations:
        raise DeckValidationError(violations)
    return deck
