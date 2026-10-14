"""Profile `generic`: any ontology, any axes; only term existence and roots."""

from __future__ import annotations

from ontospan.models import Annotation, Layer
from ontospan.ontology import is_under
from ontospan.profiles.base import Context
from ontospan.report import Issue

NAME = "generic"


def check_annotation(layer: Layer, annotation: Annotation, ctx: Context) -> list[Issue]:
    ontology = ctx.ontology
    if ontology is None:
        return []
    term = annotation.term_id
    where = f"{ctx.path}.term_id"
    if not ontology.is_active(term):
        return [Issue("error", "unknown_term", where, f"{term} is not an active term")]
    if layer.allowed_roots and not any(
        is_under(ontology, term, root) for root in layer.allowed_roots
    ):
        roots = list(layer.allowed_roots)
        return [
            Issue("error", "outside_allowed_roots", where, f"{term} not under {roots}")
        ]
    return []
