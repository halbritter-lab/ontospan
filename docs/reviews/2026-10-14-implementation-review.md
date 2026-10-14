# Ontospan implementation and review record

Date: 2026-10-14. Tasks 1–12 of the reviewed T1 plan are complete on `feat/shared-annotation-format`, final code commit `acba84c`. The empty `main` baseline is `92d0ebc`. Task 13 (private GitHub publication) is separate and awaits explicit authorization; no remote, push or merge exists.

A fresh-context Codex review agent and a separate read-only Claude Code 2.1.296 session reviewed `92d0ebc..52fb89a`. Their findings were combined and corrected in one pass, with observed failing and passing regression tests. The [original Claude report](2026-10-14-claude-code-review.md) describes the pre-correction state. No second review was claimed. No Critical or Important finding remains open.

## Corrected findings

| Area | Correction and evidence |
|---|---|
| T1 newer-minor bundles | Manifests declare a version appropriate to their units; completed manifests are checked before writing. Directory and ZIP round trips retain future optional layer/ontology fields. |
| T1 manifest identity | Identical and conflicting duplicate layer IDs are rejected before constructing a lookup. |
| T1 serialized contracts | Both `schema_version` and `artifact_type` are required in document and manifest JSON schemas, including newer-minor reads. Constructor defaults remain convenient. Conformance fixtures cover missing discriminators and versions. |
| T1 archives | Invalid ZIP, CRC and decompression failures become `FormatError` with `invalid_archive`; unrelated filesystem errors retain their native types. |
| T1 references | Malformed percent escapes and invalid UTF-8 are rejected. Valid Unicode, literal percent signs and encoded colons retain their identity. |
| T1 Unicode | Recursive checks cover document text, keys and unknown fields. Loading and dumping invalid Unicode produce structured errors instead of leaking encoding exceptions. |
| T1 known field types | Newer-minor reads retain strict JSON types for known fields while accepting future fields/profiles. ISO timestamps and JSON arrays remain valid. |
| T1 agreement | `terms_a`, `terms_b` and `terms_equal` expose the distinct term-set counts needed for micro-averaging. |
| T1 warnings | Optional `report=` sinks preserve loader warnings and prefix bundle unit issues with file paths. Existing return types are unchanged. |
| T1 parser boundaries | ASCII SemVer, duplicate JSON keys and all leading BOMs have explicit validation/idempotence regressions. |
| T1 Phenopackets | Default export is per document/unit; subject grouping is explicit. Alternate sets of one document cannot be silently combined, duplicate-document packet IDs include set identity, and ontology release conflicts/mismatches are rejected. |

## Final verification

The coordinator independently verified **181 tests passed, 1 skipped** (Windows lacks directory-symlink creation permission). Ruff, format (35 files), mypy (18 source files), schema drift, sdist and wheel builds pass. The final wheel imports in a clean environment without optional Phenopacket dependencies and includes all three schemas; both serialized artifact schemas require explicit versions and discriminators.

The matching implementation was also checked by Claude against 3,000 brute-force assignment examples. Current tests use synthetic documents and the miniature ontology, without live data or services.

## Decisions and deviations

2. T1 is implemented on a feature branch rather than directly on `main`. Its code stays in the separate repository specified by the plan.
3. The execution ledgers were retained through final review instead of being cleaned up before coordination. Their decisions are preserved here before scratch cleanup.
4. The T1 scaffold smoke test was written before implementation; the editable package was subsequently reinstalled once because the first installation saw an empty source tree. This changes development setup only.
5. The T1 schema directory may include Python's `__pycache__`; verification checks the three actual schema files rather than an exact directory listing. No contract file is omitted.
6. The plan generator defines five valid and thirteen invalid initial fixtures, despite prose saying fourteen invalid. All defined cases were retained, and review regressions add further conformance cases.
12. Unicode crashes, known-type coercion and missing term denominators were raised from Minor to Important because they break advertised validation, compatibility and micro-averaging behavior. They are fixed rather than deferred.
13. Subject grouping defaults to `False` because binding spec F9 explicitly makes grouping optional, overriding the plan code's `True`. Callers must opt into grouping.
14. Current unreleased 1.0 schema files were regenerated to repair required discriminators; constructor defaults are retained. Consumers of the development schemas must update them before release.
15. Optional `report=` sinks preserve existing loader return types. Callers must supply a sink to inspect warnings; README shows the supported usage.
16. Grouped exports reject alternate sets, conflicting releases and a mismatched ontology instead of selecting data silently. Callers select one set per document and provide the matching ontology.
17. The conformance index supplies `artifact_type` externally, because an invalid fixture may omit its own discriminator. External fixture runners use that index to select schemas.
18. Missing files and filesystem permission failures retain native exceptions; corrupt archive data uses `FormatError`. Import callers handle those two classes separately.

## Deferred minor findings

- T1: new local repository `C:/Users/jan-p/Development/ontospan`, branch `feat/shared-annotation-format`, empty `main` baseline `92d0ebc`. Final code commit: `acba84c`.
- T1: uppercase `.ZIP` chooses a directory; suffix handling can become case-insensitive.
- T1: Windows junction-specific regression coverage; the symlink regression requires privileges unavailable here.
- T1: optimal matching has cubic worst-case runtime; large live-agreement workloads can use prepared keys and overlap components later.
- T1: after an out-of-range segment, additional ordering diagnostics may be incomplete; the input is already rejected.
- T1: `allowed_roots` syntax/existence checks and further model/bundle conformance fixtures.
- T1: listed units outside `documents/` are accepted by the reader, though the writer emits the planned directory structure.

## Deliberate boundaries

Unlisted files, including incidental OS files, remain rejected to maintain manifest integrity. Valid percent-escape hex case is accepted, and source references may point outside the current bundle. Directory reading assumes stable input during verification; concurrent filesystem swaps need a separate trust-boundary design. Multi-set adjudication, downstream migrations and clinical Phenopacket validation are separate work. `parse_phenopacket` provides structural parsing; historical export and fixed ECO identifiers follow the binding spec.

The paired Ontocurator/T1 review record is retained in the Ontocurator feature branch under `docs/superpowers/reviews/2026-10-14-t0-t1-implementation-review.md`. Both implementation branches and built artifacts remain local.
