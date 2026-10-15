import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest
from builders import (
    CREATED,
    HPO_LAYER,
    SEIZURE,
    annotation,
    corrected_sample,
    translated_sample,
    unit,
    with_variant,
)

from ontospan import bundle
from ontospan.bundle import read_bundle, write_bundle
from ontospan.models import (
    AnnotatedDocument,
    Contributor,
    Layer,
    OntologyResource,
    Producer,
    ReleaseInfo,
    SupersededRelease,
)
from ontospan.report import FormatError, ValidationReport


def test_bundle_warnings_have_unit_file_paths(tmp_path: Path) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b", created_at=CREATED)
    report = ValidationReport()
    read_bundle(tmp_path / "b", report=report)
    assert [(i.code, i.path) for i in report.warnings] == [
        ("hierarchy_not_checked", "documents/00000.json:annotation_set.layers[0]"),
        ("hierarchy_not_checked", "documents/00001.json:annotation_set.layers[0]"),
    ]


def test_manifest_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b", created_at=CREATED)
    path = tmp_path / "b" / "manifest.json"
    raw = path.read_text().replace(
        '"schema_version": "1.1.0"',
        '"schema_version": "2.0.0", "schema_version": "1.1.0"',
    )
    path.write_text(raw, encoding="utf-8")
    assert error_codes(tmp_path / "b") == ["duplicate_json_key"]


DIAGNOSIS = Layer(
    layer_id="diagnosis",
    profile="generic",
    ontology=OntologyResource(id="mondo", version="2026-06-01"),
)


@pytest.mark.parametrize("name", ["bundle", "bundle.zip"])
def test_newer_units_keep_a_readable_manifest(tmp_path: Path, name: str) -> None:
    data = two_annotators()[0].model_dump(mode="json")
    data["schema_version"] = "1.2.3"
    data["annotation_set"]["layers"][0]["ontology"]["future_resource"] = "kept"
    data["annotation_set"]["layers"][0]["future_layer"] = {"kept": True}
    newer = AnnotatedDocument.model_validate(data)
    manifest = write_bundle(tmp_path / name, [newer], bundle_id="b", created_at=CREATED)
    assert manifest.schema_version == "1.2.3"
    assert read_bundle(tmp_path / name) == (manifest, [newer])


def test_manifest_validation_precedes_writing(tmp_path: Path) -> None:
    contributor = Contributor(actor_id="ann", future_field="unsupported")
    with pytest.raises(FormatError) as raised:
        write_bundle(
            tmp_path / "b",
            two_annotators(),
            bundle_id="b",
            created_at=CREATED,
            contributors=[contributor],
        )
    assert [i.code for i in raised.value.report.errors] == ["schema"]
    assert not (tmp_path / "b").exists()


@pytest.mark.parametrize("conflicting", [False, True])
def test_manifest_layer_ids_cannot_repeat(tmp_path: Path, conflicting: bool) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b", created_at=CREATED)
    path = tmp_path / "b" / "manifest.json"
    data = json.loads(path.read_bytes())
    duplicate = dict(data["layers"][0])
    if conflicting:
        duplicate["profile"] = "generic"
    data["layers"].insert(0, duplicate)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert error_codes(tmp_path / "b") == ["duplicate_layer"]


@pytest.mark.parametrize("damage", ["nonzip", "crc", "deflate"])
def test_archive_damage_is_a_format_error(tmp_path: Path, damage: str) -> None:
    path = tmp_path / "bad.zip"
    if damage == "nonzip":
        path.write_bytes(b"this is not a zip")
    else:
        compression = zipfile.ZIP_STORED if damage == "crc" else zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            archive.writestr("manifest.json", b'{"schema_version":"1.0.0"}')
        payload = bytearray(path.read_bytes())
        offset = (
            30
            + int.from_bytes(payload[26:28], "little")
            + int.from_bytes(payload[28:30], "little")
        )
        payload[offset] ^= 255
        path.write_bytes(payload)
    assert error_codes(path) == ["invalid_archive"]


def test_missing_archive_keeps_the_filesystem_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_bundle(tmp_path / "missing.zip")


def two_annotators() -> list[AnnotatedDocument]:
    return [
        unit([annotation("a1", SEIZURE, [(63, 76)])], set_id="set-a", actor="ann-01"),
        unit(
            [annotation("b1", SEIZURE, [(55, 76)], actor="ann-02")],
            set_id="set-b",
            actor="ann-02",
        ),
    ]


def error_codes(source: Path) -> list[str]:
    with pytest.raises(FormatError) as raised:
        read_bundle(source)
    return [issue.code for issue in raised.value.report.errors]


@pytest.mark.parametrize("name", ["bundle", "bundle.zip"])
def test_a_bundle_round_trips_as_directory_and_zip(tmp_path: Path, name: str) -> None:
    units = two_annotators()
    manifest = write_bundle(
        tmp_path / name,
        units,
        bundle_id="b-1",
        release_name="Gold v1",
        contributors=[Contributor(actor_id="ann-01", orcid="0000-0002-1825-0097")],
        created_at=CREATED,
    )
    assert manifest.layers == (HPO_LAYER,)
    assert [f.path for f in manifest.files] == [
        "documents/00000.json",
        "documents/00001.json",
    ]
    assert read_bundle(tmp_path / name) == (manifest, units)


def test_a_changed_file_is_detected(tmp_path: Path) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b-1", created_at=CREATED)
    target = tmp_path / "b" / "documents" / "00000.json"
    target.write_bytes(target.read_bytes().replace(b"ann-01", b"ann-09"))
    assert error_codes(tmp_path / "b") == ["file_hash"]


def test_a_crlf_checkout_is_named_as_such(tmp_path: Path) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b-1", created_at=CREATED)
    target = tmp_path / "b" / "documents" / "00001.json"
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    assert error_codes(tmp_path / "b") == ["crlf_checkout"]


def test_escaping_paths_are_refused(tmp_path: Path) -> None:
    write_bundle(
        tmp_path / "b.zip", two_annotators(), bundle_id="b-1", created_at=CREATED
    )
    with zipfile.ZipFile(tmp_path / "b.zip", "a") as archive:
        archive.writestr("../evil.json", "{}")
    assert error_codes(tmp_path / "b.zip") == ["unsafe_path"]


def test_duplicate_zip_entries_are_refused(tmp_path: Path) -> None:
    write_bundle(
        tmp_path / "b.zip", two_annotators(), bundle_id="b-1", created_at=CREATED
    )
    with (
        zipfile.ZipFile(tmp_path / "b.zip", "a") as archive,
        pytest.warns(UserWarning, match="Duplicate name"),
    ):
        archive.writestr("documents/00000.json", "{}")
    assert error_codes(tmp_path / "b.zip") == ["duplicate_entry"]


def test_links_inside_a_directory_bundle_are_refused(tmp_path: Path) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b-1", created_at=CREATED)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        os.symlink(outside, tmp_path / "b" / "documents" / "link.json")
    except OSError:
        pytest.skip("creating symlinks is not permitted here")
    assert error_codes(tmp_path / "b") == ["unsafe_path"]


def test_unlisted_and_missing_files_are_errors(tmp_path: Path) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b-1", created_at=CREATED)
    (tmp_path / "b" / "documents" / "extra.json").write_text("{}", encoding="utf-8")
    (tmp_path / "b" / "documents" / "00001.json").unlink()
    assert error_codes(tmp_path / "b") == ["unlisted_file", "missing_file"]


@pytest.mark.parametrize("name", ["b", "b.zip"])
def test_bundles_over_the_size_limit_are_not_read(
    tmp_path: Path, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_bundle(tmp_path / name, two_annotators(), bundle_id="b-1", created_at=CREATED)
    monkeypatch.setattr(bundle, "MAX_TOTAL_BYTES", 100)
    assert error_codes(tmp_path / name) == ["too_large"]


def test_conflicting_layers_and_repeated_sets_cannot_be_written(tmp_path: Path) -> None:
    other = HPO_LAYER.model_copy(
        update={"ontology": OntologyResource(id="hp", version="2025-01-01")}
    )
    units = [unit([]), unit([], layers=[other], set_id="set-2"), unit([])]
    with pytest.raises(FormatError) as raised:
        write_bundle(tmp_path / "b", units, bundle_id="b-1", created_at=CREATED)
    codes = [issue.code for issue in raised.value.report.errors]
    assert codes == ["conflicting_layers", "duplicate_annotation_set"]
    assert not (tmp_path / "b").exists()


def test_invalid_units_cannot_be_written(tmp_path: Path) -> None:
    broken = unit([annotation("a1", SEIZURE, [(63, 76)], layer_id="x")])
    with pytest.raises(FormatError) as raised:
        write_bundle(tmp_path / "b", [broken], bundle_id="b-1", created_at=CREATED)
    assert [issue.code for issue in raised.value.report.errors] == ["unknown_layer"]


def test_the_manifest_is_strictly_validated(tmp_path: Path) -> None:
    write_bundle(tmp_path / "b", two_annotators(), bundle_id="b-1", created_at=CREATED)
    path = tmp_path / "b" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    assert error_codes(tmp_path / "b") == ["schema"]
    path.write_text("[1, 2", encoding="utf-8")
    assert error_codes(tmp_path / "b") == ["invalid_json"]
    path.write_text("[]", encoding="utf-8")
    assert error_codes(tmp_path / "b") == ["not_an_object"]


def test_manifest_layers_are_compared_by_id_not_by_order(tmp_path: Path) -> None:
    units = [
        unit([], layers=[HPO_LAYER, DIAGNOSIS]),
        unit([], set_id="set-2"),
    ]
    write_bundle(tmp_path / "b", units, bundle_id="b-1", created_at=CREATED)
    path = tmp_path / "b" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["layers"].reverse()
    path.write_text(json.dumps(data), encoding="utf-8")
    assert read_bundle(tmp_path / "b")[1] == units

    data["layers"].pop()
    path.write_text(json.dumps(data), encoding="utf-8")
    assert error_codes(tmp_path / "b") == ["manifest_layers"]


RELEASE = ReleaseInfo(
    name="Gold v2",
    description="Corrected release",
    project_id="project-1",
    producer=Producer(name="ontocurator", version="0.3.0"),
    supersedes=(SupersededRelease(bundle_id="b-0", manifest_sha256="a" * 64),),
)


@pytest.mark.parametrize("name", ["bundle", "bundle.zip"])
def test_the_release_block_round_trips(tmp_path: Path, name: str) -> None:
    units = [translated_sample()]
    manifest = write_bundle(
        tmp_path / name, units, bundle_id="b-1", created_at=CREATED, release=RELEASE
    )
    assert manifest.release == RELEASE
    assert manifest.release_name == "Gold v2"
    assert read_bundle(tmp_path / name) == (manifest, units)


def test_a_release_block_lifts_a_1_0_manifest_to_1_1(tmp_path: Path) -> None:
    data = two_annotators()[0].model_dump(mode="json")
    data["schema_version"] = "1.0.0"
    old = AnnotatedDocument.model_validate(data)
    manifest = write_bundle(
        tmp_path / "b", [old], bundle_id="b-1", created_at=CREATED, release=RELEASE
    )
    assert manifest.schema_version == "1.1.0"
    assert read_bundle(tmp_path / "b")[1] == [old]


def test_a_1_0_bundle_stays_readable(tmp_path: Path) -> None:
    units = []
    for item in two_annotators():
        data = item.model_dump(mode="json")
        data["schema_version"] = "1.0.0"
        units.append(AnnotatedDocument.model_validate(data))
    manifest = write_bundle(
        tmp_path / "b", units, bundle_id="b-1", created_at=CREATED, release_name="v1"
    )
    assert manifest.schema_version == "1.0.0"
    assert manifest.release is None
    assert read_bundle(tmp_path / "b") == (manifest, units)


def test_release_name_must_match_the_release_block(tmp_path: Path) -> None:
    with pytest.raises(FormatError) as raised:
        write_bundle(
            tmp_path / "b",
            [translated_sample()],
            bundle_id="b-1",
            created_at=CREATED,
            release_name="Gold v1",
            release=RELEASE,
        )
    assert [i.code for i in raised.value.report.errors] == ["release_name_mismatch"]
    assert not (tmp_path / "b").exists()

    write_bundle(
        tmp_path / "ok",
        [translated_sample()],
        bundle_id="b-1",
        created_at=CREATED,
        release=RELEASE,
    )
    path = tmp_path / "ok" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["release_name"] = "Gold v1"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert error_codes(tmp_path / "ok") == ["release_name_mismatch"]


def test_duplicate_variant_versions_are_refused(tmp_path: Path) -> None:
    first = translated_sample()
    assert first.document.variant is not None
    other_text = unit([], text="Andere Übersetzung.", set_id="set-2")
    second = with_variant(
        other_text, first.document.variant, first.document.translation
    )
    with pytest.raises(FormatError) as raised:
        write_bundle(
            tmp_path / "b", [first, second], bundle_id="b-1", created_at=CREATED
        )
    assert [i.code for i in raised.value.report.errors] == ["variant_duplicate"]
    assert not (tmp_path / "b").exists()


def test_duplicate_variant_versions_are_refused_on_reading(tmp_path: Path) -> None:
    first = translated_sample()
    second = with_variant(
        unit([], text="Andere Übersetzung.", set_id="set-2"),
        first.document.variant,
        first.document.translation,
    )
    write_bundle(tmp_path / "b", [first], bundle_id="b-1", created_at=CREATED)
    write_bundle(tmp_path / "c", [second], bundle_id="b-1", created_at=CREATED)
    shutil.copy(
        tmp_path / "c" / "documents" / "00000.json",
        tmp_path / "b" / "documents" / "00001.json",
    )
    path = tmp_path / "b" / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["files"].append(
        json.loads((tmp_path / "c" / "manifest.json").read_text("utf-8"))["files"][0]
        | {"path": "documents/00001.json"}
    )
    path.write_text(json.dumps(data), encoding="utf-8")
    assert error_codes(tmp_path / "b") == ["variant_duplicate"]


def test_sets_of_one_variant_and_other_versions_may_share_a_bundle(
    tmp_path: Path,
) -> None:
    units = [
        translated_sample(),
        renamed_set(translated_sample(), "set-2"),
        renamed_set(corrected_sample(), "set-3"),
    ]
    manifest = write_bundle(tmp_path / "b", units, bundle_id="b-1", created_at=CREATED)
    assert read_bundle(tmp_path / "b") == (manifest, units)


def renamed_set(item: AnnotatedDocument, set_id: str) -> AnnotatedDocument:
    changed = item.annotation_set.model_copy(update={"annotation_set_id": set_id})
    return item.model_copy(update={"annotation_set": changed})
