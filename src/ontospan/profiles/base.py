"""What a profile checker gets and returns."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ontospan.models import Annotation, Layer
from ontospan.ontology import OntologyView
from ontospan.report import Issue


@dataclass(frozen=True)
class Context:
    """Where an annotation sits and what is known around it."""

    path: str
    ontology: OntologyView | None = None
    # The unit declares a newer minor version than this package knows.
    newer_minor: bool = False


Checker = Callable[[Layer, Annotation, Context], list[Issue]]
