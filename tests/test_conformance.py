import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from conformance_cases import ROOT, expected, files

from ontospan.bundle import read_bundle
from ontospan.report import FormatError
from ontospan.schema import HPO_ANNOTATION, schema_name
from ontospan.schema_export import build_schemas
from ontospan.validate import validate

CASES = expected()["cases"]


def test_the_committed_fixtures_are_up_to_date() -> None:
    for name, content in files().items():
        path = ROOT / name
        assert path.is_file(), (
            f"run `uv run python tests/conformance_cases.py` ({name})"
        )
        assert path.read_text(encoding="utf-8") == content, f"{name} is stale"


@pytest.mark.parametrize("case", CASES, ids=[case["file"] for case in CASES])
def test_each_fixture_gives_the_expected_codes(
    case: dict[str, Any], tmp_path: Path
) -> None:
    data = json.loads((ROOT / case["file"]).read_text(encoding="utf-8"))
    if case["artifact_type"] == "bundle":
        (tmp_path / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(FormatError) as raised:
            read_bundle(tmp_path)
        report = raised.value.report
    else:
        report = validate(data)
    assert [issue.code for issue in report.errors] == case["errors"]
    assert [issue.code for issue in report.warnings] == case["warnings"]


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["hpo_profile_schema"] is not None],
    ids=lambda case: case["file"],
)
def test_the_profile_schema_agrees_with_the_profile_rules(case: dict[str, Any]) -> None:
    schema = build_schemas()[schema_name(HPO_ANNOTATION)]
    validator = jsonschema.Draft202012Validator(schema)
    data = json.loads((ROOT / case["file"]).read_text(encoding="utf-8"))
    hpo_layers = {
        layer["layer_id"]
        for layer in data["annotation_set"]["layers"]
        if layer["profile"] == "hpo-phenotype"
    }
    annotations = [
        item
        for item in data["annotation_set"]["annotations"]
        if item["layer_id"] in hpo_layers
    ]
    valid = all(validator.is_valid(item) for item in annotations)
    assert valid is case["hpo_profile_schema"]
