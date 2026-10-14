"""The JSON Schema files (package data) and how they are named.

``annotated-document-<major>.<minor>.json`` and friends: one file per released
minor version. ``ontospan.schema_export`` writes the current version's files.
"""

from __future__ import annotations

from ontospan._version import SCHEMA_VERSION

DOCUMENT = "annotated-document"
MANIFEST = "bundle-manifest"
HPO_ANNOTATION = "hpo-phenotype-annotation"
KINDS = (DOCUMENT, MANIFEST, HPO_ANNOTATION)


def schema_name(kind: str, version: str = SCHEMA_VERSION) -> str:
    """The file of a schema kind for a version: patch versions share a file."""
    major, minor, _ = version.split(".")
    return f"{kind}-{major}.{minor}.json"
