"""ontospan: a shared format for ontology concept annotations on text spans."""

from ontospan._version import SCHEMA_VERSION, __version__
from ontospan.bundle import read_bundle, write_bundle
from ontospan.matching import Agreement, MatchGroup, agreement, match_annotations
from ontospan.models import (
    Actor,
    AnnotatedDocument,
    Annotation,
    AnnotationSet,
    AxisValue,
    Contributor,
    Document,
    Layer,
    Manifest,
    Mention,
    Modifier,
    OntologyResource,
    Producer,
    Provenance,
    ReleaseInfo,
    Segment,
    SupersededRelease,
    Translation,
    TranslationCheck,
    Variant,
    VariantOrigin,
)
from ontospan.ontology import ObographOntology, OntologyView, is_under
from ontospan.phenopacket import (
    ExportReport,
    parse_phenopacket,
    to_phenopacket,
    to_phenopackets,
)
from ontospan.profiles.hpo import default_axes
from ontospan.refs import AnnotationRef, annotation_ref, parse_annotation_ref
from ontospan.report import FormatError, Issue, ValidationReport
from ontospan.segments import normalize_segment, segments_flat, spanning_segment
from ontospan.text import canonical_text, make_document, segment, text_sha256
from ontospan.validate import dump_json, load_annotated_document, validate

__all__ = [
    "SCHEMA_VERSION",
    "Actor",
    "Agreement",
    "AnnotatedDocument",
    "Annotation",
    "AnnotationRef",
    "AnnotationSet",
    "AxisValue",
    "Contributor",
    "Document",
    "ExportReport",
    "FormatError",
    "Issue",
    "Layer",
    "Manifest",
    "MatchGroup",
    "Mention",
    "Modifier",
    "ObographOntology",
    "OntologyResource",
    "OntologyView",
    "Producer",
    "Provenance",
    "ReleaseInfo",
    "Segment",
    "SupersededRelease",
    "Translation",
    "TranslationCheck",
    "ValidationReport",
    "Variant",
    "VariantOrigin",
    "__version__",
    "agreement",
    "annotation_ref",
    "canonical_text",
    "default_axes",
    "dump_json",
    "is_under",
    "load_annotated_document",
    "make_document",
    "match_annotations",
    "normalize_segment",
    "parse_annotation_ref",
    "parse_phenopacket",
    "read_bundle",
    "segment",
    "segments_flat",
    "spanning_segment",
    "text_sha256",
    "to_phenopacket",
    "to_phenopackets",
    "validate",
    "write_bundle",
]
