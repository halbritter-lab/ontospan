import json
from typing import Any

import pytest
from builders import FIXTURES, HPO_LAYER, SEIZURE, TEXT, annotation, axes, unit

from ontospan.models import AnnotatedDocument, Layer, OntologyResource
from ontospan.ontology import ObographOntology
from ontospan.report import FormatError, ValidationReport
from ontospan.validate import dump_json, load_annotated_document, validate


@pytest.mark.parametrize("location", ["unknown", "segment", "key"])
def test_all_strings_are_checked_for_invalid_unicode(
    sample_unit: AnnotatedDocument, location: str
) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "1.2.0"
    if location == "unknown":
        data["future"] = ["\ud800"]
    elif location == "key":
        data["\ud800"] = "value"
    else:
        data["annotation_set"]["annotations"][0]["mentions"][0]["segments"][0][
            "text"
        ] = "\ud800"
    assert codes(data) == ["invalid_unicode"]
    with pytest.raises(FormatError) as raised:
        load_annotated_document(json.dumps(data))
    assert raised.value.report.errors[0].code == "invalid_unicode"
    if location == "unknown":
        with pytest.raises(FormatError) as raised:
            dump_json(AnnotatedDocument.model_validate(data))
        assert raised.value.report.errors[0].code == "invalid_unicode"


@pytest.mark.parametrize("version", ["².0.0", "\uff11.\uff10.\uff10", "01.0.0"])
def test_versions_use_ascii_semver(
    sample_unit: AnnotatedDocument, version: str
) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = version
    assert codes(data) == ["schema_version"]


def test_document_loaders_reject_duplicate_json_keys(
    sample_unit: AnnotatedDocument,
) -> None:
    raw = (
        dump_json(sample_unit)
        .decode()
        .replace(
            '"schema_version": "1.1.0"',
            '"schema_version": "2.0.0", "schema_version": "1.1.0"',
        )
    )
    with pytest.raises(FormatError) as raised:
        load_annotated_document(raw)
    assert raised.value.report.errors[0].code == "duplicate_json_key"


def test_loader_warnings_can_be_collected(sample_unit: AnnotatedDocument) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "1.2.0"
    collected = ValidationReport()
    load_annotated_document(data, report=collected)
    assert [i.code for i in collected.warnings] == [
        "newer_minor",
        "hierarchy_not_checked",
    ]


def test_newer_minor_still_requires_explicit_artifact_type(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "1.2.0"
    del data["artifact_type"]
    assert codes(data) == ["schema"]


def test_invalid_unicode_is_reported_and_loading_raises_format_error(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    data["document"]["text"] = "\ud800"
    assert codes(data) == ["invalid_unicode"]
    with pytest.raises(FormatError) as raised:
        load_annotated_document(json.dumps(data))
    assert raised.value.report.errors[0].code == "invalid_unicode"


@pytest.mark.parametrize("bad_start", ["6", 6.0, True])
def test_newer_minor_keeps_known_json_types_strict(
    sample_unit: AnnotatedDocument, bad_start: object
) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "1.2.0"
    data["annotation_set"]["annotations"][0]["mentions"][0]["segments"][0]["start"] = (
        bad_start
    )
    assert "model" in codes(data)


def test_newer_minor_preserves_json_datetime_and_array_semantics(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "1.2.0"
    data["document"]["optional_new_field"] = [1, "kept"]
    assert codes(data) == []
    loaded = load_annotated_document(json.dumps(data))
    assert loaded.annotation_set.created_at.isoformat() == "2026-10-14T12:00:00+00:00"
    assert loaded.document.model_dump()["optional_new_field"] == [1, "kept"]


def codes(data: object, **options: Any) -> list[str]:
    return [issue.code for issue in validate(data, **options).errors]


def warnings(data: object, **options: Any) -> list[str]:
    return [issue.code for issue in validate(data, **options).warnings]


def dumped(item: AnnotatedDocument) -> dict[str, Any]:
    return item.model_dump(mode="json")


@pytest.fixture(scope="module")
def hp() -> ObographOntology:
    return ObographOntology.load(FIXTURES / "hp-mini.json")


def test_a_correct_unit_only_warns_that_the_hierarchy_was_not_checked(
    sample_unit: AnnotatedDocument,
) -> None:
    report = validate(dumped(sample_unit))
    assert report.ok, report.errors
    assert warnings(sample_unit) == ["hierarchy_not_checked"]


def test_with_the_ontology_the_sample_has_no_issues_at_all(
    sample_unit: AnnotatedDocument, hp: ObographOntology
) -> None:
    assert validate(sample_unit, {"hp": hp}).issues == []


def test_something_that_is_no_object_is_reported_not_raised() -> None:
    assert codes([1]) == ["not_an_object"]
    with pytest.raises(FormatError) as raised:
        load_annotated_document(b"{not json")
    assert raised.value.report.errors[0].code == "invalid_json"


def test_another_major_version_or_a_broken_version_is_refused(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "2.0.0"
    assert codes(data) == ["unsupported_major"]
    data["schema_version"] = "1.0"
    assert codes(data) == ["schema_version"]


def test_a_newer_minor_version_is_read_with_warnings_and_kept_on_write(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "1.2.0"
    data["annotation_set"]["relations"] = [{"from": "a1", "to": "a2"}]
    data["annotation_set"]["layers"].append(
        {
            "layer_id": "maxo",
            "profile": "medical-action",
            "ontology": {"id": "maxo", "version": "1"},
        }
    )
    assert codes(data) == []
    assert warnings(data) == ["newer_minor", "hierarchy_not_checked", "unknown_profile"]
    again = load_annotated_document(data)
    assert b'"relations"' in dump_json(again)


def test_unknown_fields_are_errors_for_the_declared_version(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    data["annotation_set"]["relations"] = []
    assert codes(data) == ["schema"]


@pytest.mark.parametrize(
    ("created_at", "expected"),
    [
        ("2026-10-14", ["schema"]),
        ("2026-10-14T12:00:00", ["schema"]),
        ("2026-10-14T14:00:00+02:00", []),
        ("2026-10-14T12:00:00.5Z", []),
    ],
)
def test_timestamps_need_date_time_and_time_zone(
    sample_unit: AnnotatedDocument, created_at: str, expected: list[str]
) -> None:
    data = dumped(sample_unit)
    data["annotation_set"]["created_at"] = created_at
    assert codes(data) == expected


def test_text_must_be_canonical_and_match_its_hash(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    data["document"]["text"] = TEXT + "\r\n"
    assert codes(data) == ["text_not_canonical", "text_hash"]


def test_a_segment_must_quote_the_text_it_points_to(
    sample_unit: AnnotatedDocument,
) -> None:
    data = dumped(sample_unit)
    mention = data["annotation_set"]["annotations"][0]["mentions"][0]
    mention["segments"][0]["text"] = "Krampfanfalle"
    assert codes(data) == ["segment_text_mismatch"]


def test_a_segment_past_the_end_is_an_error() -> None:
    data = dumped(unit([annotation("a1", SEIZURE, [(63, 76)])]))
    seg = data["annotation_set"]["annotations"][0]["mentions"][0]["segments"][0]
    seg.update(start=70, end=83, text="Krampfanfälle")
    assert codes(data) == ["segment_out_of_range"]


def test_the_segments_of_a_mention_are_sorted_and_do_not_overlap() -> None:
    reversed_ = annotation("a1", SEIZURE, [[(63, 76), (55, 62)]])
    assert codes(unit([reversed_])) == ["segments_unordered"]
    assert codes(unit([annotation("a1", SEIZURE, [[(55, 62), (63, 76)]])])) == []


def test_a_segment_of_only_punctuation_and_space_is_a_warning() -> None:
    item = unit([annotation("a1", SEIZURE, [(39, 41)])])  # ". "
    assert codes(item) == []
    assert warnings(item) == ["hierarchy_not_checked", "empty_after_normalization"]


def test_annotations_must_name_a_declared_layer_and_have_unique_ids() -> None:
    first = annotation("a1", SEIZURE, [(6, 19)])
    other = annotation("a3", SEIZURE, [(63, 76)], layer_id="x")
    assert codes(unit([first, first, other])) == [
        "duplicate_annotation",
        "unknown_layer",
    ]


def test_a_layer_is_declared_once() -> None:
    assert codes(unit([], layers=[HPO_LAYER, HPO_LAYER])) == ["duplicate_layer"]


def test_an_unknown_profile_is_an_error_for_the_declared_version() -> None:
    layer = Layer(
        layer_id="hpo", profile="nope", ontology=OntologyResource(id="hp", version="1")
    )
    assert codes(unit([], layers=[layer])) == ["unknown_profile"]


def test_source_refs_use_the_reference_syntax() -> None:
    good = "urn:ontospan:set-a:a1"
    item = annotation("a1", SEIZURE, [(6, 19)], source_refs=[good, "a1"])
    assert codes(unit([item])) == ["source_ref_syntax"]


def test_a_different_ontology_release_is_reported(hp: ObographOntology) -> None:
    layer = HPO_LAYER.model_copy(
        update={"ontology": OntologyResource(id="hp", version="2025-01-01")}
    )
    data = unit([annotation("a1", SEIZURE, [(6, 19)])], layers=[layer])
    assert warnings(data, ontologies={"hp": hp}) == ["ontology_release_mismatch"]


def test_projects_can_require_chosen_axes() -> None:
    data = unit([annotation("a1", SEIZURE, [(6, 19)], axes_=axes(basis="defaulted"))])
    assert codes(data) == []
    assert codes(data, require_chosen_axes=True) == ["axis_not_chosen"] * 3


def test_tool_actors_can_be_required_to_name_tool_and_version() -> None:
    item = annotation("a1", SEIZURE, [(6, 19)], actor="llm", kind="tool", method="tool")
    data = unit([item])
    assert "tool_identity" not in warnings(data)
    assert warnings(data, require_tool_identity=True) == [
        "hierarchy_not_checked",
        "tool_identity",
    ]


def test_dump_and_load_round_trip(sample_unit: AnnotatedDocument) -> None:
    assert load_annotated_document(dump_json(sample_unit)) == sample_unit


def test_load_raises_with_the_report(sample_unit: AnnotatedDocument) -> None:
    data = dumped(sample_unit)
    data["schema_version"] = "2.0.0"
    with pytest.raises(FormatError) as raised:
        load_annotated_document(data)
    assert raised.value.report.errors[0].code == "unsupported_major"
