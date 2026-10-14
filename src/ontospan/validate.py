"""Validation, loading and dumping of annotated documents."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from functools import cache
from importlib import resources
from typing import Any, NamedTuple

import jsonschema
from pydantic import BaseModel, ValidationError

from ontospan._version import SCHEMA_VERSION
from ontospan.models import Actor, AnnotatedDocument, Layer, Segment
from ontospan.ontology import OntologyView
from ontospan.profiles import HIERARCHICAL_PROFILES, PROFILES, Context
from ontospan.refs import parse_annotation_ref
from ontospan.report import FormatError, Level, ValidationReport, fail
from ontospan.schema import DOCUMENT, schema_name
from ontospan.segments import normalize_segment
from ontospan.text import canonical_text, text_sha256

SUPPORTED_MAJOR, SUPPORTED_MINOR = (int(p) for p in SCHEMA_VERSION.split(".")[:2])
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
FORMAT_CHECKER = jsonschema.FormatChecker(formats=())


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _date_time(value: object) -> bool:
    """RFC 3339 with a time zone, checked without extra dependencies."""
    if not isinstance(value, str):
        return True
    if not _RFC3339.match(value):
        raise ValueError(f"{value!r} is not a date-time with a time zone")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return True


class Version(NamedTuple):
    major: int
    minor: int

    @property
    def newer(self) -> bool:
        """A newer minor version than this package knows."""
        return self.minor > SUPPORTED_MINOR


@cache
def schema_validator(name: str) -> jsonschema.Draft202012Validator:
    files = resources.files("ontospan.schema")
    schema = json.loads(files.joinpath(name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def _path(parts: Iterable[Any]) -> str:
    return ".".join(str(part) for part in parts) or "$"


def check_version(value: object, report: ValidationReport) -> Version | None:
    """Record version problems; None if the data must not be read at all."""
    parts = value.split(".") if isinstance(value, str) else []
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        report.add("error", "schema_version", "schema_version", f"invalid {value!r}")
        return None
    version = Version(int(parts[0]), int(parts[1]))
    if version.major != SUPPORTED_MAJOR:
        message = f"major version {version.major} is not supported"
        report.add("error", "unsupported_major", "schema_version", message)
        return None
    if version.newer:
        message = f"{value} is newer than {SCHEMA_VERSION}; unknown parts are kept"
        report.add("warning", "newer_minor", "schema_version", message)
    return version


def check_schema(
    data: Mapping[str, Any], kind: str, version: Version, report: ValidationReport
) -> None:
    """Strict check against the schema file of the declared version.

    A newer minor version has no schema here; it is read leniently.
    """
    if version.newer:
        return
    name = schema_name(kind, f"{version.major}.{version.minor}.0")
    if not resources.files("ontospan.schema").joinpath(name).is_file():
        report.add("error", "schema_unavailable", "schema_version", f"{name} missing")
        return
    errors = schema_validator(name).iter_errors(data)
    for error in sorted(errors, key=lambda e: [str(p) for p in e.absolute_path]):
        report.add("error", "schema", _path(error.absolute_path), error.message)


def _parse(
    data: object, report: ValidationReport
) -> tuple[AnnotatedDocument, Version] | None:
    if not isinstance(data, Mapping):
        report.add("error", "not_an_object", "$", "an annotated document is an object")
        return None
    version = check_version(data.get("schema_version"), report)
    if version is None:
        return None
    check_schema(data, DOCUMENT, version, report)
    if not report.ok:
        return None
    try:
        return AnnotatedDocument.model_validate(data), version
    except ValidationError as exc:
        for error in exc.errors():
            report.add("error", "model", _path(error["loc"]), error["msg"])
        return None


def _check_segments(
    segments: Sequence[Segment],
    text: str,
    path: str,
    report: ValidationReport,
    *,
    matched: bool = False,
) -> None:
    previous_end = -1
    for index, seg in enumerate(segments):
        where = f"{path}[{index}]"
        if seg.end > len(text):
            message = f"segment ends at {seg.end}, text has {len(text)} codepoints"
            report.add("error", "segment_out_of_range", where, message)
            continue
        quoted = text[seg.start : seg.end]
        if quoted != seg.text:
            message = f"expected {quoted!r}, got {seg.text!r}"
            report.add("error", "segment_text_mismatch", where, message)
        elif matched and normalize_segment(text, seg) is None:
            message = "only whitespace or punctuation: it never matches"
            report.add("warning", "empty_after_normalization", where, message)
        if seg.start < previous_end:
            message = "segments must be sorted and must not overlap"
            report.add("error", "segments_unordered", where, message)
        previous_end = seg.end


def _check_actor(actor: Actor, path: str, report: ValidationReport) -> None:
    if actor.kind == "tool" and not (actor.name and actor.version):
        message = "a tool actor should name the tool and its version"
        report.add("warning", "tool_identity", path, message)


def _check_layers(
    unit: AnnotatedDocument,
    version: Version,
    ontologies: Mapping[str, OntologyView],
    report: ValidationReport,
) -> dict[str, Layer]:
    layers: dict[str, Layer] = {}
    for index, layer in enumerate(unit.annotation_set.layers):
        where = f"annotation_set.layers[{index}]"
        if layer.layer_id in layers:
            message = f"layer {layer.layer_id!r} is declared twice"
            report.add("error", "duplicate_layer", where, message)
        layers[layer.layer_id] = layer
        ontology = ontologies.get(layer.ontology.id)
        if layer.profile not in PROFILES:
            level: Level = "warning" if version.newer else "error"
            message = f"unknown profile {layer.profile!r}; annotations not checked"
            report.add(level, "unknown_profile", f"{where}.profile", message)
        elif layer.profile in HIERARCHICAL_PROFILES and ontology is None:
            message = f"no ontology {layer.ontology.id!r}: terms were not checked"
            report.add("warning", "hierarchy_not_checked", where, message)
        if ontology is not None and ontology.release not in (
            None,
            layer.ontology.version,
        ):
            message = (
                f"layer uses {layer.ontology.version}, ontology is {ontology.release}"
            )
            report.add("warning", "ontology_release_mismatch", where, message)
    return layers


def _check_content(
    unit: AnnotatedDocument,
    version: Version,
    ontologies: Mapping[str, OntologyView],
    report: ValidationReport,
    *,
    require_chosen_axes: bool,
    require_tool_identity: bool,
) -> None:
    text = unit.document.text
    if canonical_text(text) != text:
        message = "text must be NFC with LF line endings and no BOM"
        report.add("error", "text_not_canonical", "document.text", message)
    if text_sha256(text) != unit.document.text_sha256:
        report.add("error", "text_hash", "document.text_sha256", "hash does not match")
    if require_tool_identity:
        for index, actor in enumerate(unit.annotation_set.actors):
            _check_actor(actor, f"annotation_set.actors[{index}]", report)

    layers = _check_layers(unit, version, ontologies, report)
    seen: set[str] = set()
    for index, annotation in enumerate(unit.annotation_set.annotations):
        path = f"annotation_set.annotations[{index}]"
        if annotation.annotation_id in seen:
            message = f"annotation id {annotation.annotation_id!r} is used twice"
            report.add("error", "duplicate_annotation", path, message)
        seen.add(annotation.annotation_id)
        for r, ref in enumerate(annotation.provenance.source_refs):
            try:
                parse_annotation_ref(ref)
            except ValueError as exc:
                where = f"{path}.provenance.source_refs[{r}]"
                report.add("error", "source_ref_syntax", where, str(exc))
        if require_tool_identity:
            _check_actor(
                annotation.provenance.actor, f"{path}.provenance.actor", report
            )
        if require_chosen_axes:
            for axis, value in annotation.axes.items():
                if value.basis != "chosen":
                    where = f"{path}.axes.{axis}"
                    report.add("error", "axis_not_chosen", where, f"{axis} not chosen")
        declared = layers.get(annotation.layer_id)
        if declared is None:
            message = f"layer {annotation.layer_id!r} is not declared"
            report.add("error", "unknown_layer", f"{path}.layer_id", message)
            continue
        for m, mention in enumerate(annotation.mentions):
            where = f"{path}.mentions[{m}]"
            _check_segments(
                mention.segments, text, f"{where}.segments", report, matched=True
            )
            _check_segments(mention.cue_segments, text, f"{where}.cue_segments", report)
        for m, modifier in enumerate(annotation.modifiers):
            where = f"{path}.modifiers[{m}].segments"
            _check_segments(modifier.segments, text, where, report)
        checker = PROFILES.get(declared.profile)
        if checker is not None:
            ontology = ontologies.get(declared.ontology.id)
            ctx = Context(path, ontology, version.newer)
            report.issues.extend(checker(declared, annotation, ctx))


def validate(
    data: object,
    ontologies: Mapping[str, OntologyView] | None = None,
    *,
    require_chosen_axes: bool = False,
    require_tool_identity: bool = False,
) -> ValidationReport:
    """Every problem of an annotated document; nothing is raised.

    ``ontologies`` maps ontology ids such as "hp" to an ``OntologyView``.
    ``require_chosen_axes`` (project option, T1 F8) makes defaulted axes errors.
    ``require_tool_identity`` warns about tool actors without name and version.
    """
    report = ValidationReport()
    raw = data.model_dump(mode="json") if isinstance(data, AnnotatedDocument) else data
    parsed = _parse(raw, report)
    if parsed is not None:
        unit, version = parsed
        _check_content(
            unit,
            version,
            ontologies or {},
            report,
            require_chosen_axes=require_chosen_axes,
            require_tool_identity=require_tool_identity,
        )
    return report


def load_annotated_document(
    data: bytes | str | Mapping[str, Any],
    ontologies: Mapping[str, OntologyView] | None = None,
) -> AnnotatedDocument:
    """Parse and validate; raises ``FormatError`` on any error."""
    raw: object = data
    if isinstance(data, bytes | str):
        try:
            raw = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise fail("invalid_json", "$", str(exc)) from exc
    report = validate(raw, ontologies)
    if not report.ok:
        raise FormatError(report)
    return AnnotatedDocument.model_validate(raw)


def dump_json(model: BaseModel) -> bytes:
    """Stable UTF-8 JSON: sorted keys, two-space indent, LF, trailing newline."""
    data = model.model_dump(mode="json")
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")
