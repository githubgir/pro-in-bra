# {{SPEC_ID}}: {{TITLE}}

- **Source issue:** {{ISSUE}}
- **Status:** draft <!-- draft | approved | superseded -->
- **Codebase context:** [context.md](context.md)

## 1. Summary

<!-- Two or three sentences: what changes for whom, and why. -->

## 2. Scope

**In scope**

-

**Out of scope (non-goals)**

-

## 3. Interfaces

<!-- Public functions/classes/CLI/config this work adds or changes, with full
type signatures. Name the module each lives in. Existing signatures that must
NOT change are listed under "Brownfield impact". -->

```python
```

## 4. Requirements

<!-- One row per testable behaviour. IDs are REQ-001, REQ-002, ... and are
never renumbered once tests reference them. Every REQ needs at least one test
whose name contains it (e.g. test_req_001_...). Use Given/When/Then. -->

| ID | Requirement | Acceptance (Given / When / Then) |
|----|-------------|----------------------------------|

## 5. Edge cases and errors

<!-- Empty input, NaN/inf, single observation, duplicate or unsorted index,
time zones, missing data, invalid arguments (which exception, which message). -->

-

## 6. Data and numerical conventions

<!-- dtypes, units, annualisation, day counts, tolerances (rtol/atol), seeds,
look-ahead rules (what information is available at time t). -->

-

## 7. Non-functional requirements

<!-- Performance budget (e.g. 10y x 3000 assets daily < 2s), memory, logging. -->

-

## 8. Brownfield impact

<!-- Existing modules touched, behaviour that must stay the same (these get
characterization tests), callers that may be affected, migrations. -->

| Existing code | Change | Characterization test needed? |
|---------------|--------|-------------------------------|

## 9. Decisions (interview log)

<!-- Q: ... / A: ... captured during the interview, newest last. -->

## 10. Open questions

<!-- Must be empty before the spec is approved. -->
