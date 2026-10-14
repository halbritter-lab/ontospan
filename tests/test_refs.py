import pytest

from ontospan.refs import AnnotationRef, annotation_ref, parse_annotation_ref


def test_a_reference_names_set_and_annotation_and_encodes_colons() -> None:
    ref = annotation_ref("e3c:EN1:ann-01", "a1")
    assert ref == "urn:ontospan:e3c%3AEN1%3Aann-01:a1"
    assert parse_annotation_ref(ref) == AnnotationRef("e3c:EN1:ann-01", "a1")


def test_an_export_reference_starts_with_the_bundle() -> None:
    ref = annotation_ref("set-a", "a 1", bundle_id="gold:v1")
    assert ref == "urn:ontospan:gold%3Av1:set-a:a%201"
    assert parse_annotation_ref(ref) == AnnotationRef("set-a", "a 1", "gold:v1")


@pytest.mark.parametrize(
    "ref", ["a1", "urn:ontospan:a1", "urn:ontospan:s::a1", "urn:other:s:a1"]
)
def test_malformed_references_are_refused(ref: str) -> None:
    with pytest.raises(ValueError):
        parse_annotation_ref(ref)
