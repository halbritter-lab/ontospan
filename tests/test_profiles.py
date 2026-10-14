import pytest
from builders import FIXTURES, HPO_LAYER, SEIZURE, SEVERE, annotation, axes

from ontospan.models import Annotation, AxisValue, Layer, OntologyResource
from ontospan.ontology import ObographOntology
from ontospan.profiles import PROFILES, Context, generic
from ontospan.profiles.hpo import check_annotation, default_axes


@pytest.fixture(scope="module")
def hp() -> ObographOntology:
    return ObographOntology.load(FIXTURES / "hp-mini.json")


def codes(
    item: Annotation,
    hp: ObographOntology | None,
    layer: Layer = HPO_LAYER,
    newer_minor: bool = False,
) -> list[tuple[str, str]]:
    ctx = Context(path="a", ontology=hp, newer_minor=newer_minor)
    return [(i.level, i.code) for i in check_annotation(layer, item, ctx)]


def test_both_profiles_are_registered() -> None:
    assert sorted(PROFILES) == ["generic", "hpo-phenotype"]


def test_a_correct_annotation_has_no_issues(hp: ObographOntology) -> None:
    item = annotation("a1", SEIZURE, [(63, 76)], modifiers=[(SEVERE, [(55, 62)])])
    assert codes(item, hp) == []


def test_defaults_are_present_patient_current_and_marked_defaulted() -> None:
    assert default_axes() == {
        "assertion": AxisValue(value="present", basis="defaulted"),
        "experiencer": AxisValue(value="patient", basis="defaulted"),
        "temporality": AxisValue(value="current", basis="defaulted"),
    }


def test_axes_must_be_complete_and_use_profile_values() -> None:
    bad = {**axes(), "temporality": AxisValue(value="future", basis="chosen")}
    missing = {k: v for k, v in axes().items() if k != "experiencer"}
    assert codes(annotation("a1", SEIZURE, [(6, 19)], axes_=bad), None) == [
        ("error", "axis_value")
    ]
    assert codes(annotation("a2", SEIZURE, [(6, 19)], axes_=missing), None) == [
        ("error", "axes")
    ]


def test_an_unknown_axis_is_an_error_unless_the_unit_is_newer() -> None:
    more = {**axes(), "certainty": AxisValue(value="high", basis="chosen")}
    item = annotation("a1", SEIZURE, [(6, 19)], axes_=more)
    assert codes(item, None) == [("error", "axes")]
    assert codes(item, None, newer_minor=True) == [("warning", "unknown_axis")]


def test_unknown_is_allowed_for_experiencer_and_temporality() -> None:
    values = axes(experiencer="unknown", temporality="unknown")
    assert codes(annotation("a1", SEIZURE, [(63, 76)], axes_=values), None) == []


def test_without_mentions_an_annotation_must_be_document_level() -> None:
    assert codes(annotation("a1", SEIZURE, []), None) == [("error", "missing_evidence")]
    assert codes(annotation("a2", SEIZURE, [], document_level=True), None) == []
    assert codes(annotation("a3", SEIZURE, [(63, 76)], document_level=True), None) == [
        ("error", "document_level_with_mentions")
    ]


def test_terms_must_be_active_hpo_terms_and_not_modifiers(hp: ObographOntology) -> None:
    assert codes(annotation("a1", "HP:0000057", [(6, 19)]), hp) == [
        ("error", "unknown_term")
    ]
    assert codes(annotation("a2", SEVERE, [(55, 62)]), hp) == [
        ("error", "modifier_as_annotation")
    ]
    assert codes(annotation("a3", "MONDO:0005027", [(63, 76)]), hp) == [
        ("error", "not_an_hpo_id"),
        ("error", "unknown_term"),
    ]


def test_history_terms_are_allowed_unless_the_project_restricts_roots(
    hp: ObographOntology,
) -> None:
    history = annotation("a1", "HP:0032444", [(63, 76)])
    assert codes(history, hp) == []
    restricted = HPO_LAYER.model_copy(update={"allowed_roots": ("HP:0000118",)})
    assert codes(history, hp, layer=restricted) == [("error", "outside_allowed_roots")]


def test_modifiers_must_be_clinical_modifiers_and_frequency_only_warns(
    hp: ObographOntology,
) -> None:
    modifiers = [("HP:0012832", []), ("HP:0040282", []), ("HP:0011146", [])]
    item = annotation("a1", SEIZURE, [(63, 76)], modifiers=modifiers)
    assert codes(item, hp) == [
        ("warning", "cohort_frequency"),
        ("error", "not_a_modifier"),
    ]


def test_the_generic_profile_checks_terms_and_roots_only(hp: ObographOntology) -> None:
    layer = Layer(
        layer_id="any",
        profile="generic",
        ontology=OntologyResource(id="hp", version="2026-06-23"),
        allowed_roots=("HP:0000118",),
    )
    free_axes = {"certainty": AxisValue(value="high", basis="chosen")}
    ctx = Context(path="a", ontology=hp)
    ok = annotation("a1", SEIZURE, [(63, 76)], axes_=free_axes, layer_id="any")
    outside = annotation("a2", "HP:0032444", [(63, 76)], layer_id="any")
    unknown = annotation("a3", "HP:9999999", [(63, 76)], layer_id="any")
    assert generic.check_annotation(layer, ok, ctx) == []
    assert [i.code for i in generic.check_annotation(layer, outside, ctx)] == [
        "outside_allowed_roots"
    ]
    assert [i.code for i in generic.check_annotation(layer, unknown, ctx)] == [
        "unknown_term"
    ]
    assert generic.check_annotation(layer, unknown, Context(path="a")) == []
