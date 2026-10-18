#!/usr/bin/env python3
"""Install the Copilot software factory into an existing repository.

    python install.py /path/to/brownfield-repo [--dry-run] [--force]
                      [--src src] [--tests tests] [--base main]

Copies `template/` into the target. Existing files are never overwritten
unless --force is given, except for two files that are merged:
`.github/copilot-instructions.md` (factory block appended once) and
`.gitignore` (factory entries appended once).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template"
MERGED = {".github/copilot-instructions.md"}
SKIP = {".factory/gitignore.snippet"}
BLOCK_START = "<!-- software-factory:start -->"
BLOCK_END = "<!-- software-factory:end -->"


def detect_src_paths(target: Path) -> list[str]:
    if (target / "src").is_dir():
        return ["src"]
    packages = sorted(
        p.name
        for p in target.iterdir()
        if p.is_dir() and (p / "__init__.py").exists() and p.name not in {"tests", "test", "docs"}
    )
    return packages or ["."]


def detect_test_paths(target: Path) -> list[str]:
    for name in ("tests", "test"):
        if (target / name).is_dir():
            return [name]
    return ["tests"]


def detect_base_branch(target: Path) -> str:
    for cmd in (
        ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        ["git", "branch", "--show-current"],
    ):
        proc = subprocess.run(cmd, cwd=target, capture_output=True, text=True, check=False)
        name = proc.stdout.strip()
        if proc.returncode == 0 and name:
            return name.removeprefix("origin/")
    return "main"


def configure(text: str, src: list[str], tests: list[str], base: str) -> str:
    text = re.sub(r"(?m)^base_branch = .*$", f"base_branch = {json.dumps(base)}", text)
    text = re.sub(r"(?m)^src_paths = \[[^\]]*\]", f"src_paths = {json.dumps(src)}", text)
    return re.sub(r"(?m)^test_paths = \[[^\]]*\]", f"test_paths = {json.dumps(tests)}", text)


def merge_instructions(existing: str, factory: str) -> str | None:
    if BLOCK_START in existing:
        return None
    body = factory.split("\n", 1)[1].lstrip()  # drop the template's own H1
    block = f"{BLOCK_START}\n## Software factory\n\n{body.rstrip()}\n{BLOCK_END}\n"
    return existing.rstrip() + "\n\n" + block


def merge_gitignore(existing: str, snippet: str) -> str | None:
    present = {line.strip() for line in existing.splitlines()}
    missing = [ln for ln in snippet.splitlines() if ln.strip() and ln.strip() not in present]
    entries = [ln for ln in missing if not ln.startswith("#")]
    if not entries:
        return None
    return existing.rstrip() + ("\n\n" if existing.strip() else "") + "\n".join(missing) + "\n"


def install(
    target: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    src: list[str] | None = None,
    tests: list[str] | None = None,
    base: str | None = None,
) -> list[str]:
    """Copy the template into `target`. Returns a log of actions."""
    log: list[str] = []
    src = src or detect_src_paths(target)
    tests = tests or detect_test_paths(target)
    base = base or detect_base_branch(target)

    def write(path: Path, text: str, action: str) -> None:
        log.append(f"{action:<9} {path.relative_to(target)}")
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    for source in sorted(TEMPLATE.rglob("*")):
        if source.is_dir() or "__pycache__" in source.parts:
            continue
        rel = source.relative_to(TEMPLATE).as_posix()
        if rel in SKIP:
            continue
        dest = target / rel
        text = source.read_text(encoding="utf-8")
        if rel == ".factory/config.toml":
            text = configure(text, src, tests, base)
        if dest.exists() and rel in MERGED:
            merged = merge_instructions(dest.read_text(encoding="utf-8"), text)
            if merged is None:
                log.append(f"{'unchanged':<9} {rel}")
            else:
                write(dest, merged, "merged")
            continue
        if dest.exists() and not force:
            log.append(f"{'kept':<9} {rel} (exists; use --force to overwrite)")
            continue
        write(dest, text, "overwrote" if dest.exists() else "created")
        if rel == ".factory/swf.py" and not dry_run:
            dest.chmod(0o755)

    gitignore = target / ".gitignore"
    snippet = (TEMPLATE / ".factory" / "gitignore.snippet").read_text(encoding="utf-8")
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    merged_ignore = merge_gitignore(current, snippet)
    if merged_ignore is not None:
        write(gitignore, merged_ignore, "merged" if current else "created")

    log.append(f"config    src_paths={src} test_paths={tests} base_branch={base!r}")
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("target", type=Path)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--src", nargs="+", help="production code paths (auto-detected)")
    parser.add_argument("--tests", nargs="+", help="test paths (auto-detected)")
    parser.add_argument("--base", help="base branch (auto-detected)")
    args = parser.parse_args(argv)

    target: Path = args.target.resolve()
    if not (target / ".git").exists():
        print(f"{target} is not a git repository root.", file=sys.stderr)
        return 2
    log = install(
        target,
        force=args.force,
        dry_run=args.dry_run,
        src=args.src,
        tests=args.tests,
        base=args.base,
    )
    print("\n".join(log))
    if args.dry_run:
        print("\nDry run: nothing written.")
        return 0
    print("\nNext steps:")
    print("  1. pip install pytest pytest-cov ruff mypy   (in the repo's environment)")
    print("  2. Review .factory/config.toml")
    print("  3. In VS Code Copilot Chat: /derive-standards, then /factory-start issues/<ID>.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
