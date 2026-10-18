from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "template"
SWF = TEMPLATE / ".factory" / "swf.py"


def load_swf() -> ModuleType:
    spec = importlib.util.spec_from_file_location("swf", SWF)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["swf"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def swf() -> ModuleType:
    return load_swf()


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


EXISTING_SRC = '''\
"""Existing brownfield analytics code."""


def simple_return(p0: float, p1: float) -> float:
    """Arithmetic return between two prices."""
    return p1 / p0 - 1.0
'''

EXISTING_TEST = """\
from quant.returns import simple_return


def test_simple_return() -> None:
    assert simple_return(100.0, 110.0) == pytest_approx(0.1)


def pytest_approx(x: float) -> object:
    import pytest

    return pytest.approx(x)
"""


@pytest.fixture
def brownfield(tmp_path: Path) -> Path:
    root = tmp_path / "brownfield"
    (root / "src" / "quant").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "quant" / "__init__.py").write_text("")
    (root / "src" / "quant" / "returns.py").write_text(EXISTING_SRC)
    (root / "tests" / "test_returns.py").write_text(EXISTING_TEST)
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [tool.pytest.ini_options]
            pythonpath = ["src"]

            [tool.mypy]
            mypy_path = "src"
            """
        )
    )
    factory = root / ".factory"
    (factory / "templates").mkdir(parents=True)
    shutil.copy(SWF, factory / "swf.py")
    shutil.copy(TEMPLATE / ".factory" / "templates" / "spec.md", factory / "templates" / "spec.md")
    config = (TEMPLATE / ".factory" / "config.toml").read_text()
    config = config.replace('"~/.factory-holdout"', f'"{tmp_path / "holdout"}"')
    (factory / "config.toml").write_text(config)
    (root / ".gitignore").write_text(".factory/runs/\n.factory/holdout-staging/\n__pycache__/\n")
    (root / "issues").mkdir()
    (root / "issues" / "Q-1.md").write_text("# Log returns\n\nAdd log returns.\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return root


Runner = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def run(brownfield: Path) -> Runner:
    def _run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, ".factory/swf.py", *args],
            cwd=brownfield,
            capture_output=True,
            text=True,
            check=False,
        )

    return _run
