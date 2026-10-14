import hashlib

import pytest

from ontospan.text import canonical_text, make_document, segment, text_sha256


def test_canonical_text_is_nfc_with_lf_line_endings() -> None:
    raw = "Café\r\nzweite Zeile\rdritte"
    assert canonical_text(raw) == "Café\nzweite Zeile\ndritte"


def test_a_leading_bom_is_dropped_from_strings_and_bytes() -> None:
    assert canonical_text("﻿Café") == "Café"
    assert make_document("d1", "de", "﻿Café").text == "Café"


def test_text_hash_is_sha256_of_utf8() -> None:
    assert text_sha256("Café") == hashlib.sha256("Café".encode()).hexdigest()


def test_a_document_from_bytes_keeps_the_hash_of_the_original_bytes() -> None:
    raw = "﻿Café\r\n".encode()
    document = make_document("d1", "de", raw)
    assert document.text == "Café\n"
    assert document.text_sha256 == text_sha256("Café\n")
    assert document.source_text_sha256 == hashlib.sha256(raw).hexdigest()


def test_a_document_from_bytes_must_be_utf8() -> None:
    with pytest.raises(UnicodeDecodeError):
        make_document("d1", "de", "Grüße".encode("latin-1"))


def test_a_segment_quotes_its_text() -> None:
    assert segment("Keine Krampfanfälle", 6, 19).text == "Krampfanfälle"


def test_all_leading_boms_are_removed_and_canonicalization_is_idempotent() -> None:
    raw = "\ufeff\ufeff\ufeffCafé\r\n"
    assert canonical_text(raw) == "Café\n"
    assert canonical_text(canonical_text(raw)) == "Café\n"
    assert make_document("d", "de", raw).text == "Café\n"
