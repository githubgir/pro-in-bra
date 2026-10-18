from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import install  # noqa: E402


@pytest.fixture
def target(tmp_path: Path) -> Path:
    root = tmp_path / "legacy"
    (root / "alpha").mkdir(parents=True)
    (root / "alpha" / "__init__.py").write_text("")
    (root / "test").mkdir()
    (root / ".github").mkdir()
    (root / ".github" / "copilot-instructions.md").write_text("# House rules\n\nUse tabs.\n")
    (root / ".gitignore").write_text("*.pyc\n")
    subprocess.run(["git", "init", "-q", "-b", "develop"], cwd=root, check=True)
    return root


def test_install_detects_layout_and_merges(target: Path) -> None:
    log = install.install(target)
    config = (target / ".factory" / "config.toml").read_text()
    assert 'src_paths = ["alpha"]' in config
    assert 'test_paths = ["test"]' in config
    assert 'base_branch = "develop"' in config
    assert (target / ".github" / "agents" / "factory-orchestrator.agent.md").exists()
    assert not (target / ".factory" / "gitignore.snippet").exists()

    instructions = (target / ".github" / "copilot-instructions.md").read_text()
    assert instructions.startswith("# House rules\n\nUse tabs.")
    assert install.BLOCK_START in instructions
    assert ".factory/runs/" in (target / ".gitignore").read_text()
    assert any(line.startswith("merged") for line in log)


def test_install_is_idempotent_and_keeps_user_edits(target: Path) -> None:
    install.install(target)
    standards = target / "docs" / "coding-standards.md"
    standards.write_text("mine")
    before = {p: p.read_text() for p in target.rglob("*") if p.is_file() and ".git/" not in str(p)}
    log = install.install(target)
    after = {p: p.read_text() for p in target.rglob("*") if p.is_file() and ".git/" not in str(p)}
    assert before == after
    assert standards.read_text() == "mine"
    assert not any(line.startswith(("created", "merged", "overwrote")) for line in log)


def test_dry_run_writes_nothing(target: Path) -> None:
    install.install(target, dry_run=True, src=["alpha"], tests=["test"], base="main")
    assert not (target / ".factory").exists()


def test_cli_rejects_non_git_dir(tmp_path: Path) -> None:
    assert install.main([str(tmp_path)]) == 2
