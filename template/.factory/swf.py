#!/usr/bin/env python3
"""swf - software factory gate CLI.

Deterministic checks that the Copilot agents must pass through. Agents may
argue with each other; they cannot argue with this script.

Usage (from the repository root):

    python .factory/swf.py new SPEC-ID --issue issues/SPEC-ID.md
    python .factory/swf.py baseline SPEC-ID
    python .factory/swf.py gate red SPEC-ID          # new tests fail, nothing else breaks
    python .factory/swf.py lock SPEC-ID              # freeze reviewed tests
    python .factory/swf.py gate green SPEC-ID --fast # inner coding loop
    python .factory/swf.py gate final SPEC-ID        # green + mutation + hold-out
    python .factory/swf.py round SPEC-ID tests       # exit 3 => escalate to human
    python .factory/swf.py holdout stash SPEC-ID
    python .factory/swf.py status [SPEC-ID]
    python .factory/swf.py changed SPEC-ID       # files changed since the spec started

Exit codes: 0 pass, 1 gate failed, 2 usage error, 3 escalate to human.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_ESCALATE = 3

SPEC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REQ_IN_SPEC_RE = re.compile(r"\bREQ-(\d+)\b")
REQ_IN_TEST_RE = re.compile(r"(?<![a-z])req[-_]?(\d+)", re.IGNORECASE)
PYTEST_SUMMARY_RE = re.compile(r"^(FAILED|ERROR) (.+?)(?: - .*)?$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
CHARACTERIZATION_MARK = "characterization"
PHASES = (
    "intake",
    "scout",
    "interview",
    "spec",
    "baseline",
    "tests",
    "holdout",
    "locked",
    "code",
    "final",
    "hardening",
    "done",
    "escalated",
)


# --------------------------------------------------------------------------- config


@dataclass
class Config:
    root: Path
    base_branch: str = "main"
    src_paths: list[str] = field(default_factory=lambda: ["src"])
    test_paths: list[str] = field(default_factory=lambda: ["tests"])
    specs_dir: str = "specs"
    holdout_root: str = "~/.factory-holdout"
    holdout_required: bool = False
    max_rounds: int = 4
    coverage_min: float = 90.0
    mutation_min: float = 70.0
    mutation_max_mutants: int = 200
    mutation_timeout_s: int = 120
    ruff: bool = True
    mypy: bool = True
    mypy_args: list[str] = field(default_factory=list)
    pytest_args: list[str] = field(default_factory=list)
    python: str = sys.executable

    @property
    def factory_dir(self) -> Path:
        return self.root / ".factory"

    @property
    def runs_dir(self) -> Path:
        return self.factory_dir / "runs"


def load_config(root: Path) -> Config:
    cfg = Config(root=root)
    path = root / ".factory" / "config.toml"
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    merged: dict[str, object] = {}
    for section in ("project", "loops", "gates", "holdout"):
        merged.update(data.get(section, {}))
    for key, value in merged.items():
        if not hasattr(cfg, key) or key == "root":
            raise SystemExit(f"Unknown config key in .factory/config.toml: {key}")
        setattr(cfg, key, value)
    return cfg


def find_root(start: Path | None = None) -> Path:
    proc = _run(["git", "rev-parse", "--show-toplevel"], cwd=start or Path.cwd())
    if proc.returncode != 0:
        raise SystemExit("swf must run inside a git repository")
    return Path(proc.stdout.strip())


# --------------------------------------------------------------------------- process


def _run(
    cmd: Sequence[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        list(cmd),
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass
class PytestResult:
    code: int
    failed: set[str]
    output: str
    timed_out: bool = False

    @property
    def collection_error(self) -> bool:
        return self.code == 2 or any(f.endswith(".py") for f in self.failed)


def run_pytest(
    cfg: Config,
    args: Sequence[str],
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> PytestResult:
    cmd = [cfg.python, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider"]
    cmd += [*cfg.pytest_args, *args]
    try:
        proc = _run(cmd, cfg.root, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return PytestResult(code=-1, failed=set(), output="timeout", timed_out=True)
    output = proc.stdout + proc.stderr
    failed = set()
    for line in output.splitlines():
        match = PYTEST_SUMMARY_RE.match(line.strip())
        if match:
            failed.add(match.group(2).strip())
    return PytestResult(code=proc.returncode, failed=failed, output=output)


# --------------------------------------------------------------------------- git


def _git(cfg: Config, *args: str) -> str:
    proc = _run(["git", "-c", "core.quotepath=off", *args], cfg.root)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def head_commit(cfg: Config) -> str:
    return _git(cfg, "rev-parse", "HEAD").strip()


def base_commit(cfg: Config, state: dict[str, object] | None) -> str:
    if state and state.get("base_commit"):
        return str(state["base_commit"])
    for ref in (cfg.base_branch, f"origin/{cfg.base_branch}"):
        proc = _run(["git", "merge-base", "HEAD", ref], cfg.root)
        if proc.returncode == 0:
            return proc.stdout.strip()
    return head_commit(cfg)


def untracked_files(cfg: Config) -> set[str]:
    out = _git(cfg, "ls-files", "--others", "--exclude-standard")
    return {line for line in out.splitlines() if line}


def changed_files(cfg: Config, base: str) -> list[str]:
    """Files added or modified since `base`, including uncommitted and untracked."""
    names = set(_git(cfg, "diff", "--name-only", base).splitlines())
    names |= untracked_files(cfg)
    return sorted(n for n in names if n and (cfg.root / n).is_file())


def parse_diff_lines(diff_text: str) -> set[int]:
    """Line numbers on the new side of a unified diff produced with -U0."""
    lines: set[int] = set()
    for line in diff_text.splitlines():
        match = HUNK_RE.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) is not None else 1
        lines.update(range(start, start + count))
    return lines


def changed_lines(cfg: Config, base: str, path: str, untracked: set[str]) -> set[int]:
    if path in untracked:
        text = (cfg.root / path).read_text(encoding="utf-8")
        return set(range(1, text.count("\n") + 2))
    return parse_diff_lines(_git(cfg, "diff", "-U0", base, "--", path))


# --------------------------------------------------------------------------- file classes


def _under(path: str, prefixes: Iterable[str]) -> bool:
    parts = Path(path).parts
    for prefix in prefixes:
        pre = Path(prefix).parts
        if pre == (".",) or parts[: len(pre)] == pre:
            return True
    return False


def is_test_file(cfg: Config, path: str) -> bool:
    if not path.endswith(".py"):
        return False
    name = Path(path).name
    looks_like_test = name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
    return looks_like_test or _under(path, cfg.test_paths)


def is_src_file(cfg: Config, path: str) -> bool:
    return (
        path.endswith(".py")
        and not is_test_file(cfg, path)
        and _under(path, cfg.src_paths)
        and not _under(path, [".factory", cfg.specs_dir])
    )


def is_characterization(path: str) -> bool:
    return CHARACTERIZATION_MARK in Path(path).name


# --------------------------------------------------------------------------- state


def spec_dir(cfg: Config, sid: str) -> Path:
    if not SPEC_ID_RE.match(sid):
        raise SystemExit(f"Invalid spec id: {sid!r}")
    return cfg.root / cfg.specs_dir / sid


def load_state(cfg: Config, sid: str) -> dict[str, object]:
    path = spec_dir(cfg, sid) / "state.json"
    if not path.exists():
        raise SystemExit(f"No spec {sid!r}; run: python .factory/swf.py new {sid}")
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


def save_state(cfg: Config, sid: str, state: dict[str, object]) -> None:
    path = spec_dir(cfg, sid) / "state.json"
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _history(state: dict[str, object], event: str) -> None:
    history = state.setdefault("history", [])
    assert isinstance(history, list)
    history.append(f"{_now()} {event}")


def log_gate(cfg: Config, sid: str, name: str, checks: list[Check]) -> None:
    path = spec_dir(cfg, sid) / "gate-log.md"
    verdict = "PASS" if all(c.ok for c in checks) else "FAIL"
    lines = [f"\n## {_now()} gate {name}: {verdict}\n"]
    lines += [f"- [{'x' if c.ok else ' '}] {c.name}: {c.detail}" for c in checks]
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- checks


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    extra: list[str] = field(default_factory=list)


def report(checks: list[Check]) -> int:
    for check in checks:
        print(f"[{'PASS' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
        for line in check.extra:
            print(f"        {line}")
    ok = all(c.ok for c in checks)
    print("\nGATE PASSED" if ok else "\nGATE FAILED")
    return EXIT_OK if ok else EXIT_FAIL


def _tail(text: str, n: int = 25) -> list[str]:
    return text.strip().splitlines()[-n:]


def spec_requirements(cfg: Config, sid: str) -> set[int]:
    spec = spec_dir(cfg, sid) / "spec.md"
    if not spec.exists():
        return set()
    return {int(m) for m in REQ_IN_SPEC_RE.findall(spec.read_text(encoding="utf-8"))}


def test_requirements(text: str) -> set[int]:
    return {int(m) for m in REQ_IN_TEST_RE.findall(text)}


def check_ruff(cfg: Config, files: list[str]) -> list[Check]:
    if not cfg.ruff or not files:
        return []
    checks = []
    for label, args in (("ruff lint", ["check"]), ("ruff format", ["format", "--check"])):
        proc = _run([cfg.python, "-m", "ruff", *args, *files], cfg.root)
        detail = "clean" if proc.returncode == 0 else "violations (fix them, do not suppress)"
        if "No module named" in proc.stderr:
            detail = "ruff not installed: pip install ruff"
        extra = [] if proc.returncode == 0 else _tail(proc.stdout + proc.stderr)
        checks.append(Check(label, proc.returncode == 0, detail, extra))
    return checks


def check_mypy(cfg: Config, files: list[str]) -> list[Check]:
    if not cfg.mypy or not files:
        return []
    proc = _run([cfg.python, "-m", "mypy", *cfg.mypy_args, *files], cfg.root)
    detail = "clean" if proc.returncode == 0 else "type errors"
    if "No module named" in proc.stderr:
        detail = "mypy not installed: pip install mypy"
    extra = [] if proc.returncode == 0 else _tail(proc.stdout + proc.stderr)
    return [Check("mypy", proc.returncode == 0, detail, extra)]


def _changed_tests(cfg: Config, state: dict[str, object]) -> tuple[list[str], list[str]]:
    base = base_commit(cfg, state)
    tests = [f for f in changed_files(cfg, base) if is_test_file(cfg, f)]
    char = [f for f in tests if is_characterization(f)]
    spec = [f for f in tests if not is_characterization(f) and Path(f).name != "conftest.py"]
    return spec, char


def _new_failures(cfg: Config, state: dict[str, object], result: PytestResult) -> set[str]:
    baseline = state.get("baseline_failures", [])
    assert isinstance(baseline, list)
    return result.failed - set(baseline)


# --------------------------------------------------------------------------- commands


def cmd_new(cfg: Config, args: argparse.Namespace) -> int:
    directory = spec_dir(cfg, args.spec_id)
    if (directory / "state.json").exists():
        print(f"Spec {args.spec_id} already exists; use `status` or `phase`.")
        return EXIT_USAGE
    (directory / "reviews").mkdir(parents=True, exist_ok=True)
    title = args.spec_id
    issue_text = ""
    if args.issue:
        issue_path = cfg.root / args.issue
        if not issue_path.exists():
            print(f"Issue file not found: {args.issue}")
            return EXIT_USAGE
        issue_text = issue_path.read_text(encoding="utf-8")
        heading = next((ln for ln in issue_text.splitlines() if ln.startswith("# ")), "")
        title = heading[2:].strip() or title
    template = cfg.factory_dir / "templates" / "spec.md"
    if template.exists() and not (directory / "spec.md").exists():
        text = template.read_text(encoding="utf-8")
        text = text.replace("{{SPEC_ID}}", args.spec_id).replace("{{TITLE}}", title)
        text = text.replace("{{ISSUE}}", args.issue or "n/a")
        (directory / "spec.md").write_text(text, encoding="utf-8")
    state: dict[str, object] = {
        "spec_id": args.spec_id,
        "title": title,
        "issue": args.issue,
        "phase": "intake",
        "base_commit": head_commit(cfg),
        "rounds": {},
        "history": [],
    }
    _history(state, "created")
    save_state(cfg, args.spec_id, state)
    print(f"Created {directory.relative_to(cfg.root)} (base {str(state['base_commit'])[:10]})")
    return EXIT_OK


def cmd_phase(cfg: Config, args: argparse.Namespace) -> int:
    state = load_state(cfg, args.spec_id)
    state["phase"] = args.phase
    _history(state, f"phase -> {args.phase}" + (f" ({args.note})" if args.note else ""))
    save_state(cfg, args.spec_id, state)
    print(f"{args.spec_id}: phase = {args.phase}")
    return EXIT_OK


def cmd_round(cfg: Config, args: argparse.Namespace) -> int:
    state = load_state(cfg, args.spec_id)
    rounds = state.setdefault("rounds", {})
    assert isinstance(rounds, dict)
    if args.reset:
        rounds[args.loop] = 0
        state["phase"] = args.loop if args.loop in PHASES else state["phase"]
        _history(state, f"round {args.loop} reset by human")
        save_state(cfg, args.spec_id, state)
        print(f"{args.loop}: rounds reset to 0/{cfg.max_rounds}")
        return EXIT_OK
    rounds[args.loop] = int(rounds.get(args.loop, 0)) + 1
    current = rounds[args.loop]
    _history(state, f"round {args.loop} #{current}")
    if current > cfg.max_rounds:
        state["phase"] = "escalated"
        _history(state, f"escalated: {args.loop} exceeded {cfg.max_rounds} rounds")
        save_state(cfg, args.spec_id, state)
        print(f"ESCALATE: loop '{args.loop}' exceeded {cfg.max_rounds} rounds. Ask the human.")
        return EXIT_ESCALATE
    save_state(cfg, args.spec_id, state)
    print(f"{args.loop}: round {current}/{cfg.max_rounds}")
    return EXIT_OK


def cmd_status(cfg: Config, args: argparse.Namespace) -> int:
    specs_root = cfg.root / cfg.specs_dir
    if not args.spec_id:
        found = sorted(specs_root.glob("*/state.json")) if specs_root.exists() else []
        if not found:
            print("No specs yet.")
        for path in found:
            st = json.loads(path.read_text(encoding="utf-8"))
            print(f"{st['spec_id']:<20} {st['phase']:<10} {st.get('title', '')}")
        return EXIT_OK
    state = load_state(cfg, args.spec_id)
    print(f"spec:      {state['spec_id']} - {state.get('title')}")
    print(f"phase:     {state['phase']}")
    print(f"base:      {str(state.get('base_commit'))[:10]}")
    print(f"rounds:    {state.get('rounds')} (max {cfg.max_rounds})")
    print(f"locked:    {len(state.get('lock', {}))} test files")  # type: ignore[arg-type]
    print(f"holdout:   {len(_holdout_files(cfg, args.spec_id))} files")
    print("history:")
    for item in list(state.get("history", []))[-10:]:  # type: ignore[call-overload]
        print(f"  {item}")
    return EXIT_OK


def cmd_changed(cfg: Config, args: argparse.Namespace) -> int:
    state = load_state(cfg, args.spec_id)
    base = base_commit(cfg, state)
    print(f"base: {base}  (git diff {base[:10]} -- <path>)")
    groups: dict[str, list[str]] = {"source": [], "tests": [], "other": []}
    for path in changed_files(cfg, base):
        if _under(path, [".factory", cfg.specs_dir]):
            continue
        if is_src_file(cfg, path):
            groups["source"].append(path)
        elif is_test_file(cfg, path):
            groups["tests"].append(path)
        else:
            groups["other"].append(path)
    for name, paths in groups.items():
        print(f"{name}:")
        for path in paths:
            print(f"  {path}")
    return EXIT_OK


def cmd_baseline(cfg: Config, args: argparse.Namespace) -> int:
    state = load_state(cfg, args.spec_id)
    result = run_pytest(cfg, ["--tb=no", *cfg.test_paths])
    state["baseline_failures"] = sorted(result.failed)
    _history(state, f"baseline: {len(result.failed)} pre-existing failures")
    save_state(cfg, args.spec_id, state)
    if result.code not in (0, 1, 5):
        print("WARNING: the test suite did not run cleanly:")
        print("\n".join(_tail(result.output)))
    print(f"Baseline recorded: {len(result.failed)} pre-existing failing/erroring tests.")
    for nodeid in sorted(result.failed):
        print(f"  {nodeid}")
    return EXIT_OK


def gate_red(cfg: Config, sid: str) -> list[Check]:
    state = load_state(cfg, sid)
    spec_tests, char_tests = _changed_tests(cfg, state)
    checks: list[Check] = []

    checks.append(
        Check("new spec tests exist", bool(spec_tests), ", ".join(spec_tests) or "none found")
    )
    if not spec_tests:
        return checks

    reqs = spec_requirements(cfg, sid)
    test_text = "\n".join((cfg.root / f).read_text(encoding="utf-8") for f in spec_tests)
    missing = sorted(reqs - test_requirements(test_text))
    checks.append(
        Check(
            "every REQ has a test",
            bool(reqs) and not missing,
            "spec.md has no REQ-n ids"
            if not reqs
            else (f"missing: {', '.join(f'REQ-{n:03d}' for n in missing)}" if missing else "ok"),
        )
    )

    if char_tests:
        res = run_pytest(cfg, ["--tb=short", *char_tests])
        checks.append(
            Check(
                "characterization tests pass on current code",
                res.code == 0,
                "ok" if res.code == 0 else "they must describe CURRENT behaviour",
                [] if res.code == 0 else _tail(res.output),
            )
        )

    res = run_pytest(cfg, ["--tb=line", *spec_tests])
    syntax_problem = "SyntaxError" in res.output or "IndentationError" in res.output
    is_red = res.code in (1, 2) and not syntax_problem
    if res.code == 0:
        detail = "all new tests already pass - they do not specify new behaviour"
    elif syntax_problem:
        detail = "tests are broken (syntax error), not red"
    elif res.collection_error:
        detail = "red via import/collection error (acceptable: symbol does not exist yet)"
    else:
        detail = f"{len(res.failed)} failing as expected"
    checks.append(Check("new tests are red", is_red, detail, [] if is_red else _tail(res.output)))

    ignores = [f"--ignore={f}" for f in spec_tests]
    res = run_pytest(cfg, ["--tb=line", *ignores, *cfg.test_paths])
    new_fail = _new_failures(cfg, state, res)
    checks.append(
        Check(
            "existing suite unaffected",
            not new_fail,
            "ok" if not new_fail else f"{len(new_fail)} new failures",
            sorted(new_fail),
        )
    )
    checks += check_ruff(cfg, spec_tests + char_tests)
    return checks


def cmd_lock(cfg: Config, args: argparse.Namespace) -> int:
    state = load_state(cfg, args.spec_id)
    spec_tests, char_tests = _changed_tests(cfg, state)
    base = base_commit(cfg, state)
    all_tests = [f for f in changed_files(cfg, base) if is_test_file(cfg, f)]
    if not spec_tests:
        print("Nothing to lock: no new spec tests.")
        return EXIT_FAIL
    state["lock"] = {f: _sha(cfg.root / f) for f in all_tests}
    state["phase"] = "locked"
    _history(state, f"locked {len(all_tests)} test files")
    save_state(cfg, args.spec_id, state)
    print(
        f"Locked {len(all_tests)} test files "
        f"(spec: {len(spec_tests)}, characterization: {len(char_tests)})."
    )
    return EXIT_OK


def cmd_unlock(cfg: Config, args: argparse.Namespace) -> int:
    state = load_state(cfg, args.spec_id)
    state.pop("lock", None)
    state["phase"] = "hardening"
    _history(state, f"unlocked: {args.reason}")
    save_state(cfg, args.spec_id, state)
    print("Unlocked. Only the test-writer may change tests now; re-run review and `lock`.")
    return EXIT_OK


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_lock(cfg: Config, state: dict[str, object]) -> Check:
    lock = state.get("lock")
    if not isinstance(lock, dict) or not lock:
        return Check("tests locked", False, "run review loop then `swf lock` first")
    base = base_commit(cfg, state)
    current = {f for f in changed_files(cfg, base) if is_test_file(cfg, f)}
    problems = []
    for path, digest in lock.items():
        file = cfg.root / path
        if not file.exists():
            problems.append(f"deleted: {path}")
        elif _sha(file) != digest:
            problems.append(f"modified: {path}")
    problems += [f"added after lock: {p}" for p in sorted(current - set(lock))]
    deleted_tracked = {
        line[2:]
        for line in _git(cfg, "diff", "--name-status", base).splitlines()
        if line.startswith("D") and is_test_file(cfg, line[2:].strip())
    }
    problems += [f"pre-existing test deleted: {p.strip()}" for p in sorted(deleted_tracked)]
    return Check(
        "locked tests untouched",
        not problems,
        "ok" if not problems else "the coder must not change tests",
        problems,
    )


def diff_coverage(
    cfg: Config, coverage_json: Path, files: dict[str, set[int]]
) -> tuple[float | None, list[str]]:
    data = json.loads(coverage_json.read_text(encoding="utf-8")) if coverage_json.exists() else {}
    by_path: dict[Path, dict[str, Any]] = {}
    for key, value in data.get("files", {}).items():
        path = Path(key)
        by_path[(path if path.is_absolute() else cfg.root / path).resolve()] = value
    covered = total = 0
    gaps: list[str] = []
    for rel, lines in files.items():
        info = by_path.get((cfg.root / rel).resolve())
        if info is None:
            source = (cfg.root / rel).read_text(encoding="utf-8").splitlines()
            code = [n for n in lines if n <= len(source) and _is_code(source[n - 1])]
            total += len(code)
            if code:
                gaps.append(f"{rel}: never imported by tests ({len(code)} changed lines)")
            continue
        executed: set[int] = set(info.get("executed_lines", []))
        missing: set[int] = set(info.get("missing_lines", []))
        hit_br = [(a, b) for a, b in info.get("executed_branches", []) if a in lines]
        miss_br = [(a, b) for a, b in info.get("missing_branches", []) if a in lines]
        file_cov = len(executed & lines) + len(hit_br)
        file_tot = len((executed | missing) & lines) + len(hit_br) + len(miss_br)
        covered += file_cov
        total += file_tot
        missed_lines = sorted(missing & lines)
        if missed_lines:
            gaps.append(f"{rel}: uncovered lines {_ranges(missed_lines)}")
        if miss_br:
            gaps.append(f"{rel}: uncovered branches {', '.join(f'{a}->{b}' for a, b in miss_br)}")
    if total == 0:
        return None, gaps
    return 100.0 * covered / total, gaps


def _is_code(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _ranges(nums: list[int]) -> str:
    out: list[str] = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        out.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = n
    out.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(out)


def gate_green(cfg: Config, sid: str, mutation: bool) -> list[Check]:
    state = load_state(cfg, sid)
    checks = [check_lock(cfg, state)]
    base = base_commit(cfg, state)
    untracked = untracked_files(cfg)
    changed = changed_files(cfg, base)
    src = [f for f in changed if is_src_file(cfg, f)]

    cfg.runs_dir.mkdir(parents=True, exist_ok=True)
    cov_json = cfg.runs_dir / f"coverage-{sid}.json"
    cov_json.unlink(missing_ok=True)
    cov_args = [f"--cov={p}" for p in cfg.src_paths]
    cov_args += ["--cov-branch", f"--cov-report=json:{cov_json}", "--cov-report="]
    res = run_pytest(cfg, ["--tb=short", *cov_args, *cfg.test_paths])
    if res.code == 4 and "--cov" in res.output:
        checks.append(Check("test suite", False, "pytest-cov missing: pip install pytest-cov"))
        return checks
    new_fail = _new_failures(cfg, state, res)
    lock = state.get("lock") or {}
    locked_failing = {f for f in res.failed if f.split("::")[0] in lock}  # type: ignore[operator]
    bad = new_fail | locked_failing
    checks.append(
        Check(
            "full test suite green",
            not bad and res.code in (0, 1),
            "ok" if not bad else f"{len(bad)} failing",
            sorted(bad) + ([] if not bad else ["--- output tail ---", *_tail(res.output, 40)]),
        )
    )

    lines = {f: changed_lines(cfg, base, f, untracked) for f in src}
    pct, gaps = diff_coverage(cfg, cov_json, lines)
    if pct is None:
        checks.append(Check("diff coverage", True, "no changed executable source lines", gaps))
    else:
        checks.append(
            Check(
                "diff coverage (lines+branches)",
                pct >= cfg.coverage_min,
                f"{pct:.1f}% (min {cfg.coverage_min:.0f}%)",
                gaps,
            )
        )

    py_changed = [f for f in changed if f.endswith(".py") and not _under(f, [".factory"])]
    checks += check_ruff(cfg, py_changed)
    checks += check_mypy(cfg, src)
    if mutation:
        checks.append(mutation_check(cfg, state, lines))
    return checks


def cmd_gate(cfg: Config, args: argparse.Namespace) -> int:
    sid = args.spec_id
    if args.kind == "red":
        checks = gate_red(cfg, sid)
    elif args.kind == "green":
        checks = gate_green(cfg, sid, mutation=not args.fast)
    elif args.kind == "mutation":
        state = load_state(cfg, sid)
        base = base_commit(cfg, state)
        untracked = untracked_files(cfg)
        src = [f for f in changed_files(cfg, base) if is_src_file(cfg, f)]
        lines = {f: changed_lines(cfg, base, f, untracked) for f in src}
        checks = [mutation_check(cfg, state, lines)]
    else:  # final
        checks = gate_green(cfg, sid, mutation=True)
        checks.append(holdout_check(cfg, sid))
    log_gate(cfg, sid, args.kind + (" --fast" if getattr(args, "fast", False) else ""), checks)
    return report(checks)


# --------------------------------------------------------------------------- mutation

CMP_SWAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}
BIN_SWAP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Div,
    ast.Mod: ast.FloorDiv,
    ast.Pow: ast.Mult,
}


@dataclass(frozen=True)
class Mutant:
    path: str
    node_index: int
    variant: int
    lineno: int
    description: str


def _mutations_for(node: ast.AST) -> list[tuple[str, Callable[[ast.AST], None]]]:
    """Possible mutations of a node, as (description, in-place mutator)."""
    out: list[tuple[str, Callable[[ast.AST], None]]] = []
    if isinstance(node, ast.Compare):
        for i, op in enumerate(node.ops):
            new = CMP_SWAP.get(type(op))
            if new is not None:

                def swap_cmp(n: ast.AST, i: int = i, new: type[ast.cmpop] = new) -> None:
                    assert isinstance(n, ast.Compare)
                    n.ops[i] = new()

                out.append((f"{type(op).__name__} -> {new.__name__}", swap_cmp))
    elif isinstance(node, ast.BinOp | ast.AugAssign):
        new_op = BIN_SWAP.get(type(node.op))
        if new_op is not None:

            def swap_bin(n: ast.AST, new: type[ast.operator] = new_op) -> None:
                n.op = new()  # type: ignore[attr-defined]

            out.append((f"{type(node.op).__name__} -> {new_op.__name__}", swap_bin))
    elif isinstance(node, ast.BoolOp):
        new_bool = ast.Or if isinstance(node.op, ast.And) else ast.And

        def swap_bool(n: ast.AST, new: type[ast.boolop] = new_bool) -> None:
            n.op = new()  # type: ignore[attr-defined]

        out.append((f"{type(node.op).__name__} -> {new_bool.__name__}", swap_bool))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not | ast.USub):

        def drop_unary(n: ast.AST) -> None:
            n.op = ast.UAdd()  # type: ignore[attr-defined]

        out.append((f"remove {type(node.op).__name__}", drop_unary))
    elif isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool):

            def flip(n: ast.AST) -> None:
                n.value = not n.value  # type: ignore[attr-defined]

            out.append((f"{value} -> {not value}", flip))
        elif isinstance(value, int | float):

            def bump(n: ast.AST) -> None:
                n.value = n.value + 1  # type: ignore[attr-defined]

            out.append((f"{value!r} -> {value + 1!r}", bump))
    elif isinstance(node, ast.If | ast.While | ast.IfExp):

        def negate(n: ast.AST) -> None:
            n.test = ast.UnaryOp(op=ast.Not(), operand=n.test)  # type: ignore[attr-defined]

        out.append(("negate condition", negate))
    elif isinstance(node, ast.Return) and not _returns_none(node):

        def return_none(n: ast.AST) -> None:
            n.value = ast.Constant(value=None)  # type: ignore[attr-defined]

        out.append(("return None", return_none))
    return out


def _returns_none(node: ast.Return) -> bool:
    return node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None)


def _skip_nodes(tree: ast.AST) -> set[int]:
    """ids of nodes that must not be mutated: docstrings and annotations."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        annotations: list[ast.AST | None] = []
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            annotations.append(node.returns)
            all_args = node.args.args + node.args.kwonlyargs + node.args.posonlyargs
            annotations += [a.annotation for a in all_args]
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        for ann in annotations:
            if ann is not None:
                skip.update(id(n) for n in ast.walk(ann))
        body = getattr(node, "body", None)
        first = body[0] if isinstance(body, list) and body else None
        docstring = first.value if isinstance(first, ast.Expr) else None
        if isinstance(docstring, ast.Constant) and isinstance(docstring.value, str):
            skip.add(id(docstring))
    return skip


def find_mutants(path: str, source: str, lines: set[int]) -> list[Mutant]:
    tree = ast.parse(source)
    skip = _skip_nodes(tree)
    mutants = []
    for index, node in enumerate(ast.walk(tree)):
        lineno = getattr(node, "lineno", None)
        if lineno is None or lineno not in lines or id(node) in skip:
            continue
        for variant, (desc, _) in enumerate(_mutations_for(node)):
            mutants.append(Mutant(path, index, variant, lineno, desc))
    return mutants


def apply_mutant(source: str, mutant: Mutant) -> str:
    tree = ast.parse(source)
    node = list(ast.walk(tree))[mutant.node_index]
    _, mutate = _mutations_for(node)[mutant.variant]
    mutate(node)
    return ast.unparse(ast.fix_missing_locations(tree))


def _backup_dir(cfg: Config) -> Path:
    return cfg.runs_dir / "mutation-backup"


def restore_backups(cfg: Config) -> list[str]:
    restored: list[str] = []
    backup_root = _backup_dir(cfg)
    if not backup_root.exists():
        return restored
    for backup in backup_root.rglob("*.py"):
        rel = backup.relative_to(backup_root)
        shutil.copy2(backup, cfg.root / rel)
        restored.append(str(rel))
    shutil.rmtree(backup_root)
    return restored


def run_mutation(
    cfg: Config, lines_by_file: dict[str, set[int]], test_targets: list[str]
) -> tuple[int, int, list[Mutant], str]:
    """Returns (killed, total, survivors, note)."""
    if _backup_dir(cfg).exists():
        raise SystemExit("Stale mutation backups found; run `swf mutation-restore` first.")
    mutants: list[Mutant] = []
    sources: dict[str, str] = {}
    for path, lines in lines_by_file.items():
        sources[path] = (cfg.root / path).read_text(encoding="utf-8")
        mutants += find_mutants(path, sources[path], lines)
    note = ""
    if len(mutants) > cfg.mutation_max_mutants:
        note = f"sampled {cfg.mutation_max_mutants} of {len(mutants)} mutants"
        mutants = sorted(
            random.Random(0).sample(mutants, cfg.mutation_max_mutants),
            key=lambda m: (m.path, m.lineno, m.node_index, m.variant),
        )
    if not mutants:
        return 0, 0, [], "no mutable changed lines"

    args = ["-x", "--tb=no", "-q", *test_targets]
    started = time.monotonic()
    clean = run_pytest(cfg, args, timeout=cfg.mutation_timeout_s * 5)
    duration = time.monotonic() - started
    if clean.code != 0:
        raise SystemExit("Mutation testing needs a green suite first:\n" + clean.output[-2000:])
    timeout = min(float(cfg.mutation_timeout_s), max(10.0, 3 * duration))

    killed = 0
    survivors: list[Mutant] = []
    backup_root = _backup_dir(cfg)
    for mutant in mutants:
        target = cfg.root / mutant.path
        backup = backup_root / mutant.path
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        try:
            target.write_text(apply_mutant(sources[mutant.path], mutant), encoding="utf-8")
            with tempfile.TemporaryDirectory() as pycache:
                env = {"PYTHONPYCACHEPREFIX": pycache, "PYTHONDONTWRITEBYTECODE": "1"}
                res = run_pytest(cfg, args, env=env, timeout=timeout)
        finally:
            shutil.copy2(backup, target)
            backup.unlink()
        if res.timed_out or res.code != 0:
            killed += 1
        else:
            survivors.append(mutant)
    shutil.rmtree(backup_root, ignore_errors=True)
    return killed, len(mutants), survivors, note


def mutation_check(cfg: Config, state: dict[str, object], lines: dict[str, set[int]]) -> Check:
    lock = state.get("lock")
    if isinstance(lock, dict) and lock:
        targets = sorted(lock)
    else:
        spec_tests, char_tests = _changed_tests(cfg, state)
        targets = spec_tests + char_tests or list(cfg.test_paths)
    killed, total, survivors, note = run_mutation(cfg, lines, targets)
    if total == 0:
        return Check("mutation score", True, note)
    score = 100.0 * killed / total
    extra = [f"SURVIVED {m.path}:{m.lineno} {m.description}" for m in survivors]
    detail = f"{score:.1f}% ({killed}/{total} killed, min {cfg.mutation_min:.0f}%)"
    if note:
        detail += f"; {note}"
    return Check("mutation score", score >= cfg.mutation_min, detail, extra)


def cmd_mutation_restore(cfg: Config, args: argparse.Namespace) -> int:
    restored = restore_backups(cfg)
    print("Restored: " + (", ".join(restored) if restored else "nothing to restore"))
    return EXIT_OK


# --------------------------------------------------------------------------- hold-out


def holdout_dir(cfg: Config, sid: str) -> Path:
    return Path(cfg.holdout_root).expanduser() / cfg.root.name / sid


def _holdout_files(cfg: Config, sid: str) -> list[Path]:
    directory = holdout_dir(cfg, sid)
    return sorted(directory.glob("*.py")) if directory.exists() else []


def cmd_holdout(cfg: Config, args: argparse.Namespace) -> int:
    sid = args.spec_id
    if args.action == "stash":
        staging = cfg.factory_dir / "holdout-staging" / sid
        files = sorted(staging.glob("*.py")) if staging.exists() else []
        if not files:
            print(f"No files in {staging.relative_to(cfg.root)}")
            return EXIT_FAIL
        target = holdout_dir(cfg, sid)
        target.mkdir(parents=True, exist_ok=True)
        reqs: set[int] = set()
        for file in files:
            reqs |= test_requirements(file.read_text(encoding="utf-8"))
            shutil.move(str(file), target / file.name)
        shutil.rmtree(staging)
        state = load_state(cfg, sid)
        _history(state, f"holdout stashed: {len(files)} files")
        save_state(cfg, sid, state)
        covered = ", ".join(f"REQ-{n:03d}" for n in sorted(reqs)) or "none"
        print(f"Stashed {len(files)} hold-out files outside the workspace. Covers: {covered}")
        return EXIT_OK
    check = holdout_check(cfg, sid)
    log_gate(cfg, sid, "holdout", [check])
    return report([check])


def holdout_check(cfg: Config, sid: str) -> Check:
    files = _holdout_files(cfg, sid)
    if not files:
        return Check("hold-out tests", not cfg.holdout_required, "none present")
    paths = [str(cfg.root / p) for p in cfg.src_paths] + [str(cfg.root)]
    pythonpath = os.pathsep.join([*paths, os.environ.get("PYTHONPATH", "")])
    args = ["--tb=no", f"--rootdir={cfg.root}", *map(str, files)]
    res = run_pytest(cfg, args, env={"PYTHONPATH": pythonpath})
    if res.code not in (0, 1):
        # Collection/usage problems: say so without leaking the test source.
        return Check("hold-out tests", False, f"could not run (pytest exit {res.code})")
    per_req: dict[str, int] = {}
    for nodeid in res.failed:
        name = nodeid.split("::")[-1]
        ids = test_requirements(name) or {0}
        for n in ids:
            key = f"REQ-{n:03d}" if n else "unlabelled"
            per_req[key] = per_req.get(key, 0) + 1
    # Only requirement-level counts are reported, never test names or tracebacks,
    # so the coder cannot overfit to the hidden tests.
    extra = [f"{req}: {count} hidden check(s) failed" for req, count in sorted(per_req.items())]
    detail = "all passed" if not per_req else f"{len(res.failed)} hidden checks failed"
    return Check("hold-out tests", not per_req, detail, extra)


# --------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="swf", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="create specs/<id>/ from an issue file")
    p.add_argument("spec_id")
    p.add_argument("--issue", help="path to issues/<id>.md")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("phase", help="record the current phase")
    p.add_argument("spec_id")
    p.add_argument("phase", choices=PHASES)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_phase)

    p = sub.add_parser("round", help="count a loop iteration; exit 3 = escalate")
    p.add_argument("spec_id")
    p.add_argument("loop", choices=("spec", "tests", "code", "holdout", "hardening"))
    p.add_argument("--reset", action="store_true", help="human override after escalation")
    p.set_defaults(func=cmd_round)

    p = sub.add_parser("status", help="show spec state (or list all specs)")
    p.add_argument("spec_id", nargs="?")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("changed", help="list files changed since the spec's base commit")
    p.add_argument("spec_id")
    p.set_defaults(func=cmd_changed)

    p = sub.add_parser("baseline", help="record pre-existing test failures")
    p.add_argument("spec_id")
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("gate", help="run a quality gate")
    p.add_argument("kind", choices=("red", "green", "mutation", "final"))
    p.add_argument("spec_id")
    p.add_argument("--fast", action="store_true", help="green without mutation testing")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("lock", help="freeze reviewed tests (coder may not change them)")
    p.add_argument("spec_id")
    p.set_defaults(func=cmd_lock)

    p = sub.add_parser("unlock", help="re-open tests for hardening")
    p.add_argument("spec_id")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_unlock)

    p = sub.add_parser("holdout", help="stash or run hidden acceptance tests")
    p.add_argument("action", choices=("stash", "run"))
    p.add_argument("spec_id")
    p.set_defaults(func=cmd_holdout)

    p = sub.add_parser("mutation-restore", help="restore sources after an interrupted mutation run")
    p.set_defaults(func=cmd_mutation_restore)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(find_root())
    result: int = args.func(cfg, args)
    return result


if __name__ == "__main__":
    sys.exit(main())
