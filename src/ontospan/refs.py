"""References to annotations: ``urn:ontospan:[<bundle>:]<set>:<annotation>``.

Every part is percent-encoded, so ids may contain ":" (T1 spec, changes after
the plan review). ``source_refs`` and Phenopacket evidence use this syntax;
exports add the bundle id.
"""

from __future__ import annotations

from typing import NamedTuple
from urllib.parse import quote, unquote

PREFIX = "urn:ontospan:"


class AnnotationRef(NamedTuple):
    annotation_set_id: str
    annotation_id: str
    bundle_id: str | None = None


def annotation_ref(
    annotation_set_id: str, annotation_id: str, bundle_id: str | None = None
) -> str:
    parts = [annotation_set_id, annotation_id]
    if bundle_id is not None:
        parts.insert(0, bundle_id)
    return PREFIX + ":".join(quote(part, safe="") for part in parts)


def parse_annotation_ref(ref: str) -> AnnotationRef:
    """The parts of a reference; ``ValueError`` if it is not one."""
    if not ref.startswith(PREFIX):
        raise ValueError(f"{ref!r} does not start with {PREFIX!r}")
    parts = [unquote(part) for part in ref[len(PREFIX) :].split(":")]
    if len(parts) not in (2, 3) or not all(parts):
        raise ValueError(f"{ref!r} needs a set id and an annotation id")
    if len(parts) == 3:
        return AnnotationRef(parts[1], parts[2], parts[0])
    return AnnotationRef(parts[0], parts[1])
