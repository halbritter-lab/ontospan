"""Builders for test data around one fixed German sample text."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ontospan.models import (
    Actor,
    AnnotatedDocument,
    Annotation,
    AnnotationSet,
    AxisValue,
    Document,
    Layer,
    Mention,
    Modifier,
    OntologyResource,
    Provenance,
    Translation,
    TranslationCheck,
    Variant,
)
from ontospan.text import make_document, segment, text_sha256

FIXTURES = Path(__file__).parent / "fixtures"
TEXT = "Keine Krampfanfälle in der Neonatalzeit. Seit 2 Wochen schwere Krampfanfälle."
SEIZURE = "HP:0001250"
DIALEPTIC = "HP:0011146"
SEVERE = "HP:0012828"
HPO_LAYER = Layer(
    layer_id="hpo",
    profile="hpo-phenotype",
    ontology=OntologyResource(id="hp", version="2026-06-23"),
)
CREATED = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
# The English source of the German sample text, for translation variants.
SOURCE_TEXT = "No seizures in the neonatal period. Severe seizures for 2 weeks."
SOURCE_SHA256 = text_sha256(SOURCE_TEXT)
MACHINE_TRANSLATION = Translation(
    provider="test-mt",
    model="m1",
    run_id="run-1",
    recipe="recipe-1",
    checks=(
        TranslationCheck(code="units_added", passed=True),
        TranslationCheck(code="length_ratio", passed=False, detail="0.4"),
    ),
)


def axes(
    assertion: str = "present",
    experiencer: str = "patient",
    temporality: str = "current",
    basis: Any = "chosen",
) -> dict[str, AxisValue]:
    return {
        "assertion": AxisValue(value=assertion, basis=basis),
        "experiencer": AxisValue(value=experiencer, basis=basis),
        "temporality": AxisValue(value=temporality, basis=basis),
    }


def annotation(
    annotation_id: str,
    term_id: str,
    spans: Sequence[tuple[int, int] | Sequence[tuple[int, int]]],
    *,
    text: str = TEXT,
    axes_: dict[str, AxisValue] | None = None,
    cues: Sequence[tuple[int, int]] = (),
    modifiers: Sequence[tuple[str, Sequence[tuple[int, int]]]] = (),
    actor: str = "ann-03",
    kind: Any = "human",
    method: Any = "manual",
    document_level: bool = False,
    layer_id: str = "hpo",
    source_refs: Sequence[str] = (),
) -> Annotation:
    """One annotation. A span (start, end) is a mention with one segment; a list
    of spans is one discontinuous mention. Cues go to the first mention."""
    mentions = []
    for index, span in enumerate(spans):
        parts = [span] if isinstance(span[0], int) else list(span)
        mentions.append(
            Mention(
                segments=tuple(segment(text, s, e) for s, e in parts),
                cue_segments=tuple(segment(text, s, e) for s, e in cues)
                if index == 0
                else (),
            )
        )
    return Annotation(
        annotation_id=annotation_id,
        layer_id=layer_id,
        term_id=term_id,
        axes=axes_ if axes_ is not None else axes(),
        mentions=tuple(mentions),
        document_level=document_level,
        modifiers=tuple(
            Modifier(
                term_id=term, segments=tuple(segment(text, s, e) for s, e in where)
            )
            for term, where in modifiers
        ),
        provenance=Provenance(
            actor=Actor(actor_id=actor, kind=kind),
            method=method,
            source_refs=tuple(source_refs),
        ),
    )


def unit(
    annotations: Sequence[Annotation],
    *,
    text: str = TEXT,
    layers: Sequence[Layer] = (HPO_LAYER,),
    set_id: str = "set-1",
    set_kind: Any = "individual",
    subject_id: str | None = None,
    actor: str = "ann-03",
    document_id: str = "doc-1",
) -> AnnotatedDocument:
    return AnnotatedDocument(
        document=make_document(document_id, "de", text, subject_id=subject_id),
        annotation_set=AnnotationSet(
            annotation_set_id=set_id,
            set_kind=set_kind,
            actors=(Actor(actor_id=actor, kind="human"),),
            created_at=CREATED,
            blind=True,
            layers=tuple(layers),
            annotations=tuple(annotations),
        ),
    )


def sample() -> AnnotatedDocument:
    """'Keine Krampfanfälle' (absent, historical) and 'schwere Krampfanfälle'."""
    return unit(
        [
            annotation(
                "a1",
                SEIZURE,
                [(6, 19)],
                cues=[(0, 5)],
                axes_=axes("absent", temporality="historical"),
            ),
            annotation("a2", SEIZURE, [(63, 76)], modifiers=[(SEVERE, [(55, 62)])]),
        ]
    )


def with_variant(
    item: AnnotatedDocument,
    variant: Variant | None,
    translation: Translation | None = None,
    *,
    case_id: str | None = "case-1",
) -> AnnotatedDocument:
    """The unit with format 1.1 variant fields on its document."""
    document = Document.model_validate(
        {
            **item.document.model_dump(),
            "case_id": case_id,
            "variant": variant,
            "translation": translation,
        }
    )
    return item.model_copy(update={"document": document})


def translated_sample() -> AnnotatedDocument:
    """The sample as a machine translation of ``SOURCE_TEXT``."""
    variant = Variant(
        version=1, origin="machine_translation", derived_from=SOURCE_SHA256
    )
    return with_variant(sample(), variant, MACHINE_TRANSLATION)


def corrected_sample() -> AnnotatedDocument:
    """The sample as version 2, a correction of an earlier German text."""
    earlier = text_sha256(TEXT.replace("schwere", "starke"))
    variant = Variant(version=2, origin="correction", derived_from=earlier)
    return with_variant(sample(), variant)
