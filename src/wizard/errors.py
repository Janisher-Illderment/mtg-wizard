"""Exceptions raised by the wizard package.

These wrap lower-level SDK / validation failures into a small, user-facing
vocabulary so the CLI can print a single clean message and exit cleanly
without leaking stack traces to the terminal.
"""

from __future__ import annotations


class WizardAPIError(Exception):
    """Raised when a call to the Anthropic API fails.

    `user_message` is the sanitized, human-readable string the CLI should
    show to the user — never includes raw API payloads or stack noise.
    """

    def __init__(self, user_message: str, *, cause: BaseException | None = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.__cause__ = cause


class DeckValidationError(Exception):
    """Raised when a DeckSuggestion violates format-legality rules.

    Carries the full list of violations so the CLI can print each one.
    """

    def __init__(self, violations: list[str]):
        self.violations = list(violations)
        super().__init__("; ".join(self.violations))
