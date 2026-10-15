"""Format 1.1: document variants and translations (T5 V4, decision D-aa)."""

import json
from importlib import resources
from typing import Any

import jsonschema
import pytest
from builders import (
    MACHINE_TRANSLATION,
    SOURCE_SHA256,
    corrected_sample,
    sample,
    translated_sample,
    with_variant,
)

from ontospan.models import AnnotatedDocument, Translation, Variant
from ontospan.text import text_sha256
from ontospan.validate import dump_json, load_annotated_document, validate

EARLIER = text_sha256("Ein älterer Text.")


def test_a_translation_unit_round_trips() -> None:
    unit = translated_sample()
    loaded = load_annotated_document(dump_json(unit))
    assert loaded == unit
    assert loaded.document.case_id == "case-1"
    assert loaded.document.variant == Variant(
        version=1, origin="machine_translation", derived_from=SOURCE_SHA256
    )
    assert loaded.document.translation == MACHINE_TRANSLATION
    assert validate(unit).ok


def test_a_correction_unit_is_valid() -> None:
    assert validate(corrected_sample()).ok


def _unit(
    origin: Any,
    *,
    version: int = 1,
    derived_from: str | None = EARLIER,
    translation: Translation | None = None,
) -> AnnotatedDocument:
    variant = Variant(version=version, origin=origin, derived_from=derived_from)
    return with_variant(sample(), variant, translation)


SELF = sample().document.text_sha256

# unit, code, level: one case per row of the rule table.
RULES: dict[str, tuple[AnnotatedDocument, str, str]] = {
    "translation-without-source": (
        _unit(
            "machine_translation", derived_from=None, translation=MACHINE_TRANSLATION
        ),
        "variant_derived_from_missing",
        "error",
    ),
    "native-with-source": (_unit("native"), "variant_native_invalid", "error"),
    "native-version-2": (
        _unit("native", version=2, derived_from=None),
        "variant_native_invalid",
        "error",
    ),
    "correction-version-1": (
        _unit("correction", version=1),
        "variant_version_invalid",
        "error",
    ),
    "self-reference": (
        _unit("correction", version=2, derived_from=SELF),
        "variant_self_reference",
        "error",
    ),
    "translation-on-native": (
        _unit("native", derived_from=None, translation=MACHINE_TRANSLATION),
        "translation_unexpected",
        "error",
    ),
    "translation-missing": (
        _unit("human_translation"),
        "translation_missing",
        "warning",
    ),
}


@pytest.mark.parametrize("name", list(RULES))
def test_variant_rules(name: str) -> None:
    unit, code, level = RULES[name]
    report = validate(unit)
    issues = report.errors if level == "error" else report.warnings
    found = [issue for issue in issues if issue.code != "hierarchy_not_checked"]
    assert [issue.code for issue in found] == [code]
    assert found[0].path.startswith("document.")
    assert report.ok is (level == "warning")


def test_units_without_variant_stay_valid_1_0() -> None:
    data = sample().model_dump(mode="json")
    data["schema_version"] = "1.0.0"
    files = resources.files("ontospan.schema")
    frozen = json.loads(
        files.joinpath("annotated-document-1.0.json").read_text(encoding="utf-8")
    )
    assert jsonschema.Draft202012Validator(frozen).is_valid(data)
    report = validate(data)
    assert report.ok
    assert [issue.code for issue in report.warnings] == ["hierarchy_not_checked"]


def test_a_1_0_unit_cannot_declare_variant_fields() -> None:
    data = translated_sample().model_dump(mode="json")
    data["schema_version"] = "1.0.0"
    assert "schema" in [issue.code for issue in validate(data).errors]
