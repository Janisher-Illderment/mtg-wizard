"""Configuration loader — reads settings from environment via python-dotenv."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the wizard CLI."""

    anthropic_api_key: str | None
    db_path: Path
    model: str
    max_output_tokens: int = 8192


def _expand_path(raw: str) -> Path:
    """Expand `~` and env vars, then resolve to an absolute Path."""
    return Path(os.path.expandvars(raw)).expanduser()


def _parse_positive_int(raw: str | None, *, default: int, name: str) -> int:
    """Parse a positive int from env, falling back to `default` on invalid input."""
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        # Prefer a safe default over crashing at startup; log to stderr so the
        # misconfiguration is at least visible.
        import sys

        print(
            f"warning: {name}={raw!r} is not a valid integer; using {default}.",
            file=sys.stderr,
        )
        return default
    if value <= 0:
        return default
    return value


def load_settings() -> Settings:
    """Load settings from the environment (.env + process env)."""
    load_dotenv()
    db_path_raw = os.environ.get("WIZARD_DB_PATH", "~/.wizard/cards.db")
    model = os.environ.get("WIZARD_MODEL", "claude-sonnet-4-6")
    max_output_tokens = _parse_positive_int(
        os.environ.get("WIZARD_MAX_OUTPUT_TOKENS"),
        default=8192,
        name="WIZARD_MAX_OUTPUT_TOKENS",
    )
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        db_path=_expand_path(db_path_raw),
        model=model,
        max_output_tokens=max_output_tokens,
    )
