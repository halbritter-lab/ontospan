"""Profile registry: profile name -> annotation checker."""

from __future__ import annotations

from ontospan.profiles import generic, hpo
from ontospan.profiles.base import Checker, Context

PROFILES: dict[str, Checker] = {
    generic.NAME: generic.check_annotation,
    hpo.NAME: hpo.check_annotation,
}
# Profiles whose rules need the ontology; without it validation warns.
HIERARCHICAL_PROFILES = frozenset({hpo.NAME})

__all__ = ["HIERARCHICAL_PROFILES", "PROFILES", "Checker", "Context"]
