"""Segment normalisation (T1 F11) and helpers for discontinuous mentions (T1 F4)."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from ontospan.models import Mention, Segment


def _trimmable(char: str) -> bool:
    return char.isspace() or unicodedata.category(char).startswith("P")


def normalize_segment(text: str, seg: Segment) -> tuple[int, int] | None:
    """The segment without edge whitespace and punctuation; None if nothing is left."""
    start, end = seg.start, seg.end
    while start < end and _trimmable(text[start]):
        start += 1
    while end > start and _trimmable(text[end - 1]):
        end -= 1
    return (start, end) if start < end else None


def spanning_segment(mention: Mention, text: str) -> Segment:
    """One segment from the first to the last segment of a mention."""
    start = min(seg.start for seg in mention.segments)
    end = max(seg.end for seg in mention.segments)
    return Segment(start=start, end=end, text=text[start:end])


def segments_flat(mentions: Iterable[Mention]) -> list[Segment]:
    """Every segment of these mentions, in text order."""
    return sorted(
        (seg for mention in mentions for seg in mention.segments),
        key=lambda seg: (seg.start, seg.end),
    )
