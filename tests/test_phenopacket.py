from datetime import datetime

import pytest
from builders import CREATED, FIXTURES, HPO_LAYER, SEIZURE, annotation, axes, unit

from ontospan.models import AnnotatedDocument, Layer, OntologyResource
from ontospan.ontology import ObographOntology
from ontospan.phenopacket import parse_phenopacket, to_phenopacket, to_phenopackets


@pytest.fixture(scope="module")
def hp() -> ObographOntology:
    return ObographOntology.load(FIXTURES / "hp-mini.json")


def test_the_sample_exports_absent_and_present_seizure(
    sample_unit: AnnotatedDocument, hp: ObographOntology
) -> None:
    packet, report = to_phenopacket(
        sample_unit, hp, created_at=CREATED, bundle_id="b-1"
    )

    assert packet["id"] == "doc-1"
    absent, present = packet["phenotypicFeatures"]
    assert absent["type"] == {"id": SEIZURE, "label": "Seizure"}
    assert absent["excluded"] is True
    assert "excluded" not in present
    assert present["severity"] == {"id": "HP:0012828", "label": "Severe"}
    evidence = absent["evidence"][0]
    assert evidence["evidenceCode"] == {
        "id": "ECO:0000218",
        "label": "manual assertion",
    }
    assert evidence["reference"]["id"] == "urn:ontospan:b-1:set-1:a1"
    assert packet["metaData"]["resources"][0]["version"] == "2026-06-23"
    assert packet["metaData"]["phenopacketSchemaVersion"] == "2.0"
    assert packet["metaData"]["created"] == "2026-10-14T12:00:00Z"
    assert (report.exported, report.historical) == (2, 1)


def test_references_tell_apart_sets_of_the_same_document(hp: ObographOntology) -> None:
    first = unit([annotation("a1", SEIZURE, [(63, 76)])], set_id="ann-01:set")
    second = unit([annotation("a1", SEIZURE, [(63, 76)])], set_id="ann-02:set")
    refs = [
        to_phenopacket(item, hp, created_at=CREATED)[0]["phenotypicFeatures"][0][
            "evidence"
        ][0]["reference"]["id"]
        for item in (first, second)
    ]
    assert refs == ["urn:ontospan:ann-01%3Aset:a1", "urn:ontospan:ann-02%3Aset:a1"]


def test_uncertain_is_omitted_unless_asked_for(hp: ObographOntology) -> None:
    data = unit([annotation("a1", SEIZURE, [(63, 76)], axes_=axes("uncertain"))])
    packet, report = to_phenopacket(data, hp, created_at=CREATED)
    assert packet["phenotypicFeatures"] == []
    assert report.omitted_uncertain == 1

    packet, report = to_phenopacket(
        data, hp, created_at=CREATED, include_uncertain=True
    )
    feature = packet["phenotypicFeatures"][0]
    assert "excluded" not in feature
    assert "uncertain" in feature["evidence"][0]["reference"]["description"]
    assert report.uncertain_included == 1


def test_only_patient_findings_are_exported_and_the_rest_counted(
    hp: ObographOntology,
) -> None:
    data = unit(
        [
            annotation(
                "a1", SEIZURE, [(6, 19)], axes_=axes(experiencer="family_member")
            ),
            annotation("a2", SEIZURE, [(63, 76)], axes_=axes(experiencer="other")),
            annotation("a3", SEIZURE, [(63, 76)], axes_=axes(experiencer="unknown")),
        ]
    )
    packet, report = to_phenopacket(data, hp, created_at=CREATED)
    assert packet["phenotypicFeatures"] == []
    counts = (
        report.omitted_family,
        report.omitted_other_person,
        report.omitted_unknown_experiencer,
    )
    assert counts == (1, 1, 1)


def test_other_layers_are_skipped_and_counted(hp: ObographOntology) -> None:
    maxo = Layer(
        layer_id="maxo",
        profile="generic",
        ontology=OntologyResource(id="maxo", version="2026-01-01"),
    )
    data = unit(
        [
            annotation("a1", SEIZURE, [(63, 76)]),
            annotation("m1", "MAXO:0000001", [(63, 76)], layer_id="maxo"),
        ],
        layers=[HPO_LAYER, maxo],
    )
    packet, report = to_phenopacket(data, hp, created_at=CREATED)
    assert len(packet["phenotypicFeatures"]) == 1
    assert report.skipped_other_layers == 1


def test_onset_other_modifiers_frequency_and_tool_evidence(
    hp: ObographOntology,
) -> None:
    modifiers = [("HP:0003593", []), ("HP:0012832", []), ("HP:0040282", [])]
    item = annotation(
        "a1",
        SEIZURE,
        [(63, 76)],
        modifiers=modifiers,
        actor="llm-run-7",
        kind="tool",
        method="tool",
    )
    packet, report = to_phenopacket(
        unit([item], subject_id="P1"), hp, created_at=CREATED
    )
    feature = packet["phenotypicFeatures"][0]
    assert packet["subject"] == {"id": "P1"}
    assert feature["onset"] == {
        "ontologyClass": {"id": "HP:0003593", "label": "Infantile onset"}
    }
    assert feature["modifiers"] == [
        {"id": "HP:0012832", "label": "Bilateral"},
        {"id": "HP:0040282", "label": "Frequent"},
    ]
    assert feature["evidence"][0]["evidenceCode"]["id"] == "ECO:0007636"
    assert report.frequency_modifiers == 1


def test_resources_name_the_release_of_the_layer(hp: ObographOntology) -> None:
    older = HPO_LAYER.model_copy(
        update={"ontology": OntologyResource(id="hp", version="2025-01-01")}
    )
    data = unit([annotation("a1", SEIZURE, [(63, 76)])], layers=[older])
    with pytest.raises(ValueError, match="ontology release"):
        to_phenopacket(data, hp, created_at=CREATED)


def test_the_creation_time_needs_a_time_zone(
    sample_unit: AnnotatedDocument, hp: ObographOntology
) -> None:
    with pytest.raises(ValueError, match="time zone"):
        to_phenopacket(sample_unit, hp, created_at=datetime(2026, 10, 14, 12, 0))


def test_documents_of_one_subject_form_one_packet(hp: ObographOntology) -> None:
    units = [
        unit(
            [annotation("a1", SEIZURE, [(63, 76)])], document_id="d1", subject_id="P1"
        ),
        unit([annotation("a1", SEIZURE, [(6, 19)])], document_id="d2"),
        unit(
            [annotation("a2", SEIZURE, [(63, 76)])],
            document_id="d3",
            subject_id="P1",
            set_id="set-3",
        ),
    ]
    grouped = to_phenopackets(
        units, hp, created_at=CREATED, bundle_id="b-1", group_by_subject=True
    )
    assert [packet["id"] for packet, _ in grouped] == ["P1", "d2"]
    first, report = grouped[0]
    assert first["subject"] == {"id": "P1"}
    assert [
        f["evidence"][0]["reference"]["id"] for f in first["phenotypicFeatures"]
    ] == [
        "urn:ontospan:b-1:set-1:a1",
        "urn:ontospan:b-1:set-3:a2",
    ]
    assert report.exported == 2

    single = to_phenopackets(units, hp, created_at=CREATED, group_by_subject=False)
    assert [packet["id"] for packet, _ in single] == ["d1", "d2", "d3"]


def test_many_packet_export_defaults_to_separate_documents(
    hp: ObographOntology,
) -> None:
    units = [
        unit([], document_id="d1", subject_id="P1"),
        unit([], document_id="d2", subject_id="P1", set_id="s2"),
    ]
    assert [packet["id"] for packet, _ in to_phenopackets(units, hp)] == ["d1", "d2"]


def test_alternate_annotation_sets_are_never_mixed(hp: ObographOntology) -> None:
    units = [
        unit([], set_id="set:A", subject_id="P"),
        unit([], set_id="set:B", subject_id="P"),
    ]
    with pytest.raises(ValueError, match="one annotation set per document"):
        to_phenopackets(units, hp, group_by_subject=True)
    assert [p["id"] for p, _ in to_phenopackets(units, hp)] == [
        "urn:ontospan:document:doc-1:set%3AA",
        "urn:ontospan:document:doc-1:set%3AB",
    ]


def test_grouped_hpo_resources_cannot_use_conflicting_releases(
    hp: ObographOntology,
) -> None:
    older = HPO_LAYER.model_copy(
        update={"ontology": OntologyResource(id="hp", version="2025-01-01")}
    )
    units = [
        unit([], document_id="d1", subject_id="P"),
        unit([], document_id="d2", subject_id="P", set_id="s2", layers=[older]),
    ]
    with pytest.raises(ValueError, match="conflicting HPO releases"):
        to_phenopackets(units, hp, group_by_subject=True)


def test_parsing_checks_the_structure_only(
    sample_unit: AnnotatedDocument, hp: ObographOntology
) -> None:
    pytest.importorskip("phenopackets")
    from google.protobuf.json_format import ParseError

    packet, _ = to_phenopacket(sample_unit, hp, created_at=CREATED)
    parsed = parse_phenopacket(packet)
    assert parsed.phenotypic_features[0].type.id == SEIZURE
    assert parsed.meta_data.resources[0].version == "2026-06-23"
    parse_phenopacket({})  # structure only: an empty packet parses
    with pytest.raises(ParseError, match="bogus"):
        parse_phenopacket({"bogus": 1})
