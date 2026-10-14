from typing import Any

import pytest
from builders import FIXTURES, annotation, axes

from ontospan.matching import agreement, assign, match_annotations
from ontospan.models import Annotation
from ontospan.ontology import ObographOntology

# Hypotonie 0-9, "Hypotonie," 0-10, schwere 11-18, Krampfanfälle 19-32,
# "schwere Krampfanfälle" 11-32, Fieber 37-43, "Fieber." 37-44, " Fieber" 36-43.
T = "Hypotonie, schwere Krampfanfälle und Fieber."
HYPOTONIA, SEIZURE, DIALEPTIC, FEVER = (
    "HP:0001252",
    "HP:0001250",
    "HP:0011146",
    "HP:0001945",
)


def a(aid: str, term: str, *spans: Any, **kw: Any) -> Annotation:
    return annotation(aid, term, list(spans), text=T, **kw)


def kinds(
    left: list[Annotation], right: list[Annotation]
) -> list[tuple[str, str, str]]:
    return [
        (g.kind, g.a.annotation_id if g.a else "-", g.b.annotation_id if g.b else "-")
        for g in match_annotations(left, right, T)
    ]


def test_the_assignment_maximises_the_total_weight() -> None:
    assert assign([[3, 2], [2, 0]]) == [(0, 1), (1, 0)]
    assert assign([[0, 0], [0, 5]]) == [(1, 1)]
    assert assign([[1, 1, 1]]) == [(0, 0)]
    assert assign([]) == []


def test_edge_punctuation_and_whitespace_are_no_conflict() -> None:
    left = [a("a1", HYPOTONIA, (0, 10)), a("a2", FEVER, (37, 44))]
    right = [a("b1", HYPOTONIA, (0, 9)), a("b2", FEVER, (36, 43))]
    assert kinds(left, right) == [("equal", "a1", "b1"), ("equal", "a2", "b2")]


def test_overlap_with_same_term_and_axes_is_compatible() -> None:
    left, right = [a("a1", SEIZURE, (19, 32))], [a("b1", SEIZURE, (11, 32))]
    assert kinds(left, right) == [("compatible", "a1", "b1")]


def test_same_place_with_other_axes_is_an_axis_conflict() -> None:
    left = [a("a1", SEIZURE, (19, 32))]
    right = [a("b1", SEIZURE, (19, 32), axes_=axes("absent"))]
    assert kinds(left, right) == [("axis_conflict", "a1", "b1")]


def test_a_term_conflict_marks_ancestors_if_the_ontology_is_given() -> None:
    hp = ObographOntology.load(FIXTURES / "hp-mini.json")
    left, right = [a("a1", SEIZURE, (19, 32))], [a("b1", DIALEPTIC, (19, 32))]
    with_hp = match_annotations(left, right, T, hp)
    assert [(g.kind, g.ancestor) for g in with_hp] == [("term_conflict", True)]
    without = match_annotations(left, right, T)
    assert [(g.kind, g.ancestor) for g in without] == [("term_conflict", False)]


def test_unmatched_annotations_are_listed_per_side_in_text_order() -> None:
    left = [a("a2", FEVER, (37, 43)), a("a1", HYPOTONIA, (0, 9))]
    right = [a("b1", SEIZURE, (19, 32))]
    assert kinds(left, right) == [
        ("a_only", "a1", "-"),
        ("b_only", "-", "b1"),
        ("a_only", "a2", "-"),
    ]


def test_the_best_pairing_wins_over_a_weaker_one() -> None:
    left = [a("a1", SEIZURE, (19, 32))]
    right = [a("b1", SEIZURE, (11, 32)), a("b2", SEIZURE, (19, 32))]
    assert kinds(left, right) == [("b_only", "-", "b1"), ("equal", "a1", "b2")]


def test_regression_more_compatible_pairs_beat_a_greedy_first_choice() -> None:
    # Greedy pairing took a1-b1 and left a2 and b2 alone (tolerant F1 0.5).
    left = [a("a1", SEIZURE, (0, 32)), a("a2", SEIZURE, (11, 25))]
    right = [a("b1", SEIZURE, (11, 20)), a("b2", SEIZURE, (25, 32))]
    assert kinds(left, right) == [
        ("compatible", "a1", "b2"),
        ("compatible", "a2", "b1"),
    ]
    assert agreement(left, right, T).annotation_tolerant_f1 == 1.0


def test_regression_conflicts_are_paired_optimally_too() -> None:
    # a1 conflicts with b1 and b2, a2 only with b1: both conflicts are shown.
    absent = axes("absent")
    left = [a("a1", SEIZURE, (0, 32)), a("a2", SEIZURE, (11, 18))]
    right = [
        a("b1", SEIZURE, (11, 18), axes_=absent),
        a("b2", SEIZURE, (19, 32), axes_=absent),
    ]
    assert kinds(left, right) == [
        ("axis_conflict", "a1", "b2"),
        ("axis_conflict", "a2", "b1"),
    ]


def test_annotations_of_different_layers_never_pair() -> None:
    left = [a("a1", SEIZURE, (19, 32))]
    right = [a("b1", "MAXO:0000001", (19, 32), layer_id="maxo")]
    assert kinds(left, right) == [("a_only", "a1", "-"), ("b_only", "-", "b1")]
    same_term_other_layer = [a("b1", SEIZURE, (19, 32), layer_id="other")]
    result = agreement(left, same_term_other_layer, T)
    assert (result.annotation_strict_f1, result.term_f1) == (0.0, 0.0)


def test_discontinuous_mentions_compare_as_sets_of_segments() -> None:
    gap = [(0, 9), (19, 32)]
    left = [a("a1", SEIZURE, gap)]
    assert kinds(left, [a("b1", SEIZURE, [(19, 32), (0, 10)])]) == [
        ("equal", "a1", "b1")
    ]
    assert kinds(left, [a("b1", SEIZURE, (19, 32))]) == [("compatible", "a1", "b1")]
    assert kinds(left, [a("b1", SEIZURE, (37, 43))]) == [
        ("a_only", "a1", "-"),
        ("b_only", "-", "b1"),
    ]


def test_document_level_annotations() -> None:
    doc = a("a1", SEIZURE, document_level=True)
    assert kinds([doc], [a("b1", SEIZURE, document_level=True)]) == [
        ("equal", "a1", "b1")
    ]
    # D3: the same statement once with and once without a span is compatible.
    assert kinds([doc], [a("b1", SEIZURE, (19, 32))]) == [("compatible", "a1", "b1")]
    assert kinds([doc], [a("b1", FEVER, document_level=True)]) == [
        ("a_only", "a1", "-"),
        ("b_only", "-", "b1"),
    ]
    other_axes = a("b1", SEIZURE, (19, 32), axes_=axes("absent"))
    assert kinds([doc], [other_axes]) == [("b_only", "-", "b1"), ("a_only", "a1", "-")]


def test_a_mention_of_only_punctuation_never_matches() -> None:
    assert kinds([a("a1", SEIZURE, (9, 11))], [a("b1", SEIZURE, (9, 11))]) == [
        ("a_only", "a1", "-"),
        ("b_only", "-", "b1"),
    ]


def test_modifier_differences_are_flagged_on_matched_pairs() -> None:
    left = [a("a1", SEIZURE, (19, 32), modifiers=[("HP:0012828", [(11, 18)])])]
    right = [a("b1", SEIZURE, (19, 32))]
    groups = match_annotations(left, right, T)
    assert [(g.kind, g.modifiers_differ) for g in groups] == [("equal", True)]
    assert agreement(left, right, T).modifier_agreement == 0.0


def test_agreement_on_annotation_mention_and_term_level() -> None:
    left = [
        a("a1", HYPOTONIA, (0, 9)),
        a("a2", SEIZURE, (19, 32)),
        a("a3", FEVER, (37, 43)),
    ]
    right = [a("b1", HYPOTONIA, (0, 10)), a("b2", SEIZURE, (11, 32))]
    result = agreement(left, right, T)
    assert result.annotation_strict_f1 == pytest.approx(2 * 1 / 5)
    assert result.annotation_tolerant_f1 == pytest.approx(2 * 2 / 5)
    assert result.mention_strict_f1 == pytest.approx(2 * 1 / 5)
    assert result.mention_tolerant_f1 == pytest.approx(2 * 2 / 5)
    assert result.term_f1 == pytest.approx(2 * 2 / 5)
    assert result.modifier_agreement == 1.0
    counts = (result.equal, result.compatible, result.a_only, result.b_only)
    assert counts == (1, 1, 1, 0)


def test_mention_level_counts_every_mention() -> None:
    # One annotation with two mentions against one with one: the annotations
    # are only compatible, but one of the two mentions is equal.
    left = [a("a1", SEIZURE, (19, 32), (37, 43))]
    right = [a("b1", SEIZURE, (19, 32))]
    result = agreement(left, right, T)
    assert (result.equal, result.compatible) == (0, 1)
    assert (result.mentions_a, result.mentions_b, result.mentions_equal) == (2, 1, 1)
    assert result.mention_strict_f1 == pytest.approx(2 * 1 / 3)
    assert result.annotation_strict_f1 == 0.0


def test_two_empty_sets_agree_fully() -> None:
    result = agreement([], [], T)
    scores = (
        result.annotation_strict_f1,
        result.annotation_tolerant_f1,
        result.mention_strict_f1,
        result.mention_tolerant_f1,
        result.term_f1,
        result.modifier_agreement,
    )
    assert scores == (1.0, 1.0, 1.0, 1.0, 1.0, None)


def test_term_counts_for_microaveraging_count_distinct_labels() -> None:
    left = [
        a("a1", SEIZURE, (19, 32)),
        a("a2", SEIZURE, (37, 43)),
        a("a3", FEVER, (37, 43)),
    ]
    right = [
        a("b1", SEIZURE, (19, 32)),
        a("b2", HYPOTONIA, (0, 9)),
        a("b3", HYPOTONIA, (0, 10)),
    ]
    result = agreement(left, right, T)
    assert (result.terms_a, result.terms_b, result.terms_equal) == (2, 2, 1)
    assert result.term_f1 == 0.5
    empty = agreement([], [], T)
    assert (empty.terms_a, empty.terms_b, empty.terms_equal) == (0, 0, 0)
