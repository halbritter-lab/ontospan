import json
from importlib import resources
from typing import Any

import jsonschema
import pytest
from builders import CREATED, HPO_LAYER, sample

from ontospan import SCHEMA_VERSION
from ontospan.models import FileEntry, Manifest
from ontospan.profiles import hpo
from ontospan.schema import (
    DOCUMENT,
    HPO_ANNOTATION,
    KINDS,
    MANIFEST,
    schema_name,
)
from ontospan.schema_export import build_schemas

STALE = (
    "{} differs from the models. Run `uv run python -m ontospan.schema_export`. "
    "If no model changed, the pydantic version did: keep the pinned minor."
)


@pytest.mark.parametrize("kind", [DOCUMENT, MANIFEST])
def test_serialized_artifacts_require_an_explicit_schema_version(kind: str) -> None:
    model = (
        sample()
        if kind == DOCUMENT
        else Manifest(
            bundle_id="b",
            created_at=CREATED,
            layers=(HPO_LAYER,),
            files=(FileEntry(path="documents/0.json", sha256="0" * 64),),
        )
    )
    data = model.model_dump(mode="json")
    assert data["schema_version"] == SCHEMA_VERSION
    validator = jsonschema.Draft202012Validator(build_schemas()[schema_name(kind)])
    assert validator.is_valid(data)
    del data["schema_version"]
    assert not validator.is_valid(data)
    data["schema_version"] = SCHEMA_VERSION
    del data["artifact_type"]
    assert not validator.is_valid(data)


def committed(name: str) -> Any:
    files = resources.files("ontospan.schema")
    return json.loads(files.joinpath(name).read_text(encoding="utf-8"))


def test_patch_versions_share_the_file_of_their_minor_version() -> None:
    assert schema_name(DOCUMENT, "1.3.7") == "annotated-document-1.3.json"
    major_minor = ".".join(SCHEMA_VERSION.split(".")[:2])
    assert schema_name(MANIFEST) == f"bundle-manifest-{major_minor}.json"


def test_the_committed_current_schemas_match_the_models() -> None:
    built = build_schemas()
    assert set(built) == {schema_name(kind) for kind in KINDS}
    for name, schema in built.items():
        assert committed(name) == schema, STALE.format(name)


def test_every_released_minor_version_ships_its_frozen_schemas() -> None:
    major, minor, _ = (int(part) for part in SCHEMA_VERSION.split("."))
    for released in range(minor + 1):
        for kind in KINDS:
            assert committed(schema_name(kind, f"{major}.{released}.0"))


@pytest.mark.parametrize("kind", [DOCUMENT, MANIFEST])
def test_every_object_with_properties_is_closed(kind: str) -> None:
    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "properties" in node:
                assert node.get("additionalProperties") is False
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(build_schemas()[schema_name(kind)])


def test_the_profile_schema_lists_the_axis_values_of_the_profile() -> None:
    schema = build_schemas()[schema_name(HPO_ANNOTATION)]
    axes = schema["properties"]["axes"]
    assert axes["required"] == list(hpo.AXES)
    for axis, values in hpo.AXES.items():
        assert axes["properties"][axis]["properties"]["value"]["enum"] == list(values)
    assert schema["$id"] == f"urn:ontospan:schema:{schema_name(HPO_ANNOTATION)}"
