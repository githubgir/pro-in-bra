"""End-to-end: the factory flow on a small brownfield repo."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conftest import Runner

SPEC = """\
# Q-1: Log returns

| ID | Requirement | Acceptance |
|----|-------------|------------|
| REQ-001 | log_return(p0, p1) = ln(p1/p0) | Given 100, 110 then 0.09531 |
| REQ-002 | non-positive prices raise ValueError | Given 0, 1 then ValueError |
"""

SPEC_TESTS = """\
import math

import pytest

from quant.returns import log_return


def test_req_001_log_return_matches_definition() -> None:
    assert log_return(100.0, 110.0) == pytest.approx(math.log(1.1))


def test_req_001_flat_price_is_zero() -> None:
    assert log_return(50.0, 50.0) == 0.0


@pytest.mark.parametrize(("p0", "p1"), [(0.0, 1.0), (1.0, 0.0), (-1.0, 2.0)])
def test_req_002_non_positive_prices_raise(p0: float, p1: float) -> None:
    with pytest.raises(ValueError, match="positive"):
        log_return(p0, p1)
"""

IMPLEMENTATION = '''

def log_return(p0: float, p1: float) -> float:
    """Natural log return between two prices."""
    if p0 <= 0 or p1 <= 0:
        raise ValueError("prices must be positive")
    return math.log(p1 / p0)
'''

HOLDOUT = """\
import pytest

from quant.returns import log_return


def test_req_001_additivity() -> None:
    assert log_return(1.0, 2.0) + log_return(2.0, 4.0) == pytest.approx(log_return(1.0, 4.0))


def test_req_002_tiny_positive_ok() -> None:
    assert log_return(1e-300, 1e-300) == 0.0
"""


def _start(run: Runner, root: Path) -> None:
    assert run("new", "Q-1", "--issue", "issues/Q-1.md").returncode == 0
    (root / "specs" / "Q-1" / "spec.md").write_text(SPEC)
    assert run("baseline", "Q-1").returncode == 0


def _implement(root: Path) -> None:
    path = root / "src" / "quant" / "returns.py"
    text = path.read_text().replace('"""\n\n\ndef', '"""\n\nimport math\n\n\ndef', 1)
    path.write_text(text + IMPLEMENTATION)


def _state(root: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads((root / "specs" / "Q-1" / "state.json").read_text())
    return data


def test_new_creates_spec_from_issue(run: Runner, brownfield: Path) -> None:
    result = run("new", "Q-1", "--issue", "issues/Q-1.md")
    assert result.returncode == 0, result.stdout
    spec = (brownfield / "specs" / "Q-1" / "spec.md").read_text()
    assert spec.startswith("# Q-1: Log returns")
    assert _state(brownfield)["phase"] == "intake"
    assert run("new", "Q-1").returncode == 2


def test_red_gate_requires_failing_tests_for_every_req(run: Runner, brownfield: Path) -> None:
    _start(run, brownfield)
    assert run("gate", "red", "Q-1").returncode == 1  # no tests yet

    only_req1 = SPEC_TESTS.split("@pytest.mark")[0]
    (brownfield / "tests" / "test_log_returns.py").write_text(only_req1)
    result = run("gate", "red", "Q-1")
    assert result.returncode == 1
    assert "missing: REQ-002" in result.stdout

    (brownfield / "tests" / "test_log_returns.py").write_text(SPEC_TESTS)
    result = run("gate", "red", "Q-1")
    assert result.returncode == 0, result.stdout
    assert "red via import/collection error" in result.stdout


def test_red_gate_rejects_tests_that_already_pass(run: Runner, brownfield: Path) -> None:
    _start(run, brownfield)
    (brownfield / "specs" / "Q-1" / "spec.md").write_text("REQ-001 simple return")
    (brownfield / "tests" / "test_more.py").write_text(
        "from quant.returns import simple_return\n\n\n"
        "def test_req_001() -> None:\n    assert simple_return(1.0, 1.0) == 0.0\n"
    )
    result = run("gate", "red", "Q-1")
    assert result.returncode == 1
    assert "already pass" in result.stdout


def test_characterization_tests_must_pass_on_current_code(run: Runner, brownfield: Path) -> None:
    _start(run, brownfield)
    (brownfield / "tests" / "test_log_returns.py").write_text(SPEC_TESTS)
    (brownfield / "tests" / "test_characterization_returns.py").write_text(
        "from quant.returns import simple_return\n\n\n"
        "def test_simple_return_current_behaviour() -> None:\n"
        "    assert simple_return(1.0, 1.0) == 1.0\n"
    )
    result = run("gate", "red", "Q-1")
    assert result.returncode == 1
    assert "[FAIL] characterization tests pass on current code" in result.stdout


def test_full_flow_green_mutation_and_holdout(
    run: Runner, brownfield: Path, tmp_path: Path
) -> None:
    _start(run, brownfield)
    (brownfield / "tests" / "test_log_returns.py").write_text(SPEC_TESTS)
    assert run("gate", "red", "Q-1").returncode == 0
    assert run("gate", "green", "Q-1", "--fast").returncode == 1  # not locked yet

    staging = brownfield / ".factory" / "holdout-staging" / "Q-1"
    staging.mkdir(parents=True)
    (staging / "test_holdout_q1.py").write_text(HOLDOUT)
    stash = run("holdout", "stash", "Q-1")
    assert stash.returncode == 0, stash.stdout
    assert "REQ-001, REQ-002" in stash.stdout
    assert not staging.exists()
    assert (tmp_path / "holdout" / "brownfield" / "Q-1" / "test_holdout_q1.py").exists()

    assert run("lock", "Q-1").returncode == 0
    _implement(brownfield)

    changed = run("changed", "Q-1").stdout
    assert "source:\n  src/quant/returns.py\ntests:\n  tests/test_log_returns.py" in changed

    fast = run("gate", "green", "Q-1", "--fast")
    assert fast.returncode == 0, fast.stdout
    assert "diff coverage (lines+branches): 100.0%" in fast.stdout

    final = run("gate", "final", "Q-1")
    assert final.returncode == 0, final.stdout
    assert "[PASS] mutation score" in final.stdout
    assert "[PASS] hold-out tests: all passed" in final.stdout
    assert "gate final: PASS" in (brownfield / "specs" / "Q-1" / "gate-log.md").read_text()


def test_green_gate_detects_tampering_with_locked_tests(run: Runner, brownfield: Path) -> None:
    _start(run, brownfield)
    test_file = brownfield / "tests" / "test_log_returns.py"
    test_file.write_text(SPEC_TESTS)
    assert run("lock", "Q-1").returncode == 0
    _implement(brownfield)

    test_file.write_text(SPEC_TESTS.replace("math.log(1.1)", "0.0953"))
    result = run("gate", "green", "Q-1", "--fast")
    assert result.returncode == 1
    assert "modified: tests/test_log_returns.py" in result.stdout

    test_file.write_text(SPEC_TESTS)
    (brownfield / "tests" / "conftest.py").write_text("")
    result = run("gate", "green", "Q-1", "--fast")
    assert "added after lock: tests/conftest.py" in result.stdout


def test_weak_tests_fail_mutation_and_coverage(run: Runner, brownfield: Path) -> None:
    _start(run, brownfield)
    weak = (
        "from quant.returns import log_return\n\n\n"
        "def test_req_001_runs() -> None:\n    assert log_return(1.0, 2.0) is not None\n\n\n"
        "def test_req_002_placeholder() -> None:\n    assert log_return(2.0, 2.0) == 0.0\n"
    )
    (brownfield / "tests" / "test_log_returns.py").write_text(weak)
    assert run("lock", "Q-1").returncode == 0
    _implement(brownfield)
    result = run("gate", "final", "Q-1")
    assert result.returncode == 1
    assert "[FAIL] mutation score" in result.stdout
    assert "SURVIVED src/quant/returns.py" in result.stdout
    assert "[FAIL] diff coverage" in result.stdout
    assert "uncovered lines" in result.stdout


def test_holdout_failures_reported_per_requirement_only(
    run: Runner, brownfield: Path, tmp_path: Path
) -> None:
    _start(run, brownfield)
    hidden = tmp_path / "holdout" / "brownfield" / "Q-1"
    hidden.mkdir(parents=True)
    (hidden / "test_hidden.py").write_text(
        "from quant.returns import simple_return\n\n\n"
        "def test_req_007_secret_edge_case() -> None:\n"
        "    assert simple_return(1.0, 1.0) == 42  # SECRET\n"
    )
    result = run("holdout", "run", "Q-1")
    assert result.returncode == 1
    assert "REQ-007: 1 hidden check(s) failed" in result.stdout
    assert "secret_edge_case" not in result.stdout
    assert "SECRET" not in result.stdout


def test_round_escalates_after_max(run: Runner, brownfield: Path) -> None:
    _start(run, brownfield)
    for _ in range(4):
        assert run("round", "Q-1", "tests").returncode == 0
    result = run("round", "Q-1", "tests")
    assert result.returncode == 3
    assert "ESCALATE" in result.stdout
    assert _state(brownfield)["phase"] == "escalated"

    assert run("round", "Q-1", "tests", "--reset").returncode == 0
    assert _state(brownfield)["phase"] == "tests"
    assert run("round", "Q-1", "tests").returncode == 0


def test_baseline_failures_are_tolerated(run: Runner, brownfield: Path) -> None:
    legacy = "def test_legacy() -> None:\n    assert False\n"
    (brownfield / "tests" / "test_broken_legacy.py").write_text(legacy)
    subprocess.run(["git", "add", "."], cwd=brownfield, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "legacy"],
        cwd=brownfield,
        check=True,
    )
    _start(run, brownfield)
    assert _state(brownfield)["baseline_failures"] == ["tests/test_broken_legacy.py::test_legacy"]
    (brownfield / "tests" / "test_log_returns.py").write_text(SPEC_TESTS)
    result = run("gate", "red", "Q-1")
    assert "[PASS] existing suite unaffected" in result.stdout
