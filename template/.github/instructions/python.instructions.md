---
applyTo: "**/*.py"
---

# Python code

Follow [docs/coding-standards.md](../../docs/coding-standards.md), sections 1, 2 and 4,
plus section 5 for this repository's own conventions. In short:

- Full type hints; NumPy-style docstrings on public functions; `ruff` and `mypy` clean.
- Specific exceptions with helpful messages; `logging`, not `print`.
- Numeric code: no look-ahead (lag signals), explicit `periods_per_year`,
  explicit NaN policy, sorted unique `DatetimeIndex`, vectorised, never mutate
  inputs, randomness via an injected `np.random.Generator`.
- Reuse existing helpers; match neighbouring code; stay within the spec.
