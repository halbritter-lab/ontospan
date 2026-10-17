"""The shared span annotation format.

Models keep unknown fields (``extra="allow"``), so a unit of a newer minor
version survives being read and written again (T1 F3, review decision D2).
Strictness for a declared version comes from the generated JSON Schema, which
closes every object (see ``schema_export``).

Closed lists (``Basis``, ``ActorKind``, ``Method``, ``SetKind``,
``VariantOrigin`` and the axis values of a profile) only change with a new
major version.

Format 1.1 adds the optional document fields ``case_id``, ``variant`` and
``translation`` and the optional manifest block ``release``.
Format 1.2 adds optional annotation ``review_resolution`` metadata.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from ontospan._version import SCHEMA_VERSION

CURIE = r"^[A-Za-z][A-Za-z0-9_.]*:\S+$"
SHA256 = r"^[0-9a-f]{64}$"
LANGUAGE = r"^[a-z]{2,3}(-[A-Za-z0-9]+)*$"
ORCID = r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$"
VERSION = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"

Basis = Literal["chosen", "defaulted"]
ActorKind = Literal["human", "tool"]
Method = Literal["manual", "adopted", "edited", "merged", "tool"]
SetKind = Literal["individual", "stage_result", "adjudicated", "release", "tool_output"]
VariantOrigin = Literal[
    "native", "machine_translation", "human_translation", "correction"
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class _OmitsUnset(_Model):
    """Leaves out absent optional fields added by minor format versions.

    A 1.0 unit or manifest is written again without them, so it still
    matches the closed schema of the version it declares.
    """

    _omit_if_none: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler: SerializerFunctionWrapHandler) -> Any:
        data = handler(self)
        if isinstance(data, dict):
            for name in self._omit_if_none:
                if data.get(name, ...) is None:
                    del data[name]
        return data


class Segment(_Model):
    """A codepoint range [start, end) of the canonical text and the text it quotes."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Segment:
        if self.end <= self.start:
            raise ValueError("segment end must be greater than start")
        if len(self.text) != self.end - self.start:
            raise ValueError("segment text length must equal end - start")
        return self


class Mention(_Model):
    """One place a concept is mentioned; several segments make it discontinuous."""

    segments: tuple[Segment, ...] = Field(min_length=1)
    cue_segments: tuple[Segment, ...] = ()


class AxisValue(_Model):
    value: str = Field(min_length=1)
    basis: Basis


class Modifier(_Model):
    term_id: str = Field(pattern=CURIE)
    segments: tuple[Segment, ...] = ()


class Actor(_Model):
    actor_id: str = Field(min_length=1)
    kind: ActorKind
    name: str | None = None
    version: str | None = None
    model: str | None = None
    run_id: str | None = None


class Provenance(_Model):
    actor: Actor
    method: Method
    # References in the form urn:ontospan:<annotation_set_id>:<annotation_id>.
    source_refs: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class ReviewResolution(_OmitsUnset):
    """Reviewer uncertainty, independent of clinical axes and source provenance.

    The optional note permits faithful historical exports. Applications may
    require a note on new review decisions in their own write validation.
    """

    _omit_if_none = ("note",)

    outcome: Literal["uncertain"]
    reviewer: Actor
    note: str | None = None


class Annotation(_OmitsUnset):
    _omit_if_none = ("review_resolution",)

    annotation_id: str = Field(min_length=1)
    layer_id: str = Field(min_length=1)
    term_id: str = Field(pattern=CURIE)
    axes: dict[str, AxisValue] = Field(default_factory=dict)
    mentions: tuple[Mention, ...] = ()
    document_level: bool = False
    modifiers: tuple[Modifier, ...] = ()
    provenance: Provenance
    review_resolution: ReviewResolution | None = None


class OntologyResource(_Model):
    id: str = Field(min_length=1)
    # The release, e.g. "2026-06-23" for HPO.
    version: str = Field(min_length=1)
    sha256: str | None = Field(default=None, pattern=SHA256)
    iri: str | None = None


class Layer(_Model):
    layer_id: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    ontology: OntologyResource
    allowed_roots: tuple[str, ...] = ()


class AnnotationSet(_Model):
    annotation_set_id: str = Field(min_length=1)
    set_kind: SetKind
    stage: str | None = None
    actors: tuple[Actor, ...] = Field(min_length=1)
    created_at: AwareDatetime
    blind: bool | None = None
    guideline_ref: str | None = None
    layers: tuple[Layer, ...] = Field(min_length=1)
    annotations: tuple[Annotation, ...] = ()


class Variant(_Model):
    """One text version of a case in one language (format 1.1)."""

    version: int = Field(ge=1)
    origin: VariantOrigin
    # The text_sha256 of the source text (translation) or previous version.
    derived_from: str | None = Field(default=None, pattern=SHA256)


class TranslationCheck(_Model):
    """One automatic check of a translation run."""

    code: str = Field(min_length=1)
    passed: bool
    detail: str | None = None


class Translation(_Model):
    """The run that produced a translation and its automatic checks."""

    provider: str = Field(min_length=1)
    model: str | None = None
    run_id: str | None = None
    recipe: str | None = None
    checks: tuple[TranslationCheck, ...] = ()


class Document(_OmitsUnset):
    _omit_if_none = ("case_id", "variant", "translation")

    document_id: str = Field(min_length=1)
    language: str = Field(pattern=LANGUAGE)
    text: str
    text_sha256: str = Field(pattern=SHA256)
    source_text_sha256: str | None = Field(default=None, pattern=SHA256)
    subject_id: str | None = None
    # Format 1.1: the case that groups the variants of one text.
    case_id: str | None = Field(default=None, min_length=1)
    variant: Variant | None = None
    translation: Translation | None = None


class AnnotatedDocument(_Model):
    """The atomic unit: one canonical text and exactly one annotation set."""

    schema_version: str = Field(default=SCHEMA_VERSION, pattern=VERSION)
    artifact_type: Literal["annotated_document"] = "annotated_document"
    document: Document
    annotation_set: AnnotationSet


class Contributor(_Model):
    actor_id: str = Field(min_length=1)
    name: str | None = None
    orcid: str | None = Field(default=None, pattern=ORCID)


class FileEntry(_Model):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256)


class Producer(_Model):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class SupersededRelease(_Model):
    bundle_id: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=SHA256)


class ReleaseInfo(_Model):
    """Release metadata of a bundle (format 1.1)."""

    name: str = Field(min_length=1)
    description: str | None = None
    project_id: str | None = None
    producer: Producer | None = None
    supersedes: tuple[SupersededRelease, ...] = ()


class Manifest(_OmitsUnset):
    _omit_if_none = ("release",)

    schema_version: str = Field(default=SCHEMA_VERSION, pattern=VERSION)
    artifact_type: Literal["bundle"] = "bundle"
    bundle_id: str = Field(min_length=1)
    release_name: str | None = None
    created_at: AwareDatetime
    layers: tuple[Layer, ...] = Field(min_length=1)
    contributors: tuple[Contributor, ...] = ()
    files: tuple[FileEntry, ...] = Field(min_length=1)
    # Format 1.1; release_name must equal release.name when both are set.
    release: ReleaseInfo | None = None
