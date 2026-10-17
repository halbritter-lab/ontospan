"""Format 1.2 keeps reviewer uncertainty separate from clinical content."""

import json
from pathlib import Path

import pytest
from builders import CREATED, FIXTURES, sample

import ontospan
from ontospan.models import AnnotatedDocument
from ontospan.ontology import ObographOntology


def flagged(*, note: str | None = "Needs review: ä 🧬") -> AnnotatedDocument:
    data = sample().model_dump(mode="json")
    data["schema_version"] = "1.2.0"
    resolution = {
        "outcome": "uncertain",
        "reviewer": {"actor_id": "reviewer-1", "kind": "human"},
    }
    if note is not None:
        resolution["note"] = note
    item = data["annotation_set"]["annotations"][1]
    item["review_resolution"] = resolution
    item["axes"]["assertion"]["basis"] = "defaulted"
    item["provenance"]["source_refs"] = ["urn:ontospan:proposal-set:a2"]
    item["provenance"]["notes"] = ["Clinical justification", "Source note"]
    return AnnotatedDocument.model_validate(data)


@pytest.mark.parametrize("note", [None, "Needs review: ä 🧬"])
def test_resolution_json_round_trip_preserves_source_and_axes(note: str | None) -> None:
    original = flagged(note=note)
    loaded = ontospan.load_annotated_document(ontospan.dump_json(original))
    assert loaded == original
    item = loaded.annotation_set.annotations[1]
    assert isinstance(item.review_resolution, ontospan.ReviewResolution)
    assert item.review_resolution.reviewer.actor_id == "reviewer-1"
    assert item.axes["assertion"].value == "present"
    assert item.axes["assertion"].basis == "defaulted"
    assert item.provenance.actor.actor_id == "ann-03"
    assert item.provenance.method == "manual"
    assert item.provenance.notes == ("Clinical justification", "Source note")
    assert item.provenance.source_refs == ("urn:ontospan:proposal-set:a2",)
    block = json.loads(ontospan.dump_json(loaded))["annotation_set"]["annotations"][1][
        "review_resolution"
    ]
    assert ("note" in block) is (note is not None)


@pytest.mark.parametrize("name", ["bundle", "bundle.zip"])
def test_resolution_survives_bundle_round_trip(tmp_path: Path, name: str) -> None:
    item = flagged()
    manifest = ontospan.write_bundle(
        tmp_path / name, [item], bundle_id="b", created_at=CREATED
    )
    assert manifest.schema_version == "1.2.0"
    assert ontospan.read_bundle(tmp_path / name) == (manifest, [item])


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
@pytest.mark.parametrize("name", ["bundle", "bundle.zip"])
def test_historical_bundle_keeps_its_declared_version(
    tmp_path: Path, version: str, name: str
) -> None:
    item = sample().model_copy(update={"schema_version": version})
    manifest = ontospan.write_bundle(
        tmp_path / name, [item], bundle_id="b", created_at=CREATED
    )
    assert manifest.schema_version == version
    assert ontospan.read_bundle(tmp_path / name) == (manifest, [item])


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0", "1.2.0"])
def test_unflagged_annotations_omit_resolution(version: str) -> None:
    item = sample().model_copy(update={"schema_version": version})
    loaded = ontospan.load_annotated_document(ontospan.dump_json(item))
    assert loaded.schema_version == version
    assert all(
        "review_resolution" not in a
        for a in json.loads(ontospan.dump_json(loaded))["annotation_set"]["annotations"]
    )


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_older_declared_versions_reject_resolution(version: str) -> None:
    item = flagged().model_copy(update={"schema_version": version})
    assert "schema" in [i.code for i in ontospan.validate(item).errors]


@pytest.mark.parametrize(
    "block",
    [
        {"outcome": "confirmed", "reviewer": {"actor_id": "r", "kind": "human"}},
        {"outcome": "uncertain"},
        {"outcome": "uncertain", "reviewer": {"actor_id": "", "kind": "human"}},
        {
            "outcome": "uncertain",
            "reviewer": {"actor_id": "r", "kind": "human"},
            "extra": True,
        },
    ],
)
def test_resolution_schema_rejects_invalid_blocks(block: dict) -> None:
    data = flagged().model_dump(mode="json")
    data["annotation_set"]["annotations"][1]["review_resolution"] = block
    assert "schema" in [i.code for i in ontospan.validate(data).errors]


@pytest.mark.parametrize("include_uncertain", [False, True])
@pytest.mark.parametrize("group_by_subject", [False, True])
def test_phenopacket_refuses_reviewer_uncertainty(
    include_uncertain: bool, group_by_subject: bool
) -> None:
    hp = ObographOntology.load(FIXTURES / "hp-mini.json")
    with pytest.raises(ValueError, match=r"review_resolution.*a2"):
        ontospan.to_phenopacket(flagged(), hp, include_uncertain=include_uncertain)
    with pytest.raises(ValueError, match=r"review_resolution.*a2"):
        ontospan.to_phenopackets(
            [flagged()],
            hp,
            include_uncertain=include_uncertain,
            group_by_subject=group_by_subject,
        )


def test_newer_minor_keeps_unknown_resolution_fields() -> None:
    data = flagged().model_dump(mode="json")
    data["schema_version"] = "1.3.0"
    data["annotation_set"]["annotations"][1]["review_resolution"]["future"] = {
        "value": 1
    }
    loaded = ontospan.load_annotated_document(json.dumps(data))
    assert json.loads(ontospan.dump_json(loaded)) == data


@pytest.mark.parametrize("filtered_by", ["experiencer", "layer"])
def test_phenopacket_refusal_precedes_other_annotation_filters(
    filtered_by: str,
) -> None:
    data = flagged().model_dump(mode="json")
    if filtered_by == "experiencer":
        data["annotation_set"]["annotations"][1]["axes"]["experiencer"]["value"] = (
            "other"
        )
    else:
        data["annotation_set"]["layers"][0]["profile"] = "generic"
    item = AnnotatedDocument.model_validate(data)
    hp = ObographOntology.load(FIXTURES / "hp-mini.json")
    with pytest.raises(ValueError, match=r"review_resolution.*a2"):
        ontospan.to_phenopacket(item, hp)
