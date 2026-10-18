# Coding standards

These standards apply to people and to every factory agent. Where this
repository's existing code consistently does something differently, the
**Repository-specific conventions** section at the end wins. Keep that
section current with the `/derive-standards` prompt.

## 1. General Python

- Python ≥ 3.11. Format with `ruff format`; lint with `ruff check`. No
  per-line `noqa` without a reason in the same comment.
- Type hints on every public function, method and module-level constant.
  `mypy` must pass on changed files. Prefer precise types:
  `pd.Series`, `pd.DataFrame`, `npt.NDArray[np.float64]`, `Literal[...]`,
  `TypedDict`/dataclasses over loose `dict[str, Any]`.
- Docstrings in **NumPy style** on public functions: summary line,
  Parameters, Returns, Raises, and Notes for formulas or conventions.
- Small pure functions. Side effects (I/O, network, DB, clock) live at the
  edges and are passed in, so the core logic is testable without mocks.
- No magic numbers: name them (`TRADING_DAYS_PER_YEAR = 252`) or take them as
  parameters with documented defaults.
- Errors: raise specific built-in exceptions (`ValueError`, `TypeError`,
  `KeyError`) or the repo's own exception types, with a message that says what
  was wrong and what was expected. Never swallow exceptions. Never `except:`.
- Logging via `logging.getLogger(__name__)`; no `print` in library code.
- No new third-party dependencies without approval in the spec.

## 2. Numerical and quant conventions

- **No look-ahead.** A value computed for time *t* may use only information
  available at *t*. Signals are lagged before they meet returns
  (`signal.shift(1)` or an explicit `lag` parameter). Document the timing
  convention in the docstring.
- **Returns:** state whether simple or log returns, and the period. Name
  variables accordingly (`ret_simple_d`, `logret_m`), or follow the repo's names.
- **Annualisation:** explicit `periods_per_year` parameter; never infer it
  silently from index frequency.
- **Missing data:** decide and document the NaN policy per function
  (propagate / drop / fill) and test it. Never `fillna(0)` returns without a
  stated reason.
- **Index hygiene:** time series must have a sorted, unique `DatetimeIndex`.
  Validate inputs at public boundaries; be explicit about time zones.
- **Vectorise** with numpy/pandas; avoid Python loops and `DataFrame.apply`
  with `axis=1` over large data. Use loops only when the logic is recursive
  (e.g. path-dependent) and say why.
- **Do not mutate inputs.** Copy if you need to modify; return new objects.
- **Determinism:** randomness only via an injected `numpy.random.Generator`
  (`rng: np.random.Generator | None = None`), never global seeds.
- **Floating point:** compare with tolerances; choose `rtol`/`atol`
  deliberately; avoid catastrophic cancellation (prefer `np.log1p`,
  `np.expm1` where relevant).
- **Units and conventions in names:** bps vs decimals, weights summing to
  1 vs gross exposure, long-only vs long/short: never ambiguous.
- **Portfolio code:** constraints (budget, bounds, turnover) are explicit
  parameters; optimisers report convergence status and the code checks it.

## 3. Testing

- pytest. Tests mirror the source layout under `tests/`.
- Name: `test_<behaviour>`; factory-generated spec tests include the
  requirement id: `test_req_003_<behaviour>`.
- Arrange / Act / Assert; one behaviour per test; parametrise case tables.
- Float comparisons: `pytest.approx`, `np.testing.assert_allclose`,
  `pd.testing.assert_series_equal`/`assert_frame_equal` with explicit tolerance.
- Build small, hand-checkable fixtures (5-10 rows) whose expected values
  can be verified by hand or spreadsheet; add one realistic-size case for shape
  and performance where relevant.
- Property-based tests (`hypothesis`) for invariants when available:
  scale invariance, additivity of log returns, weights summing to one.
- No network, no real databases, no wall-clock dependence, no test-order
  dependence. Fixed seeds via `np.random.default_rng(seed)`.
- Characterization tests (`test_characterization_*.py`) pin current
  behaviour of brownfield code before it is changed.
- Never weaken a test to make it pass. If a test is wrong, fix it in a
  separate, explained change.

## 4. Structure and change hygiene

- Put code next to related code; follow the existing package layout.
- Reuse existing helpers before writing new ones; if you find duplication,
  note it, don't silently refactor unrelated code.
- Keep diffs focused on the spec. Refactors that are needed go in their own
  commit with characterization tests protecting them.
- Public API changes are backwards compatible unless the spec says otherwise
  (deprecate first).

## 5. Repository-specific conventions

<!-- Filled in and kept current by /derive-standards. Examples:
- Returns are stored as decimals in `pd.DataFrame` (dates x assets).
- Config is read via `mypkg.config.settings`, never `os.environ` directly.
- Tests use the `prices_small` fixture from tests/conftest.py.
-->
