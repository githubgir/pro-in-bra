---
applyTo: "**/test_*.py,**/*_test.py,**/conftest.py"
---

# Tests

Follow [docs/coding-standards.md](../../docs/coding-standards.md), section 3.

- Spec tests contain the requirement id in their name: `test_req_003_<behaviour>`.
- Characterization tests live in files named `test_characterization_*.py` and
  must pass on the current code.
- Arrange / Act / Assert, one behaviour per test, `pytest.mark.parametrize` for tables.
- Floats: `pytest.approx` / `np.testing.assert_allclose` /
  `pd.testing.assert_frame_equal` with deliberate tolerances.
- Deterministic: `np.random.default_rng(seed)`, no network, no clock, no order dependence.
- No vacuous assertions (`is not None` alone, `assert True`).
- Locked tests (after `swf lock`) are never changed by the coder.
