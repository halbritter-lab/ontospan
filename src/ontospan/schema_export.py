"""Generate the JSON Schemas of the current version; ``--check`` fails on drift.

Run ``python -m ontospan.schema_export`` after changing a model. Only the
files of the current minor version (``SCHEMA_VERSION``) are generated. Files
of earlier minor versions are frozen: they stay in ``ontospan/schema`` and are
never rewritten, so a unit is always checked against the version it declares.

The output depends on the pydantic version; the dev group pins its minor.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ontospan.models import AnnotatedDocument, Manifest
from ontospan.profiles import hpo
from ontospan.schema import DOCUMENT, HPO_ANNOTATION, MANIFEST, schema_name

SCHEMA_DIR = Path(__file__).parent / "schema"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _close(node: Any) -> Any:
    """Forbid unknown properties on every object that lists its properties."""
    if isinstance(node, dict):
        if "properties" in node:
            node["additionalProperties"] = False
        for value in node.values():
            _close(value)
    elif isinstance(node, list):
        for value in node:
            _close(value)
    return node


def _header(name: str) -> dict[str, str]:
    return {"$schema": DIALECT, "$id": f"urn:ontospan:schema:{name}"}


def _model_schema(
    model: type[AnnotatedDocument] | type[Manifest], name: str
) -> dict[str, Any]:
    schema: dict[str, Any] = _close(model.model_json_schema())
    return {**_header(name), **schema}


def _hpo_annotation_schema(name: str) -> dict[str, Any]:
    """The rules of profile hpo-phenotype that JSON Schema can express.

    It applies to each annotation of an hpo-phenotype layer, in addition to
    the document schema. Ontology rules are not expressible and are listed in
    the README.
    """
    hpo_id = {"type": "string", "pattern": hpo.HPO_ID}
    axis_values = {
        axis: {
            "type": "object",
            "required": ["value", "basis"],
            "properties": {
                "value": {"enum": list(values)},
                "basis": {"enum": ["chosen", "defaulted"]},
            },
        }
        for axis, values in hpo.AXES.items()
    }
    return {
        **_header(name),
        "title": "Annotation of an hpo-phenotype layer",
        "type": "object",
        "required": ["term_id", "axes"],
        "properties": {
            "term_id": hpo_id,
            "axes": {
                "type": "object",
                "required": list(hpo.AXES),
                "properties": axis_values,
                "additionalProperties": False,
            },
            "modifiers": {
                "type": "array",
                "items": {"type": "object", "properties": {"term_id": hpo_id}},
            },
        },
        "if": {
            "required": ["document_level"],
            "properties": {"document_level": {"const": True}},
        },
        "then": {"properties": {"mentions": {"maxItems": 0}}},
        "else": {"required": ["mentions"], "properties": {"mentions": {"minItems": 1}}},
    }


def build_schemas() -> dict[str, dict[str, Any]]:
    """The schemas of the current version, by file name."""
    document = schema_name(DOCUMENT)
    manifest = schema_name(MANIFEST)
    annotation = schema_name(HPO_ANNOTATION)
    return {
        document: _model_schema(AnnotatedDocument, document),
        manifest: _model_schema(Manifest, manifest),
        annotation: _hpo_annotation_schema(annotation),
    }


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    stale = []
    for name, schema in build_schemas().items():
        target = SCHEMA_DIR / name
        rendered = render(schema)
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
                stale.append(name)
        else:
            target.write_text(rendered, encoding="utf-8", newline="\n")
    if stale:
        print(f"Stale schemas: {', '.join(stale)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
