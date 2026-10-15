# ontospan

Shared format for ontology concept annotations on text spans, used by
Ontocurator, Phentrieve and phentrieve-benchmark.

- Canonical text (NFC, LF, no BOM) with Unicode codepoint offsets.
- One annotated document = one text + one annotation set; bundles group them.
- Profiles: `generic` and `hpo-phenotype` (axes, modifiers, allowed roots).
- Document variants (versions, translations and their checks) and release
  metadata in bundle manifests (format 1.1).
- Matching and agreement rules shared by every tool.
- Phenopacket v2 export (`pip install ontospan[phenopacket]` adds parsing
  into the official classes).

## Usage

```python
from ontospan import ObographOntology, load_annotated_document, to_phenopacket, validate

hp = ObographOntology.load("hp.json")
report = validate(data, {"hp": hp})  # errors and warnings, nothing raised
unit = load_annotated_document(raw_bytes)  # raises FormatError on errors
packet, export_report = to_phenopacket(unit, hp)
```

Offsets are Unicode codepoints of the canonical text. In JavaScript, convert
from UTF-16 indices before writing.

To collect loader warnings, pass a `ValidationReport` as the optional
`report=` sink to `load_annotated_document()` or `read_bundle()`. Their return
values stay unchanged. For example:

```python
from ontospan import ValidationReport, read_bundle

warnings = ValidationReport()
manifest, units = read_bundle(bundle_path, {"hp": hp}, report=warnings)
for issue in warnings.warnings:
    print(issue.code, issue.path, issue.message)
```

Bundle unit issues include the document file path. This preserves warnings
about newer minor versions, unknown profiles, ontology release mismatches,
cohort frequency and unchecked ontology rules. Errors raise `FormatError`
and are also appended to the supplied report.

`to_phenopackets()` defaults to one packet per annotated document. When
alternative sets share a document ID, packet IDs include the percent-encoded
document and annotation-set identities. Unambiguous document IDs are retained.
To combine documents by subject, set `group_by_subject=True` and select one
annotation set per document first, for example the adjudicated or release set.
Grouping rejects alternate sets of the same document. Exports reject conflicting
HPO releases in one packet and a supplied ontology whose release differs from
the layer release, rather than emitting ambiguous resources or foreign labels.

## Binding contract

The contract has three parts:

1. The JSON Schemas in `src/ontospan/schema/`:
   `annotated-document-<major>.<minor>.json` and
   `bundle-manifest-<major>.<minor>.json`.
2. The profile schema `hpo-phenotype-annotation-<major>.<minor>.json`. It
   applies to each annotation of an `hpo-phenotype` layer.
3. The conformance fixtures in `conformance/`. `cases.json` lists the error
   and warning codes that each file must give when validated without an
   ontology.

Regenerate the schemas with `uv run python -m ontospan.schema_export` and the
fixtures with `uv run python tests/conformance_cases.py`.

Serialized documents and manifests require explicit `schema_version` and
`artifact_type`, although Python constructors provide defaults. Versions use
ASCII SemVer numbers without leading zeros. Readers reject duplicate JSON keys
(`duplicate_json_key`) and invalid Unicode scalar values (`invalid_unicode`).
Malformed ZIP structure or compressed data produces `invalid_archive`;
filesystem failures such as a missing input file retain their normal exceptions.

### Rules that JSON Schema cannot express

- `document.text` is canonical (`text_not_canonical`), and `text_sha256` is the
  SHA-256 of its UTF-8 bytes (`text_hash`).
- A segment has `end > start` and `len(text) == end - start`. It lies within
  the text (`segment_out_of_range`) and quotes it exactly
  (`segment_text_mismatch`).
- The segments of a mention are sorted and do not overlap
  (`segments_unordered`).
- A segment that is only whitespace or punctuation gets the warning
  `empty_after_normalization` and never matches.
- Layer ids are unique (`duplicate_layer`), and every annotation names a
  declared layer (`unknown_layer`). Annotation ids are unique within a set
  (`duplicate_annotation`).
- `source_refs` use the reference syntax below (`source_ref_syntax`).
- Ontology rules of `hpo-phenotype`: the term is active (`unknown_term`). It is
  not a clinical modifier or frequency (`modifier_as_annotation`), and it lies
  under `allowed_roots` (`outside_allowed_roots`). Modifiers lie under
  *Clinical modifier* (`not_a_modifier`); *Frequency* modifiers only warn
  (`cohort_frequency`).
- An ontology whose release differs from the layer's `ontology.version` gives
  the warning `ontology_release_mismatch`.
- In a bundle, every file is listed with its SHA-256, set ids are unique, and
  the manifest layers equal the union of the units' layers.
- Variants (1.1): a `machine_translation`, `human_translation` or `correction`
  names its `derived_from` text (`variant_derived_from_missing`). A `native`
  variant is version 1 and is not derived (`variant_native_invalid`). A
  `correction` is version 2 or later (`variant_version_invalid`).
  `derived_from` is never the variant's own `text_sha256`
  (`variant_self_reference`).
- Translations (1.1): `translation` is only allowed on a translation variant
  (`translation_unexpected`). A translation variant without it gets the
  warning `translation_missing`, since a human translation may have no run data.
- In a bundle (1.1), units with the same `document_id`, `language` and
  `variant.version` have the same `text_sha256` (`variant_duplicate`). Units
  without `variant` are not compared. `release_name` equals `release.name`
  when both are set (`release_name_mismatch`).

### Format 1.1: variants, translations and release metadata

1.1 adds optional fields only; a 1.0 unit or bundle stays valid and is
checked against the frozen 1.0 schemas.

- `document.case_id` groups the variants of one case, e.g. its original and
  its translations.
- `document.variant` is one text version in one language: `version` (1, 2,
  ...), `origin` (`native`, `machine_translation`, `human_translation`,
  `correction`) and `derived_from`, the `text_sha256` of the source text
  (translation) or of the previous version (correction).
- `document.translation` describes the run that produced a translation:
  `provider`, `model`, `run_id`, `recipe` and its automatic `checks`
  (`code`, `passed`, `detail`).
- The manifest `release` block: `name`, `description`, `project_id`,
  `producer` (`name`, `version`) and `supersedes` (`bundle_id`,
  `manifest_sha256`) for the release it corrects. `write_bundle(...,
  release=...)` fills it and sets `release_name` to its name; the manifest
  then declares at least 1.1.0.

ontospan does not resolve `derived_from`: the source text may live outside
the bundle, e.g. in the consumer's project. Consumers that need the source
look it up by its hash.

Unset 1.1 fields are left out when a unit or manifest is serialized, so a
1.0 unit read and written again still matches the 1.0 schema.

### References

An annotation is referenced as `urn:ontospan:<annotation_set_id>:<annotation_id>`.
Exports prefix the bundle: `urn:ontospan:<bundle_id>:<annotation_set_id>:<annotation_id>`.
Every part is percent-encoded, so ids may contain `:`. `source_refs` use the
same syntax.
Percent escapes must decode as strict UTF-8. Hexadecimal case does not change
their meaning. Source references may point to external annotation sets;
loaders check syntax without requiring those targets to be locally available.

## Versions

- `schema_version` follows SemVer.
- **Minor versions** add optional fields and new profiles. A reader of an
  older minor version reads newer units with warnings (`newer_minor`, and
  `unknown_profile` for profiles it does not know). It keeps unknown fields
  when it writes the unit again.
- **Closed lists** (`set_kind`, `method`, actor `kind`, `basis` and the axis
  values of a profile) only change with a new **major version**. Readers
  reject unknown major versions.
- Every released minor version keeps its frozen schema files. A unit is
  checked against the schema of the version it declares.
- Released: 1.0 and 1.1 (see `CHANGELOG.md`).

## Matching and agreement

- Segments are compared without edge whitespace and punctuation.
- Annotations pair only within one layer. The pairing is an optimal
  assignment: as many `equal` pairs as possible, then `compatible`, then
  conflicts.
- A document-level and a mention-based annotation with the same term and axes
  are `compatible`.
- `agreement()` reports F1 on three levels:
  - annotation level, strict and tolerant;
  - mention level (each mention with the term and axes of its annotation),
    strict and tolerant;
  - term level (the set of layer, term and axes).

  It also reports modifier agreement and the counts needed for
  micro-averaging.

## Bundles in Git

Bundle files are hashed byte for byte. Check them in with
`*.json text eol=lf` in `.gitattributes`. Otherwise a Windows checkout with
`core.autocrlf=true` changes them, and readers report `crlf_checkout`.
