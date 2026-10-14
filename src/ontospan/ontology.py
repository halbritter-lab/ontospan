"""What the format needs to know about an ontology, and a loader for OBO Graph JSON.

Tools pass their own ontology through ``OntologyView``; ``ObographOntology``
is a small stdlib implementation for files such as ``hp.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Protocol

_RELEASE = re.compile(r"/releases/([^/]+)/")


class OntologyView(Protocol):
    @property
    def release(self) -> str | None:
        """The release, comparable with a layer's ``ontology.version``."""
        ...

    def label(self, term_id: str) -> str | None: ...

    def is_active(self, term_id: str) -> bool: ...

    def ancestors(self, term_id: str) -> frozenset[str]:
        """Every term above ``term_id`` (``is_a``, transitive), without itself."""
        ...


def is_under(ontology: OntologyView, term_id: str, root: str) -> bool:
    """True if the term is the root or one of its descendants."""
    return term_id == root or root in ontology.ancestors(term_id)


def release_of(version: str | None) -> str | None:
    """The release in a version IRI (".../releases/2026-06-23/hp.json")."""
    if version is None:
        return None
    found = _RELEASE.search(version)
    return found.group(1) if found else version


def _curie(iri: str) -> str:
    local = iri.rsplit("/", 1)[-1]
    prefix, sep, rest = local.partition("_")
    return f"{prefix}:{rest}" if sep else local


class ObographOntology:
    def __init__(
        self,
        labels: dict[str, str],
        parents: dict[str, frozenset[str]],
        obsolete: frozenset[str],
        version: str | None,
    ) -> None:
        self._labels = labels
        self._parents = parents
        self._obsolete = obsolete
        self.version = version
        self._ancestors: dict[str, frozenset[str]] = {}

    @classmethod
    def load(cls, path: Path | str) -> ObographOntology:
        graph = json.loads(Path(path).read_text(encoding="utf-8"))["graphs"][0]
        labels: dict[str, str] = {}
        obsolete: set[str] = set()
        parents: dict[str, set[str]] = {}
        for node in graph.get("nodes", []):
            if node.get("type", "CLASS") != "CLASS":
                continue
            term = _curie(node["id"])
            labels[term] = node.get("lbl") or term
            if node.get("meta", {}).get("deprecated"):
                obsolete.add(term)
        for edge in graph.get("edges", []):
            if edge.get("pred") == "is_a":
                parents.setdefault(_curie(edge["sub"]), set()).add(_curie(edge["obj"]))
        return cls(
            labels,
            {term: frozenset(above) for term, above in parents.items()},
            frozenset(obsolete),
            graph.get("meta", {}).get("version"),
        )

    @property
    def release(self) -> str | None:
        return release_of(self.version)

    def label(self, term_id: str) -> str | None:
        return self._labels.get(term_id)

    def is_active(self, term_id: str) -> bool:
        return term_id in self._labels and term_id not in self._obsolete

    def ancestors(self, term_id: str) -> frozenset[str]:
        known = self._ancestors.get(term_id)
        if known is not None:
            return known
        seen: set[str] = set()
        stack = list(self._parents.get(term_id, ()))
        while stack:
            parent = stack.pop()
            if parent not in seen:
                seen.add(parent)
                stack.extend(self._parents.get(parent, ()))
        seen.discard(term_id)
        result = frozenset(seen)
        self._ancestors[term_id] = result
        return result
