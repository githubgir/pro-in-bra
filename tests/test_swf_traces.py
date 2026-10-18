"""Per agent x iteration trace files."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import Runner

TASK = "Spec Q-1, round 1. Make `swf gate green Q-1 --fast` pass.\n```python\nx = 1\n```"


def _new(run: Runner) -> None:
    assert run("new", "Q-1", "--issue", "issues/Q-1.md").returncode == 0


def test_trace_lifecycle_records_input_output_and_index(run: Runner, brownfield: Path) -> None:
    _new(run)
    assert run("round", "Q-1", "code").returncode == 0
    assert run("round", "Q-1", "code").returncode == 0

    started = run("trace", "start", "Q-1", "factory-coder", stdin=TASK)
    assert started.returncode == 0, started.stderr
    assert started.stdout.strip() == "trace 1: specs/Q-1/traces/001-coder-r2.md"
    path = brownfield / "specs" / "Q-1" / "traces" / "001-coder-r2.md"
    body = path.read_text()
    assert "- Loop / round: code / 2" in body
    assert "````text\n" + TASK + "\n````" in body  # fence longer than the inner one
    assert "## Reasoning and decisions" in body

    assert (
        run(
            "trace", "append", "Q-1", "1", "--heading", "Gate: green --fast", stdin="GATE PASSED"
        ).returncode
        == 0
    )
    assert (
        run(
            "trace", "finish", "Q-1", "1", "--status", "DONE", stdin="RESULT\nstatus: DONE"
        ).returncode
        == 0
    )
    body = path.read_text()
    assert body.index("## Output") < body.index("## Gate: green --fast")
    assert "RESULT\nstatus: DONE" in body
    assert body.count("- Status: DONE") == 2 and "- Status: running" not in body

    index = (brownfield / "specs" / "Q-1" / "traces" / "index.md").read_text()
    assert "| 001 | factory-coder | code | 2 | DONE |" in index
    assert "[001-coder-r2.md](001-coder-r2.md)" in index


def test_each_invocation_gets_its_own_file(run: Runner, brownfield: Path) -> None:
    _new(run)
    for agent in ("factory-test-writer", "factory-test-reviewer", "factory-test-writer"):
        assert run("trace", "start", "Q-1", agent, stdin="task").returncode == 0
    names = sorted(p.name for p in (brownfield / "specs" / "Q-1" / "traces").glob("0*.md"))
    assert names == ["001-test-writer-r1.md", "002-test-reviewer-r1.md", "003-test-writer-r1.md"]
    hardening = run(
        "trace",
        "start",
        "Q-1",
        "factory-test-writer",
        "--loop",
        "hardening",
        "--round",
        "2",
        stdin="t",
    )
    assert "004-test-writer-r2.md" in hardening.stdout


def test_orchestrator_journal(run: Runner, brownfield: Path) -> None:
    _new(run)
    run("trace", "log", "Q-1", "--heading", "Interview Q3", stdin="Q: NaN policy?\nA: propagate")
    journal = (brownfield / "specs" / "Q-1" / "traces" / "orchestrator.md").read_text()
    assert "Interview Q3" in journal and "A: propagate" in journal
    assert (brownfield / "specs" / "Q-1" / "traces" / "index.md").exists()


def test_holdout_writer_trace_leaves_the_workspace(
    run: Runner, brownfield: Path, tmp_path: Path
) -> None:
    _new(run)
    started = run("trace", "start", "Q-1", "factory-holdout-writer", stdin="spec only")
    assert ".factory/holdout-staging/Q-1/001-holdout-writer-r1.md" in started.stdout
    staging = brownfield / ".factory" / "holdout-staging" / "Q-1"
    (staging / "test_hidden.py").write_text("def test_req_001_x() -> None:\n    pass\n")
    assert run("holdout", "stash", "Q-1").returncode == 0
    assert run("trace", "finish", "Q-1", "1", "--status", "DONE", stdin="ok").returncode == 0

    hidden = tmp_path / "holdout" / "brownfield" / "Q-1" / "traces" / "001-holdout-writer-r1.md"
    assert "- Status: DONE" in hidden.read_text()
    assert not list((brownfield / "specs").rglob("*holdout-writer*"))
    index = (brownfield / "specs" / "Q-1" / "traces" / "index.md").read_text()
    assert "hidden (outside workspace)" in index
    state = json.loads((brownfield / "specs" / "Q-1" / "state.json").read_text())
    assert state["traces"][0]["path"] == str(hidden)


def test_unknown_trace_seq_fails(run: Runner, brownfield: Path) -> None:
    _new(run)
    result = run("trace", "finish", "Q-1", "9", "--status", "DONE", stdin="x")
    assert result.returncode != 0
    assert "No trace #9" in result.stderr
