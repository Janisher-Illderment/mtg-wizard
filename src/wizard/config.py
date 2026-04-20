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


def _expand_path(raw: str) -> Path:
    """Expand `~` and env vars, then resolve to an absolute Path."""
    return Path(os.path.expandvars(raw)).expanduser()


def load_settings() -> Settings:
    """Load settings from the environment (.env + process env)."""
    load_dotenv()
    db_path_raw = os.environ.get("WIZARD_DB_PATH", "~/.wizard/cards.db")
    model = os.environ.get("WIZARD_MODEL", "claude-sonnet-4-6")
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        db_path=_expand_path(db_path_raw),
        model=model,
    )
