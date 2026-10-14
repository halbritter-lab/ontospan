"""The conformance fixtures in ``conformance/``: data plus expected issue codes.

They are part of the binding contract (T1 F12, changes after the plan
review): any implementation of the format must report the same error and
warning codes for these files, validated without an ontology.

Regenerate them with ``uv run python tests/conformance_cases.py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from builders import SEIZURE, SEVERE, TEXT, annotation, axes, sample, unit

from ontospan.models import AxisValue, Layer, OntologyResource

ROOT = Path(__file__).resolve().parent.parent / "conformance"
CHECKED = ["hierarchy_not_checked"]

Data = dict[str, Any]


def _dump(item: Any) -> Data:
    data: Data = item.model_dump(mode="json")
    return data


def _sample() -> Data:
    return _dump(sample())


def _discontinuous() -> Data:
    return _dump(unit([annotation("a1", SEIZURE, [[(55, 62), (63, 76)]])]))


def _document_level() -> Data:
    return _dump(unit([annotation("a1", SEIZURE, [], document_level=True)]))


def _generic_layer() -> Data:
    layer = Layer(
        layer_id="diagnosis",
        profile="generic",
        ontology=OntologyResource(id="mondo", version="2026-06-01"),
    )
    free = {"certainty": AxisValue(value="confirmed", basis="chosen")}
    item = annotation(
        "d1", "MONDO:0005027", [(63, 76)], axes_=free, layer_id="diagnosis"
    )
    return _dump(unit([item], layers=[layer]))


def _newer_minor() -> Data:
    data = _sample()
    data["schema_version"] = "1.1.0"
    data["annotation_set"]["relations"] = [{"from": "a1", "to": "a2"}]
    data["annotation_set"]["layers"].append(
        {
            "layer_id": "maxo",
            "profile": "medical-action",
            "ontology": {"id": "maxo", "version": "2026-01-01"},
        }
    )
    return data


def _changed(change: Callable[[Data], None]) -> Callable[[], Data]:
    def build() -> Data:
        data = _sample()
        change(data)
        return data

    return build


def _first_segment(data: Data) -> Data:
    segment: Data = data["annotation_set"]["annotations"][0]["mentions"][0]["segments"][
        0
    ]
    return segment


def _hpo_axes() -> Data:
    bad = {**axes(), "temporality": AxisValue(value="future", basis="chosen")}
    del bad["experiencer"]
    return _dump(unit([annotation("a1", SEIZURE, [(63, 76)], axes_=bad)]))


def _source_ref() -> Data:
    item = annotation("a1", SEIZURE, [(63, 76)], method="adopted", source_refs=["a1"])
    return _dump(unit([item]))


# name -> (builder, errors, warnings, valid under the hpo profile schema or None)
CASES: dict[str, tuple[Callable[[], Data], list[str], list[str], bool | None]] = {
    "valid/sample": (_sample, [], CHECKED, True),
    "valid/discontinuous-mention": (_discontinuous, [], CHECKED, True),
    "valid/document-level": (_document_level, [], CHECKED, True),
    "valid/generic-layer": (_generic_layer, [], [], None),
    "valid/newer-minor": (
        _newer_minor,
        [],
        ["newer_minor", "hierarchy_not_checked", "unknown_profile"],
        True,
    ),
    "invalid/unsupported-major": (
        _changed(lambda d: d.update(schema_version="2.0.0")),
        ["unsupported_major"],
        [],
        None,
    ),
    "invalid/unknown-field": (
        _changed(lambda d: d["document"].update(title="x")),
        ["schema"],
        [],
        None,
    ),
    "invalid/timestamp-without-zone": (
        _changed(
            lambda d: d["annotation_set"].update(created_at="2026-10-14T12:00:00")
        ),
        ["schema"],
        [],
        None,
    ),
    "invalid/text-not-canonical": (
        _changed(lambda d: d["document"].update(text=TEXT + "\r\n")),
        ["text_not_canonical", "text_hash"],
        CHECKED,
        True,
    ),
    "invalid/segment-text-mismatch": (
        _changed(lambda d: _first_segment(d).update(text="Krampfanfalle")),
        ["segment_text_mismatch"],
        CHECKED,
        True,
    ),
    "invalid/segment-out-of-range": (
        _changed(lambda d: _first_segment(d).update(start=70, end=83)),
        ["segment_out_of_range"],
        CHECKED,
        True,
    ),
    "invalid/segments-unordered": (
        lambda: _dump(unit([annotation("a1", SEIZURE, [[(63, 76), (55, 62)]])])),
        ["segments_unordered"],
        CHECKED,
        True,
    ),
    "invalid/unknown-layer": (
        lambda: _dump(unit([annotation("a1", SEIZURE, [(63, 76)], layer_id="x")])),
        ["unknown_layer"],
        CHECKED,
        None,
    ),
    "invalid/hpo-axes": (_hpo_axes, ["axes", "axis_value"], CHECKED, False),
    "invalid/hpo-missing-evidence": (
        lambda: _dump(unit([annotation("a1", SEIZURE, [])])),
        ["missing_evidence"],
        CHECKED,
        False,
    ),
    "invalid/hpo-not-an-hpo-id": (
        lambda: _dump(unit([annotation("a1", "MONDO:0005027", [(63, 76)])])),
        ["not_an_hpo_id"],
        CHECKED,
        False,
    ),
    "invalid/hpo-modifier-id": (
        lambda: _dump(
            unit(
                [annotation("a1", SEIZURE, [(63, 76)], modifiers=[(f"X{SEVERE}", [])])]
            )
        ),
        ["not_an_hpo_id"],
        CHECKED,
        False,
    ),
    "invalid/source-ref-syntax": (_source_ref, ["source_ref_syntax"], CHECKED, True),
}


def render(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def expected() -> Data:
    """The content of ``conformance/cases.json``."""
    return {
        "cases": [
            {
                "file": f"{name}.json",
                "errors": errors,
                "warnings": warnings,
                "hpo_profile_schema": profile,
            }
            for name, (_, errors, warnings, profile) in CASES.items()
        ]
    }


def files() -> dict[str, str]:
    """Every fixture file by its path below ``conformance/``."""
    out = {f"{name}.json": render(build()) for name, (build, *_) in CASES.items()}
    out["cases.json"] = render(expected())
    return out


def main() -> None:
    for name, content in files().items():
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
