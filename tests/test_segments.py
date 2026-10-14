from ontospan.models import Mention
from ontospan.segments import normalize_segment, segments_flat, spanning_segment
from ontospan.text import segment

TEXT = "Hypotonie, schwere Krampfanfälle und Fieber."


def test_edge_whitespace_and_punctuation_are_trimmed() -> None:
    assert normalize_segment(TEXT, segment(TEXT, 0, 10)) == (0, 9)  # "Hypotonie,"
    assert normalize_segment(TEXT, segment(TEXT, 36, 44)) == (37, 43)  # " Fieber."
    assert normalize_segment(TEXT, segment(TEXT, 9, 11)) is None  # ", "


def test_a_discontinuous_mention_spans_from_first_to_last_segment() -> None:
    mention = Mention(segments=(segment(TEXT, 0, 9), segment(TEXT, 19, 32)))
    assert spanning_segment(mention, TEXT) == segment(TEXT, 0, 32)


def test_flat_segments_list_every_segment_in_text_order() -> None:
    first = Mention(segments=(segment(TEXT, 19, 32),))
    second = Mention(segments=(segment(TEXT, 0, 9), segment(TEXT, 37, 43)))
    assert segments_flat([first, second]) == [
        segment(TEXT, 0, 9),
        segment(TEXT, 19, 32),
        segment(TEXT, 37, 43),
    ]
