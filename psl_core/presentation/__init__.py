"""Shared match presentation for Web, Bot, challenges, and leagues."""

from .match import (
    MatchPresentation,
    PresentedEvent,
    build_match_presentation,
)

__all__ = [
    "MatchPresentation",
    "PresentedEvent",
    "build_match_presentation",
]
