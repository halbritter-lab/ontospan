"""Profile `hpo-phenotype` (T1 F5, F6, F8).

The axis values are closed lists: a new value needs a new major version.
"""

from __future__ import annotations

import re

from ontospan.models import Annotation, AxisValue, Layer
from ontospan.ontology import is_under
from ontospan.profiles.base import Context
from ontospan.report import Issue, Level

NAME = "hpo-phenotype"
HPO_ID = r"^HP:\d{7}$"
CLINICAL_MODIFIER = "HP:0012823"
FREQUENCY = "HP:0040279"
SEVERITY = "HP:0012824"
ONSET = "HP:0003674"
AXES: dict[str, tuple[str, ...]] = {
    "assertion": ("present", "absent", "uncertain"),
    "experiencer": ("patient", "family_member", "other", "unknown"),
    "temporality": ("current", "historical", "unknown"),
}
DEFAULTS = {"assertion": "present", "experiencer": "patient", "temporality": "current"}
_HPO_ID = re.compile(HPO_ID)


def default_axes() -> dict[str, AxisValue]:
    """The values a new annotation starts with, marked as not chosen yet."""
    return {
        axis: AxisValue(value=value, basis="defaulted")
        for axis, value in DEFAULTS.items()
    }


def check_annotation(layer: Layer, annotation: Annotation, ctx: Context) -> list[Issue]:
    issues: list[Issue] = []
    path = ctx.path

    def add(code: str, where: str, message: str, level: Level = "error") -> None:
        issues.append(Issue(level, code, where, message))

    term = annotation.term_id
    if not _HPO_ID.match(term):
        add("not_an_hpo_id", f"{path}.term_id", f"{term!r} is not an HPO id")
    missing = set(AXES) - set(annotation.axes)
    unknown = set(annotation.axes) - set(AXES)
    if missing or (unknown and not ctx.newer_minor):
        add("axes", f"{path}.axes", f"axes must be {sorted(AXES)}")
    elif unknown:
        add(
            "unknown_axis", f"{path}.axes", f"unknown axes {sorted(unknown)}", "warning"
        )
    for axis, allowed in AXES.items():
        given = annotation.axes.get(axis)
        if given is not None and given.value not in allowed:
            add(
                "axis_value", f"{path}.axes.{axis}", f"{given.value!r} not in {allowed}"
            )
    if not annotation.mentions and not annotation.document_level:
        add("missing_evidence", f"{path}.mentions", "no mentions: set document_level")
    if annotation.mentions and annotation.document_level:
        add("document_level_with_mentions", f"{path}.document_level", "has mentions")
    for index, modifier in enumerate(annotation.modifiers):
        if not _HPO_ID.match(modifier.term_id):
            where = f"{path}.modifiers[{index}].term_id"
            add("not_an_hpo_id", where, f"{modifier.term_id!r} is not an HPO id")

    ontology = ctx.ontology
    if ontology is None:
        return issues
    where = f"{path}.term_id"
    if not ontology.is_active(term):
        add("unknown_term", where, f"{term} is not an active HPO term")
    elif is_under(ontology, term, CLINICAL_MODIFIER) or is_under(
        ontology, term, FREQUENCY
    ):
        add("modifier_as_annotation", where, f"{term} is a modifier")
    elif layer.allowed_roots and not any(
        is_under(ontology, term, root) for root in layer.allowed_roots
    ):
        add(
            "outside_allowed_roots",
            where,
            f"{term} not under {list(layer.allowed_roots)}",
        )
    for index, modifier in enumerate(annotation.modifiers):
        where = f"{path}.modifiers[{index}].term_id"
        if not ontology.is_active(modifier.term_id):
            add("unknown_term", where, f"{modifier.term_id} is not an active HPO term")
        elif is_under(ontology, modifier.term_id, FREQUENCY):
            add(
                "cohort_frequency",
                where,
                "a cohort frequency, not one patient",
                "warning",
            )
        elif not is_under(ontology, modifier.term_id, CLINICAL_MODIFIER):
            add("not_a_modifier", where, f"{modifier.term_id} is no clinical modifier")
    return issues
