# Copilot instructions

This is an existing (brownfield) Python codebase. Changes are made test-first
through the **software factory**:

- Start work with the `factory-orchestrator` agent or `/factory-start`.
- Coding standards: [docs/coding-standards.md](../docs/coding-standards.md).
  Section 5 (repository-specific conventions) overrides the general rules.
- Specs live in `specs/<ID>/spec.md`; requirement ids look like `REQ-001`.
- Quality gates: `python .factory/swf.py ...` (see `.factory/swf.py --help`).
  A task is done only when its gate passes.

Always:

- Match the style of neighbouring code; reuse existing helpers.
- Keep changes inside the scope of the current spec.
- Never edit tests to make code pass. Never read `~/.factory-holdout/`.
- For numeric code: no look-ahead, explicit NaN policy, vectorised, no input
  mutation, injected RNG.
