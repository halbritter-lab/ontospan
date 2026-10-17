# Format 1.2 reviewer resolution

This minor-version extension supplies the technical format needed to export
unresolved Ontocurator reviewer decisions without changing clinical axes.
It introduces no clinical policy. Ontocurator requires a note on future
unresolved decisions; the shared format permits an omitted note solely to
represent historical exports faithfully.

Construct `ReviewResolution(outcome="uncertain", reviewer=Actor(...),
note=...)` and set `Annotation.review_resolution`. Use a 1.2.0 unit; older
declared versions reject the block. Retain the original actor, method, axes,
evidence, defaulted basis and provenance notes. A source proposal can be
identified with a `provenance.source_refs` URN. Do not replace original
provenance with the reviewer or infer an adoption/edit method from the flag.

Default construction now declares format 1.2.0. Historical declared versions
remain unchanged on load/write; absent blocks and notes are omitted.
Bundle directory and ZIP writers preserve the structured block and declare
the maximum unit version in the manifest. Schema dispatch uses the declared
minor, with frozen 1.0/1.1 schemas kept byte for byte. Future minor extras are
preserved according to the existing lenient forward-reading contract.

Phenopacket conversion explicitly refuses reviewer resolution with
`ValueError` identifying the annotation reference, even if the annotation
would otherwise be filtered out or `include_uncertain=True`. That option
controls clinical assertion uncertainty only. Applications must handle the
refusal rather than remove the reviewer block and silently confirm a result.

Ontocurator adoption additionally needs immutable dependency pinning,
materialization of exact proposal targets, historical missing-note warnings
and explicit import refusal until its storage preserves reviewer flags.
Those consumer changes are outside this format-only implementation.
