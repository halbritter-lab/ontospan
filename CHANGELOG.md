# Changelog

## 1.2.0

Format 1.2 adds optional annotation reviewer resolution metadata. Frozen
1.0/1.1 schemas and historical unit/bundle round trips are preserved.

- Public `ReviewResolution` model and optional `Annotation.review_resolution`:
  `outcome: "uncertain"`, `reviewer: Actor`, optional `note: str`.
  Absent blocks and notes are omitted when serialized.
- Clinical axes, original provenance, source references and clinical notes
  remain independent of the reviewer block.
- Phenopacket conversion raises `ValueError` for any annotation with a
  reviewer resolution, including when `include_uncertain=True`; that option
  continues to control clinical assertion uncertainty only.
- Versioned 1.2 schemas and reviewer resolution conformance fixtures.

## 1.1.0

Format 1.1 adds optional fields only. 1.0 units and bundles stay valid; the
1.0 schema files are unchanged.

- Documents: optional `case_id`, `variant` (`version`, `origin`,
  `derived_from`) and `translation` (`provider`, `model`, `run_id`, `recipe`,
  `checks`).
- Manifests: optional `release` block (`name`, `description`, `project_id`,
  `producer`, `supersedes`). `write_bundle()` accepts `release=`.
- New validation codes: `variant_derived_from_missing`,
  `variant_native_invalid`, `variant_version_invalid`,
  `variant_self_reference`, `translation_unexpected` (errors) and
  `translation_missing` (warning).
- New bundle codes: `variant_duplicate` and `release_name_mismatch`.
- New public names: `Variant`, `VariantOrigin`, `Translation`,
  `TranslationCheck`, `ReleaseInfo`, `Producer`, `SupersededRelease`.
- Schemas `annotated-document-1.1.json`, `bundle-manifest-1.1.json` and
  `hpo-phenotype-annotation-1.1.json`; conformance fixtures for variants, the
  release block and a 1.0 unit.

## 1.0.0

First release of the shared format: annotated documents, bundles, the
`generic` and `hpo-phenotype` profiles, matching and agreement, and the
Phenopacket export.
