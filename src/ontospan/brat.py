"""brat standoff export (``.txt`` and ``.ann``): derived, lossy, with a report.

The ``.txt`` file is the canonical text. brat offsets count codepoints of that
text, like ontospan offsets, so they are written unchanged. Write both files
as UTF-8 without newline translation (``newline=""``).

- One text-bound entity ``T`` per mention; its type is the layer id. A
  discontinuous mention has one fragment per segment (``start end;start
  end``). A brat fragment cannot cross a line break, so segments that do are
  split there.
- The annotation's term is a normalization ``N`` (``Reference T1
  HP:0001250``) with the label from the ontology, or the term id without one.
- Each axis value is an attribute ``A`` (``assertion T1 present``); its basis
  is not written.
- An annotator note ``#`` per entity keeps the rest as ``key=value`` pairs
  separated by ``; ``: ``ref`` (``urn:ontospan:...``), ``mention`` (index from
  1), ``modifiers``, ``annotator``, ``annotator_kind``, ``method``,
  ``source_refs``, ``note``, and the reviewer resolution (``review_outcome``,
  ``reviewer``, ``reviewer_kind``, ``review_note``).
- Annotations without mentions (document level) have no place in brat: they
  are not written and their references are listed in ``report.dropped``.
- Cue segments and modifier segments are not written (see the report).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from ontospan._interchange import (
    ConversionReport,
    count_dropped_segments,
    ordered_mentions,
    spanless,
)
from ontospan.models import AnnotatedDocument, Annotation, Mention
from ontospan.ontology import OntologyView
from ontospan.refs import annotation_ref

__all__ = ["BratFiles", "ConversionReport", "to_brat"]

_TOKEN = re.compile(r"\S+")
_BREAKS = re.compile(r"[\t\n\r]")


class BratFiles(NamedTuple):
    txt: str
    ann: str


def _token(value: str, what: str) -> str:
    if _TOKEN.fullmatch(value) is None:
        raise ValueError(f"brat {what} cannot contain whitespace: {value!r}")
    return value


def _fragments(mention: Mention, report: ConversionReport) -> list[tuple[int, int]]:
    """Segments as fragments, split at line breaks."""
    fragments = []
    for seg in mention.segments:
        if "\n" in seg.text:
            report.split_at_line_breaks += 1
        start = seg.start
        for piece in seg.text.split("\n"):
            if piece:
                fragments.append((start, start + len(piece)))
            start += len(piece) + 1
    return fragments


def _note(
    annotation: Annotation, ref: str, mention: int, report: ConversionReport
) -> str:
    parts = [("ref", ref), ("mention", str(mention))]
    if annotation.modifiers:
        parts.append(("modifiers", " ".join(m.term_id for m in annotation.modifiers)))
    provenance = annotation.provenance
    parts += [
        ("annotator", provenance.actor.actor_id),
        ("annotator_kind", provenance.actor.kind),
        ("method", provenance.method),
    ]
    if provenance.source_refs:
        parts.append(("source_refs", " ".join(provenance.source_refs)))
    parts += [("note", note) for note in provenance.notes]
    resolution = annotation.review_resolution
    if resolution is not None:
        parts += [
            ("review_outcome", resolution.outcome),
            ("reviewer", resolution.reviewer.actor_id),
            ("reviewer_kind", resolution.reviewer.kind),
        ]
        if resolution.note is not None:
            parts.append(("review_note", resolution.note))
    text = "; ".join(f"{key}={value}" for key, value in parts)
    flat = _BREAKS.sub(" ", text)
    if flat != text:
        report.note_text_flattened += 1
    return flat


def to_brat(
    unit: AnnotatedDocument,
    ontology: OntologyView | None = None,
    *,
    bundle_id: str | None = None,
) -> tuple[BratFiles, ConversionReport]:
    """The brat ``.txt`` and ``.ann`` of one unit and what the export left out.

    ``ontology`` only adds labels to the normalizations. ``bundle_id`` goes
    into the ``ref`` of each note. Ids (``T1``, ``N1``, ``A1``, ``#1``) are
    numbered in text order. Raises ValueError for layer ids, axis names or
    axis values with whitespace, which brat cannot parse.
    """
    text = unit.document.text
    set_id = unit.annotation_set.annotation_set_id
    annotations = unit.annotation_set.annotations
    report = ConversionReport()
    lines: list[str] = []
    counters = {"T": 0, "N": 0, "A": 0, "#": 0}

    def next_id(kind: str) -> str:
        counters[kind] += 1
        return f"{kind}{counters[kind]}"

    written: set[str] = set()
    for annotation, index, mention in ordered_mentions(annotations):
        fragments = _fragments(mention, report)
        if not fragments:
            continue
        entity = next_id("T")
        layer = _token(annotation.layer_id, "entity type")
        spans = ";".join(f"{start} {end}" for start, end in fragments)
        quoted = " ".join(text[start:end] for start, end in fragments)
        lines.append(f"{entity}\t{layer} {spans}\t{quoted}")
        label = ontology.label(annotation.term_id) if ontology is not None else None
        term = _token(annotation.term_id, "normalization")
        lines.append(
            f"{next_id('N')}\tReference {entity} {term}\t{label or annotation.term_id}"
        )
        for axis in sorted(annotation.axes):
            name = _token(axis, "attribute name")
            value = _token(annotation.axes[axis].value, "attribute value")
            lines.append(f"{next_id('A')}\t{name} {entity} {value}")
            report.axis_basis_dropped += 1
        ref = annotation_ref(set_id, annotation.annotation_id, bundle_id)
        note = _note(annotation, ref, index + 1, report)
        lines.append(f"{next_id('#')}\tAnnotatorNotes {entity}\t{note}")
        report.mentions += 1
        report.discontinuous += len(mention.segments) > 1
        written.add(annotation.annotation_id)
    for annotation in annotations:
        count_dropped_segments(annotation, report)
        if annotation.annotation_id in written:
            report.exported += 1
    report.spanless = len(spanless(annotations))
    report.dropped = sorted(
        annotation_ref(set_id, annotation.annotation_id, bundle_id)
        for annotation in annotations
        if annotation.annotation_id not in written
    )
    ann = "".join(f"{line}\n" for line in lines)
    return BratFiles(txt=text, ann=ann), report
