"""Comparing two annotation sets of the same canonical text (T1 F11).

This is the single implementation that Ontotator (merge, live agreement)
and the benchmark share.

- Annotations are only paired within the same layer.
- The pairing is an optimal assignment: as many ``equal`` pairs as possible,
  then ``compatible``, then ``axis_conflict``, then ``term_conflict``; among
  those, the one with the most shared codepoints. Inputs are ordered by text
  position and id, so ties always resolve the same way.
- A document-level annotation and a mention-based one with the same term and
  axes are ``compatible`` (review decision D3).
- A mention that normalises to nothing never matches.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, TypeVar

from ontospan.models import Annotation, Mention
from ontospan.ontology import OntologyView
from ontospan.segments import normalize_segment

MatchKind = Literal[
    "equal", "compatible", "axis_conflict", "term_conflict", "a_only", "b_only"
]
Relation = Literal["identical", "overlapping", "disjoint", "document", "unusable"]
Interval = tuple[int, int]
MentionKey = frozenset[Interval]
_LEVEL: dict[MatchKind, int] = {
    "equal": 3,
    "compatible": 2,
    "axis_conflict": 1,
    "term_conflict": 0,
}
T = TypeVar("T")


@dataclass(frozen=True)
class MatchGroup:
    kind: MatchKind
    a: Annotation | None
    b: Annotation | None
    ancestor: bool = False
    modifiers_differ: bool = False


@dataclass(frozen=True)
class Agreement:
    """Pairwise agreement of two annotation sets of one document (D1).

    The counts allow micro-averaging over documents.
    """

    annotation_strict_f1: float
    annotation_tolerant_f1: float
    mention_strict_f1: float
    mention_tolerant_f1: float
    term_f1: float
    modifier_agreement: float | None
    equal: int
    compatible: int
    axis_conflicts: int
    term_conflicts: int
    a_only: int
    b_only: int
    mentions_a: int
    mentions_b: int
    mentions_equal: int
    mentions_compatible: int
    terms_a: int
    terms_b: int
    terms_equal: int


def mention_key(mention: Mention, text: str) -> MentionKey:
    """A mention as its set of normalised segments; empty if nothing is left."""
    return frozenset(
        interval
        for seg in mention.segments
        if (interval := normalize_segment(text, seg)) is not None
    )


def _keys(annotation: Annotation, text: str) -> frozenset[MentionKey]:
    return frozenset(
        key for mention in annotation.mentions if (key := mention_key(mention, text))
    )


def _overlap(x: MentionKey, y: MentionKey) -> bool:
    return any(s1 < e2 and s2 < e1 for s1, e1 in x for s2, e2 in y)


def _covered(keys: frozenset[MentionKey]) -> set[int]:
    return {point for key in keys for start, end in key for point in range(start, end)}


def _relation(a: Annotation, b: Annotation, text: str) -> Relation:
    keys_a, keys_b = _keys(a, text), _keys(b, text)
    if (a.mentions and not keys_a) or (b.mentions and not keys_b):
        return "unusable"
    if not keys_a and not keys_b:
        return "identical"
    if not keys_a or not keys_b:
        return "document"
    if keys_a == keys_b:
        return "identical"
    if any(_overlap(x, y) for x in keys_a for y in keys_b):
        return "overlapping"
    return "disjoint"


def _axes(annotation: Annotation) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((axis, value.value) for axis, value in annotation.axes.items()))


def classify(a: Annotation, b: Annotation, text: str) -> MatchKind | None:
    """How two annotations of the same layer relate; None if they do not meet."""
    relation = _relation(a, b, text)
    if relation in ("unusable", "disjoint"):
        return None
    same_term = a.term_id == b.term_id
    same = same_term and _axes(a) == _axes(b)
    if relation == "document":
        return "compatible" if same else None
    if same:
        return "equal" if relation == "identical" else "compatible"
    if not a.mentions and not b.mentions and not same_term:
        return None
    return "axis_conflict" if same_term else "term_conflict"


def assign(weights: Sequence[Sequence[int]]) -> list[tuple[int, int]]:
    """A maximum-weight assignment (Hungarian method); weight 0 means no pair.

    Returns (row, column) pairs with positive weight, sorted by row.
    """
    rows = len(weights)
    cols = len(weights[0]) if rows else 0
    size = max(rows, cols)
    if size == 0:
        return []
    top = max((w for row in weights for w in row), default=0)
    cost = [
        [top - (weights[i][j] if i < rows and j < cols else 0) for j in range(size)]
        for i in range(size)
    ]
    infinity = (top + 1) * (size + 1) * 10
    u = [0] * (size + 1)
    v = [0] * (size + 1)
    owner = [0] * (size + 1)
    way = [0] * (size + 1)
    for i in range(1, size + 1):
        owner[0] = i
        j0 = 0
        minv = [infinity] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0 = owner[j0]
            delta = infinity
            j1 = 0
            for j in range(1, size + 1):
                if not used[j]:
                    current = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if current < minv[j]:
                        minv[j] = current
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(size + 1):
                if used[j]:
                    u[owner[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if owner[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            owner[j0] = owner[j1]
            j0 = j1
    pairs = [
        (owner[j] - 1, j - 1)
        for j in range(1, size + 1)
        if owner[j] - 1 < rows and j - 1 < cols and weights[owner[j] - 1][j - 1] > 0
    ]
    return sorted(pairs)


def _best_pairs(
    left: Sequence[T],
    right: Sequence[T],
    kind_of: Callable[[T, T], tuple[int, int] | None],
    text_length: int,
) -> list[tuple[int, int]]:
    """Pairs maximising the number of pairs per level, from the highest level
    down, then the shared codepoints. ``kind_of`` gives (level >= 1, shared)."""
    if not left or not right:
        return []
    base = min(len(left), len(right)) + 1
    scale = base * (text_length + 1)
    weights = []
    for x in left:
        row = []
        for y in right:
            found = kind_of(x, y)
            row.append(0 if found is None else base ** found[0] * scale + found[1])
        weights.append(row)
    return assign(weights)


def _start(annotation: Annotation, text: str) -> tuple[int, int, str]:
    starts = [start for key in _keys(annotation, text) for start, _ in key]
    return (
        (0, min(starts), annotation.annotation_id)
        if starts
        else (1, 0, annotation.annotation_id)
    )


def match_annotations(
    a: Sequence[Annotation],
    b: Sequence[Annotation],
    text: str,
    ontology: OntologyView | None = None,
) -> list[MatchGroup]:
    """Pair the annotations of two sets; groups come in text order."""
    groups: list[MatchGroup] = []
    for layer in sorted({x.layer_id for x in a} | {y.layer_id for y in b}):
        left = sorted(
            (x for x in a if x.layer_id == layer), key=lambda x: _start(x, text)
        )
        right = sorted(
            (y for y in b if y.layer_id == layer), key=lambda y: _start(y, text)
        )

        def kind_of(x: Annotation, y: Annotation) -> tuple[int, int] | None:
            kind = classify(x, y, text)
            if kind is None:
                return None
            shared = len(_covered(_keys(x, text)) & _covered(_keys(y, text)))
            return _LEVEL[kind] + 1, shared

        pairs = _best_pairs(left, right, kind_of, len(text))
        for i, j in pairs:
            x, y = left[i], right[j]
            kind = classify(x, y, text)
            assert kind is not None
            ancestor = (
                kind == "term_conflict"
                and ontology is not None
                and (
                    x.term_id in ontology.ancestors(y.term_id)
                    or y.term_id in ontology.ancestors(x.term_id)
                )
            )
            modifiers_differ = x.term_id == y.term_id and (
                {m.term_id for m in x.modifiers} != {m.term_id for m in y.modifiers}
            )
            groups.append(MatchGroup(kind, x, y, ancestor, modifiers_differ))
        paired_a = {i for i, _ in pairs}
        paired_b = {j for _, j in pairs}
        groups.extend(
            MatchGroup("a_only", x, None)
            for i, x in enumerate(left)
            if i not in paired_a
        )
        groups.extend(
            MatchGroup("b_only", None, y)
            for j, y in enumerate(right)
            if j not in paired_b
        )
    return sorted(groups, key=lambda group: _group_order(group, text))


def _group_order(group: MatchGroup, text: str) -> tuple[int, int, int, str, str]:
    """Text position first; document-level groups last; set A before set B."""
    sides = [side for side in (group.a, group.b) if side is not None]
    unplaced, start = min(_start(side, text)[:2] for side in sides)
    a_id = group.a.annotation_id if group.a else ""
    b_id = group.b.annotation_id if group.b else ""
    return (unplaced, start, 0 if group.a else 1, a_id, b_id)


_Unit = tuple[str, str, tuple[tuple[str, str], ...], MentionKey]


def _mention_units(annotations: Sequence[Annotation], text: str) -> list[_Unit]:
    return [
        (x.layer_id, x.term_id, _axes(x), mention_key(mention, text))
        for x in annotations
        for mention in x.mentions
    ]


def _mention_matches(
    a: Sequence[Annotation], b: Sequence[Annotation], text: str
) -> tuple[int, int]:
    """Equal and compatible mention pairs: same layer, term and axes (D1)."""
    by_label_a: dict[tuple[str, str, tuple[tuple[str, str], ...]], list[MentionKey]] = (
        defaultdict(list)
    )
    by_label_b: dict[tuple[str, str, tuple[tuple[str, str], ...]], list[MentionKey]] = (
        defaultdict(list)
    )
    for layer, term, axes, key in _mention_units(a, text):
        by_label_a[(layer, term, axes)].append(key)
    for layer, term, axes, key in _mention_units(b, text):
        by_label_b[(layer, term, axes)].append(key)

    def kind_of(x: MentionKey, y: MentionKey) -> tuple[int, int] | None:
        if not x or not y:
            return None
        shared = len(_covered(frozenset({x})) & _covered(frozenset({y})))
        if x == y:
            return 2, shared
        return (1, shared) if _overlap(x, y) else None

    equal = compatible = 0
    for label in sorted(set(by_label_a) & set(by_label_b)):
        left = sorted(by_label_a[label], key=sorted)
        right = sorted(by_label_b[label], key=sorted)
        for i, j in _best_pairs(left, right, kind_of, len(text)):
            if left[i] == right[j]:
                equal += 1
            else:
                compatible += 1
    return equal, compatible


def _f1(true_positives: int, n_a: int, n_b: int) -> float:
    return 1.0 if n_a + n_b == 0 else 2 * true_positives / (n_a + n_b)


def agreement(
    a: Sequence[Annotation],
    b: Sequence[Annotation],
    text: str,
    ontology: OntologyView | None = None,
) -> Agreement:
    """Pairwise agreement: annotation, mention and term level, plus modifiers."""
    groups = match_annotations(a, b, text, ontology)
    count = Counter(group.kind for group in groups)
    terms_a = {(x.layer_id, x.term_id, _axes(x)) for x in a}
    terms_b = {(y.layer_id, y.term_id, _axes(y)) for y in b}
    paired = [g for g in groups if g.kind in ("equal", "compatible")]
    mentions_a = sum(len(x.mentions) for x in a)
    mentions_b = sum(len(y.mentions) for y in b)
    mentions_equal, mentions_compatible = _mention_matches(a, b, text)
    agreeing = sum(not g.modifiers_differ for g in paired)
    return Agreement(
        annotation_strict_f1=_f1(count["equal"], len(a), len(b)),
        annotation_tolerant_f1=_f1(
            count["equal"] + count["compatible"], len(a), len(b)
        ),
        mention_strict_f1=_f1(mentions_equal, mentions_a, mentions_b),
        mention_tolerant_f1=_f1(
            mentions_equal + mentions_compatible, mentions_a, mentions_b
        ),
        term_f1=_f1(len(terms_a & terms_b), len(terms_a), len(terms_b)),
        modifier_agreement=agreeing / len(paired) if paired else None,
        equal=count["equal"],
        compatible=count["compatible"],
        axis_conflicts=count["axis_conflict"],
        term_conflicts=count["term_conflict"],
        a_only=count["a_only"],
        b_only=count["b_only"],
        mentions_a=mentions_a,
        mentions_b=mentions_b,
        mentions_equal=mentions_equal,
        mentions_compatible=mentions_compatible,
        terms_a=len(terms_a),
        terms_b=len(terms_b),
        terms_equal=len(terms_a & terms_b),
    )
