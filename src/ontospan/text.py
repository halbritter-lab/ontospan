"""Canonical text, hashes and the construction of documents and segments (T1 F2)."""

from __future__ import annotations

import hashlib
import unicodedata

from ontospan.models import Document, Segment

BOM = "﻿"


def canonical_text(raw: str) -> str:
    """NFC with LF line endings and no leading BOM: the text offsets refer to."""
    text = raw.removeprefix(BOM).replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_document(
    document_id: str,
    language: str,
    raw: str | bytes,
    *,
    subject_id: str | None = None,
) -> Document:
    """A document with canonical text; ``source_text_sha256`` keeps the original.

    Bytes must be UTF-8. Other encodings raise ``UnicodeDecodeError`` instead of
    being guessed. Offsets of existing annotations refer to the original text
    and must be mapped by the importer if canonicalisation changed it.
    """
    if isinstance(raw, bytes):
        source_sha = hashlib.sha256(raw).hexdigest()
        decoded = raw.decode("utf-8")
    else:
        source_sha = text_sha256(raw)
        decoded = raw
    text = canonical_text(decoded)
    return Document(
        document_id=document_id,
        language=language,
        text=text,
        text_sha256=text_sha256(text),
        source_text_sha256=source_sha,
        subject_id=subject_id,
    )


def segment(text: str, start: int, end: int) -> Segment:
    """The segment [start, end) of a canonical text, quoting it."""
    return Segment(start=start, end=end, text=text[start:end])
