# Vendor provenance clarification (2026-10-26)

`PROVENANCE.json` records acquisition from GEMSDOE31 commit `597b04cd1afb65d1ebbe3e9417fd952be48e3d74` and SHA-256 hashes for the files as acquired. Those hashes were checked locally on this date. The vendor README instead claims a direct 57GEMSDOE source and references `registry/shared_template.json`, which is absent in this checkout. The claimed transitive upstream origin has not been independently established here. Preserve the original README and receipt as historical bytes; do not describe the discrepancy as resolved.

The current review uses the shared `src/gems32/` template and canonical scripts, not the vendored GEMSDOE57 writer/evaluator as a private fork. The vendored literal uniqueness code illustrates the lattice rule but is not an organizer-authenticated scorer.
