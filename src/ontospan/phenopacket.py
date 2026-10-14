"""Phenopacket v2 export (T1 F9): derived, lossy, with a report of what was left out.

Packets are built as protobuf JSON (camelCase) without depending on the
``phenopackets`` library. ``parse_phenopacket`` parses a packet into the
official classes when the extra ``[phenopacket]`` is installed; that checks
the structure only, not the content.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from typing import Any

from ontospan._version import __version__
from ontospan.models import AnnotatedDocument, Annotation
from ontospan.ontology import OntologyView, is_under
from ontospan.profiles import hpo
from ontospan.refs import annotation_ref

MANUAL = {"id": "ECO:0000218", "label": "manual assertion"}
AUTOMATIC = {
    "id": "ECO:0007636",
    "label": "computational evidence used in automatic assertion",
}
EXPERIENCER_COUNTERS = {
    "family_member": "omitted_family",
    "other": "omitted_other_person",
    "unknown": "omitted_unknown_experiencer",
}


@dataclass
class ExportReport:
    """What the export did with each annotation, by category."""

    exported: int = 0
    omitted_family: int = 0
    omitted_other_person: int = 0
    omitted_unknown_experiencer: int = 0
    omitted_uncertain: int = 0
    uncertain_included: int = 0
    # Annotations of layers that are not hpo-phenotype.
    skipped_other_layers: int = 0
    # Exported, but a Phenopacket feature cannot say "in the past".
    historical: int = 0
    # Frequency modifiers are cohort concepts; exported as modifiers.
    frequency_modifiers: int = 0

    def add(self, other: ExportReport) -> None:
        for item in fields(self):
            setattr(
                self, item.name, getattr(self, item.name) + getattr(other, item.name)
            )


def _term(ontology: OntologyView, term_id: str) -> dict[str, str]:
    return {"id": term_id, "label": ontology.label(term_id) or term_id}


def _value(annotation: Annotation, axis: str) -> str | None:
    given = annotation.axes.get(axis)
    return given.value if given is not None else None


def _feature(
    annotation: Annotation,
    ontology: OntologyView,
    reference: str,
    report: ExportReport,
) -> dict[str, Any]:
    feature: dict[str, Any] = {"type": _term(ontology, annotation.term_id)}
    if _value(annotation, "assertion") == "absent":
        feature["excluded"] = True
    others: list[dict[str, str]] = []
    for modifier in annotation.modifiers:
        term = modifier.term_id
        if "severity" not in feature and is_under(ontology, term, hpo.SEVERITY):
            feature["severity"] = _term(ontology, term)
        elif "onset" not in feature and is_under(ontology, term, hpo.ONSET):
            feature["onset"] = {"ontologyClass": _term(ontology, term)}
        else:
            if is_under(ontology, term, hpo.FREQUENCY):
                report.frequency_modifiers += 1
            others.append(_term(ontology, term))
    if others:
        feature["modifiers"] = others
    code = AUTOMATIC if annotation.provenance.actor.kind == "tool" else MANUAL
    evidence: dict[str, Any] = {"evidenceCode": code, "reference": {"id": reference}}
    if _value(annotation, "assertion") == "uncertain":
        description = "assertion: uncertain (suspected, not confirmed)"
        evidence["reference"]["description"] = description
    feature["evidence"] = [evidence]
    return feature


def _features(
    unit: AnnotatedDocument,
    ontology: OntologyView,
    include_uncertain: bool,
    bundle_id: str | None,
    report: ExportReport,
) -> list[dict[str, Any]]:
    hpo_layers = {
        layer.layer_id
        for layer in unit.annotation_set.layers
        if layer.profile == hpo.NAME
    }
    set_id = unit.annotation_set.annotation_set_id
    features: list[dict[str, Any]] = []
    for annotation in unit.annotation_set.annotations:
        if annotation.layer_id not in hpo_layers:
            report.skipped_other_layers += 1
            continue
        experiencer = _value(annotation, "experiencer")
        if experiencer != "patient":
            counter = EXPERIENCER_COUNTERS.get(
                experiencer or "unknown", "omitted_unknown_experiencer"
            )
            setattr(report, counter, getattr(report, counter) + 1)
            continue
        if _value(annotation, "assertion") == "uncertain":
            if not include_uncertain:
                report.omitted_uncertain += 1
                continue
            report.uncertain_included += 1
        if _value(annotation, "temporality") == "historical":
            report.historical += 1
        reference = annotation_ref(set_id, annotation.annotation_id, bundle_id)
        features.append(_feature(annotation, ontology, reference, report))
        report.exported += 1
    return features


def _resources(units: Sequence[AnnotatedDocument]) -> list[dict[str, str]]:
    versions = sorted(
        {
            layer.ontology.version
            for unit in units
            for layer in unit.annotation_set.layers
            if layer.profile == hpo.NAME
        }
    )
    return [
        {
            "id": "hp",
            "name": "human phenotype ontology",
            "url": "http://purl.obolibrary.org/obo/hp.owl",
            "version": version,
            "namespacePrefix": "HP",
            "iriPrefix": "http://purl.obolibrary.org/obo/HP_",
        }
        for version in versions
    ]


def _created(created_at: datetime | None) -> str:
    if created_at is None:
        created_at = datetime.now(UTC)
    if created_at.tzinfo is None:
        raise ValueError("created_at needs a time zone")
    return created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _packet(
    packet_id: str,
    subject_id: str | None,
    units: Sequence[AnnotatedDocument],
    ontology: OntologyView,
    include_uncertain: bool,
    bundle_id: str | None,
    created: str,
) -> tuple[dict[str, Any], ExportReport]:
    report = ExportReport()
    features = [
        feature
        for unit in units
        for feature in _features(unit, ontology, include_uncertain, bundle_id, report)
    ]
    packet: dict[str, Any] = {"id": packet_id}
    if subject_id:
        packet["subject"] = {"id": subject_id}
    packet["phenotypicFeatures"] = features
    packet["metaData"] = {
        "created": created,
        "createdBy": f"ontospan {__version__}",
        "resources": _resources(units),
        "phenopacketSchemaVersion": "2.0",
    }
    return packet, report


def to_phenopacket(
    unit: AnnotatedDocument,
    ontology: OntologyView,
    *,
    include_uncertain: bool = False,
    bundle_id: str | None = None,
    created_at: datetime | None = None,
    phenopacket_id: str | None = None,
) -> tuple[dict[str, Any], ExportReport]:
    """One Phenopacket for one annotated document, from its hpo-phenotype layers."""
    document = unit.document
    return _packet(
        phenopacket_id or document.document_id,
        document.subject_id,
        [unit],
        ontology,
        include_uncertain,
        bundle_id,
        _created(created_at),
    )


def to_phenopackets(
    units: Sequence[AnnotatedDocument],
    ontology: OntologyView,
    *,
    group_by_subject: bool = True,
    include_uncertain: bool = False,
    bundle_id: str | None = None,
    created_at: datetime | None = None,
) -> list[tuple[dict[str, Any], ExportReport]]:
    """Packets for many units: one per subject_id if grouped, else one per unit.

    Units without ``subject_id`` always get a packet of their own.
    """
    created = _created(created_at)
    groups: dict[str, list[AnnotatedDocument]] = {}
    subjects: dict[str, str | None] = {}
    for unit in units:
        subject = unit.document.subject_id
        key = (
            f"subject:{subject}"
            if group_by_subject and subject
            else f"unit:{len(groups)}"
        )
        if key not in groups:
            groups[key] = []
            subjects[key] = subject
        groups[key].append(unit)
    packets = []
    for key, members in groups.items():
        subject = subjects[key]
        packet_id = (
            subject if group_by_subject and subject else members[0].document.document_id
        )
        packets.append(
            _packet(
                packet_id,
                subject,
                members,
                ontology,
                include_uncertain,
                bundle_id,
                created,
            )
        )
    return packets


def parse_phenopacket(packet: dict[str, Any]) -> Any:
    """Parse into the official ``Phenopacket`` class (structure only).

    Raises on unknown or malformed fields. It does not check content: even
    ``{}`` parses. Needs the extra ``[phenopacket]``.
    """
    from google.protobuf.json_format import ParseDict
    from phenopackets import Phenopacket

    return ParseDict(packet, Phenopacket())
