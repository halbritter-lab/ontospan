"""Shared parts of the BioC and brat exports: the report and the order.

Both exports are derived and lossy like the Phenopacket export. They are pure
functions: the same units give the same output, byte for byte.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from urllib.parse import quote

from ontospan.models import AnnotatedDocument, Annotation, Mention


@dataclass
class ConversionReport:
    """What a BioC or brat export wrote, dropped or approximated."""

    # Annotations written, as entities, BioC annotations or BioC relations.
    exported: int = 0
    # Mentions written; a discontinuous mention is one entity or annotation.
    mentions: int = 0
    # Mentions with more than one segment.
    discontinuous: int = 0
    # Annotations without mentions (document level). BioC writes them as
    # relations without nodes; brat cannot hold them and drops them.
    spanless: int = 0
    # References (``urn:ontospan:...``) of annotations that were not written.
    dropped: list[str] = field(default_factory=list)
    # Cue segments and modifier segments: only the modifier terms are kept.
    cue_segments_dropped: int = 0
    modifier_segments_dropped: int = 0
    # brat: the basis (chosen, defaulted) of axis values is not written.
    axis_basis_dropped: int = 0
    # brat: segments split at line breaks, which a brat fragment cannot cross.
    split_at_line_breaks: int = 0
    # brat: line breaks and tabs in note text replaced by spaces.
    note_text_flattened: int = 0

    def add(self, other: ConversionReport) -> None:
        for item in fields(self):
            setattr(
                self, item.name, getattr(self, item.name) + getattr(other, item.name)
            )


def mention_order(mention: Mention) -> tuple[int, int]:
    return min(seg.start for seg in mention.segments), max(
        seg.end for seg in mention.segments
    )


def ordered_mentions(
    annotations: Sequence[Annotation],
) -> list[tuple[Annotation, int, Mention]]:
    """Every mention with its annotation and index, in text order, then ids."""
    found = [
        (annotation, index, mention)
        for annotation in annotations
        for index, mention in enumerate(annotation.mentions)
    ]
    return sorted(
        found,
        key=lambda item: (
            mention_order(item[2]),
            item[0].layer_id,
            item[0].annotation_id,
            item[1],
        ),
    )


def spanless(annotations: Sequence[Annotation]) -> list[Annotation]:
    """Annotations without mentions, sorted by layer and id."""
    return sorted(
        (annotation for annotation in annotations if not annotation.mentions),
        key=lambda annotation: (annotation.layer_id, annotation.annotation_id),
    )


def count_dropped_segments(annotation: Annotation, report: ConversionReport) -> None:
    report.cue_segments_dropped += sum(
        len(mention.cue_segments) for mention in annotation.mentions
    )
    report.modifier_segments_dropped += sum(
        len(modifier.segments) for modifier in annotation.modifiers
    )


def document_ids(units: Sequence[AnnotatedDocument]) -> list[str]:
    """Document ids; alternative sets of one document get a set-specific id."""
    counts = Counter(unit.document.document_id for unit in units)
    ids = []
    for unit in units:
        document_id = unit.document.document_id
        if counts[document_id] > 1:
            set_id = quote(unit.annotation_set.annotation_set_id, safe="")
            document_id = (
                f"urn:ontospan:document:{quote(document_id, safe='')}:{set_id}"
            )
        ids.append(document_id)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate documents; select distinct document and set ids")
    return ids
