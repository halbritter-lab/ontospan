# Changelog

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
