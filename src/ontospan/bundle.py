"""Bundles: a directory or ZIP with manifest.json and documents/*.json (T1 F3).

Files are hashed byte for byte. Keep bundles in Git with ``*.json text
eol=lf`` (see ``.gitattributes``); a CRLF checkout is reported as such.
"""

from __future__ import annotations

import hashlib
import json
import lzma
import zipfile
import zlib
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from ontospan.models import (
    AnnotatedDocument,
    Contributor,
    FileEntry,
    Layer,
    Manifest,
    ReleaseInfo,
)
from ontospan.ontology import OntologyView
from ontospan.report import FormatError, ValidationReport
from ontospan.schema import MANIFEST as MANIFEST_KIND
from ontospan.validate import (
    check_schema,
    check_unicode,
    check_version,
    dump_json,
    load_annotated_document,
    parse_json,
    validate,
)

MANIFEST = "manifest.json"
MAX_TOTAL_BYTES = 512 * 1024 * 1024
# A ZIP of many tiny entries costs time per entry, not bytes.
MAX_ENTRIES = 10_000
# The first format version with the manifest ``release`` block.
RELEASE_BLOCK_VERSION = "1.1.0"


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _layers(
    units: Sequence[AnnotatedDocument], report: ValidationReport
) -> dict[str, Layer]:
    """The union of the units' layers by id; a conflicting definition is an error."""
    layers: dict[str, Layer] = {}
    for unit in units:
        for layer in unit.annotation_set.layers:
            known = layers.setdefault(layer.layer_id, layer)
            if known != layer:
                message = (
                    f"layer {layer.layer_id!r} is defined differently in two units"
                )
                report.add("error", "conflicting_layers", layer.layer_id, message)
    return layers


def _duplicate_sets(
    units: Sequence[AnnotatedDocument], report: ValidationReport
) -> None:
    seen: set[str] = set()
    for unit in units:
        set_id = unit.annotation_set.annotation_set_id
        if set_id in seen:
            message = f"annotation set {set_id!r} occurs twice"
            report.add("error", "duplicate_annotation_set", set_id, message)
        seen.add(set_id)


def _duplicate_variants(
    units: Sequence[AnnotatedDocument], report: ValidationReport
) -> None:
    """One document, language and variant version has exactly one text.

    Units without a variant are not compared, as in format 1.0. Whether
    ``derived_from`` resolves is not checked: the source may live elsewhere.
    """
    texts: dict[tuple[str, str, int], str] = {}
    for unit in units:
        document = unit.document
        if document.variant is None:
            continue
        key = (document.document_id, document.language, document.variant.version)
        known = texts.setdefault(key, document.text_sha256)
        if known != document.text_sha256:
            message = (
                f"document {key[0]!r} ({key[1]}) has two texts for version {key[2]}"
            )
            report.add("error", "variant_duplicate", key[0], message)


def write_bundle(
    target: Path,
    units: Sequence[AnnotatedDocument],
    *,
    bundle_id: str,
    created_at: datetime,
    release_name: str | None = None,
    contributors: Sequence[Contributor] = (),
    release: ReleaseInfo | None = None,
) -> Manifest:
    """Write a bundle; a target ending in .zip becomes a ZIP, otherwise a new directory.

    ``release`` fills the manifest ``release`` block (format 1.1);
    ``release_name`` defaults to its name and must equal it when both are given.
    Raises ``FormatError`` if a unit is invalid, layers conflict, a set id
    or a variant version repeats; nothing is written then.
    """
    if release is not None and release_name is None:
        release_name = release.name
    report = ValidationReport()
    if not units:
        report.add("error", "empty_bundle", "$", "a bundle needs at least one unit")
    for index, unit in enumerate(units):
        for issue in validate(unit).errors:
            report.add(
                "error", issue.code, f"units[{index}].{issue.path}", issue.message
            )
    layers = _layers(units, report)
    _duplicate_sets(units, report)
    _duplicate_variants(units, report)
    if not report.ok:
        raise FormatError(report)
    versions = [unit.schema_version for unit in units]
    if release is not None:
        versions.append(RELEASE_BLOCK_VERSION)
    files = {
        f"documents/{index:05d}.json": dump_json(unit)
        for index, unit in enumerate(units)
    }
    manifest = Manifest(
        schema_version=max(versions, key=_semver),
        bundle_id=bundle_id,
        release_name=release_name,
        release=release,
        created_at=created_at,
        layers=tuple(layers.values()),
        contributors=tuple(contributors),
        files=tuple(
            FileEntry(path=path, sha256=hashlib.sha256(data).hexdigest())
            for path, data in files.items()
        ),
    )
    payload = {MANIFEST: dump_json(manifest), **files}
    _read_manifest(payload, report)
    if target.suffix == ".zip":
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, data in payload.items():
                archive.writestr(path, data)
    else:
        target.mkdir(parents=True, exist_ok=False)
        for path, data in payload.items():
            (target / path).parent.mkdir(parents=True, exist_ok=True)
            (target / path).write_bytes(data)
    return manifest


def _read_directory(source: Path, report: ValidationReport) -> dict[str, bytes]:
    root = source.resolve()
    paths: list[Path] = []
    for path in sorted(source.rglob("*")):
        name = path.relative_to(source).as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            report.add(
                "error", "unsafe_path", name, "links are not allowed in a bundle"
            )
        elif path.is_file():
            paths.append(path)
    if sum(path.stat().st_size for path in paths) > MAX_TOTAL_BYTES:
        report.add("error", "too_large", str(source), "bundle exceeds the size limit")
    if not report.ok:
        return {}
    return {path.relative_to(source).as_posix(): path.read_bytes() for path in paths}


def _read_zip(source: Path, report: ValidationReport) -> dict[str, bytes]:
    with zipfile.ZipFile(source) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_ENTRIES:
            report.add("error", "too_large", str(source), "bundle has too many entries")
            return {}
        counts = Counter(info.filename for info in infos)
        for name in sorted(name for name, count in counts.items() if count > 1):
            report.add(
                "error", "duplicate_entry", name, "the ZIP holds this name twice"
            )
        if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
            report.add(
                "error", "too_large", str(source), "bundle exceeds the size limit"
            )
        if not report.ok:
            return {}
        return {info.filename: archive.read(info) for info in infos}


def _read_manifest(contents: Mapping[str, bytes], report: ValidationReport) -> Manifest:
    if MANIFEST not in contents:
        report.add("error", "missing_manifest", MANIFEST, "bundle has no manifest.json")
        raise FormatError(report)
    try:
        data = parse_json(contents[MANIFEST])
    except FormatError as exc:
        report.issues.extend(exc.report.issues)
        raise FormatError(report) from exc
    if not isinstance(data, dict):
        report.add("error", "not_an_object", MANIFEST, "the manifest is an object")
        raise FormatError(report)
    check_unicode(data, report)
    if not report.ok:
        raise FormatError(report)
    version = check_version(data.get("schema_version"), report)
    if version is not None:
        check_schema(data, MANIFEST_KIND, version, report)
    if not report.ok:
        raise FormatError(report)
    try:
        manifest = (
            Manifest.model_validate_json(json.dumps(data), strict=True)
            if version is not None and version.newer
            else Manifest.model_validate(data)
        )
    except ValidationError as exc:
        report.add("error", "model", MANIFEST, str(exc))
        raise FormatError(report) from exc
    seen_layers: set[str] = set()
    for index, layer in enumerate(manifest.layers):
        if layer.layer_id in seen_layers:
            report.add(
                "error",
                "duplicate_layer",
                f"manifest.layers[{index}]",
                f"layer {layer.layer_id!r} is declared twice",
            )
        seen_layers.add(layer.layer_id)
    release = manifest.release
    if release is not None and manifest.release_name not in (None, release.name):
        message = (
            f"release_name {manifest.release_name!r} differs from "
            f"release.name {release.name!r}"
        )
        report.add("error", "release_name_mismatch", MANIFEST, message)
    if not report.ok:
        raise FormatError(report)
    return manifest


def _check_hash(path: str, data: bytes, sha: str, report: ValidationReport) -> bool:
    if hashlib.sha256(data).hexdigest() == sha:
        return True
    if hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest() == sha:
        message = "line endings were changed to CRLF, e.g. by a Git checkout"
        report.add("error", "crlf_checkout", path, message)
    else:
        report.add("error", "file_hash", path, "file does not match its manifest hash")
    return False


def _load_bundle(
    source: Path,
    ontologies: Mapping[str, OntologyView] | None,
    report: ValidationReport,
) -> tuple[Manifest, list[AnnotatedDocument]]:
    """Read and verify a bundle; raises ``FormatError`` with every problem found."""
    if source.is_dir():
        contents = _read_directory(source, report)
    else:
        try:
            contents = _read_zip(source, report)
        except (
            zipfile.BadZipFile,
            zlib.error,
            lzma.LZMAError,
            EOFError,
            RuntimeError,
            NotImplementedError,
        ) as exc:
            report.add(
                "error",
                "invalid_archive",
                str(source),
                f"cannot decode ZIP archive: {exc}",
            )
            raise FormatError(report) from exc
    for name in contents:
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or "\\" in name:
            report.add("error", "unsafe_path", name, "path escapes the bundle")
    if not report.ok:
        raise FormatError(report)
    manifest = _read_manifest(contents, report)

    listed: dict[str, str] = {}
    for entry in manifest.files:
        if entry.path in listed:
            report.add("error", "duplicate_file_entry", entry.path, "listed twice")
        listed[entry.path] = entry.sha256
    for name in sorted(set(contents) - set(listed) - {MANIFEST}):
        report.add("error", "unlisted_file", name, "file is not listed in the manifest")
    units: list[AnnotatedDocument] = []
    for path, sha in listed.items():
        if path not in contents:
            report.add("error", "missing_file", path, "listed file is missing")
        elif _check_hash(path, contents[path], sha, report):
            unit_report = ValidationReport()
            with suppress(FormatError):
                units.append(
                    load_annotated_document(
                        contents[path], ontologies, report=unit_report
                    )
                )
            for issue in unit_report.issues:
                report.add(
                    issue.level, issue.code, f"{path}:{issue.path}", issue.message
                )
    _duplicate_sets(units, report)
    _duplicate_variants(units, report)
    layers = _layers(units, report)
    if report.ok and layers != {layer.layer_id: layer for layer in manifest.layers}:
        message = "manifest layers differ from the documents' layers"
        report.add("error", "manifest_layers", MANIFEST, message)
    if not report.ok:
        raise FormatError(report)
    return manifest, units


def read_bundle(
    source: Path,
    ontologies: Mapping[str, OntologyView] | None = None,
    *,
    report: ValidationReport | None = None,
) -> tuple[Manifest, list[AnnotatedDocument]]:
    """Read a bundle; optionally collect every warning and error in ``report``."""
    checked = ValidationReport()
    try:
        return _load_bundle(source, ontologies, checked)
    finally:
        if report is not None:
            report.issues.extend(checked.issues)
