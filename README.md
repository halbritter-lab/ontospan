# ontospan

Shared format for ontology concept annotations on text spans, used by
Ontocurator, Phentrieve and phentrieve-benchmark.

- Canonical text (NFC, LF, no BOM) with Unicode codepoint offsets.
- One annotated document = one text + one annotation set; bundles group them.
- Profiles: `generic` and `hpo-phenotype` (axes, modifiers, allowed roots).
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

### References

An annotation is referenced as `urn:ontospan:<annotation_set_id>:<annotation_id>`.
Exports prefix the bundle: `urn:ontospan:<bundle_id>:<annotation_set_id>:<annotation_id>`.
Every part is percent-encoded, so ids may contain `:`. `source_refs` use the
same syntax.

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
