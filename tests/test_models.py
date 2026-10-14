from datetime import datetime

import pytest
from builders import CREATED
from pydantic import ValidationError

from ontospan import SCHEMA_VERSION
from ontospan.models import AnnotatedDocument, AnnotationSet, Segment


def test_a_segment_needs_end_after_start_and_matching_text_length() -> None:
    with pytest.raises(ValidationError):
        Segment(start=5, end=5, text="x")
    with pytest.raises(ValidationError):
        Segment(start=0, end=3, text="ab")


def test_an_annotated_document_round_trips_through_json(
    sample_unit: AnnotatedDocument,
) -> None:
    data = sample_unit.model_dump(mode="json")
    assert AnnotatedDocument.model_validate(data) == sample_unit
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["annotation_set"]["created_at"] == "2026-10-14T12:00:00Z"
    assert data["annotation_set"]["annotations"][0]["axes"]["assertion"] == {
        "value": "absent",
        "basis": "chosen",
    }


def test_unknown_fields_are_kept_for_the_next_write(
    sample_unit: AnnotatedDocument,
) -> None:
    data = sample_unit.model_dump(mode="json")
    data["annotation_set"]["future_field"] = {"kept": True}
    again = AnnotatedDocument.model_validate(data).model_dump(mode="json")
    assert again["annotation_set"]["future_field"] == {"kept": True}


def test_timestamps_need_a_timezone(sample_unit: AnnotatedDocument) -> None:
    fields = sample_unit.annotation_set.model_dump()
    with pytest.raises(ValidationError):
        AnnotationSet.model_validate({**fields, "created_at": datetime(2026, 10, 14)})
    assert (
        AnnotationSet.model_validate({**fields, "created_at": CREATED}).created_at
        == CREATED
    )
