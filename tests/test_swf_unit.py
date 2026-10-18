from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType


def test_parse_diff_lines_handles_counts_and_single_lines(swf: ModuleType) -> None:
    diff = "\n".join(
        [
            "diff --git a/x.py b/x.py",
            "@@ -1,0 +2,3 @@",
            "+a",
            "@@ -10 +14 @@",
            "@@ -20,2 +30,0 @@",
        ]
    )
    assert swf.parse_diff_lines(diff) == {2, 3, 4, 14}


def test_test_requirements_accepts_common_spellings(swf: ModuleType) -> None:
    text = "def test_req_001_a(): ...\ndef test_REQ12(): ...\n# covers REQ-003"
    assert swf.test_requirements(text) == {1, 12, 3}


def test_file_classification(swf: ModuleType, tmp_path: Path) -> None:
    cfg = swf.Config(root=tmp_path, src_paths=["src"], test_paths=["tests"])
    assert swf.is_src_file(cfg, "src/pkg/a.py")
    assert not swf.is_src_file(cfg, "src/pkg/test_a.py")
    assert not swf.is_src_file(cfg, "scripts/a.py")
    assert swf.is_test_file(cfg, "tests/helpers.py")
    assert swf.is_test_file(cfg, "src/pkg/a_test.py")
    assert swf.is_characterization("tests/test_characterization_returns.py")


def test_ranges(swf: ModuleType) -> None:
    assert swf._ranges([1, 2, 3, 5, 7, 8]) == "1-3, 5, 7-8"
    assert swf._ranges([4]) == "4"


def test_mutants_only_on_changed_lines_and_skip_docstrings(swf: ModuleType) -> None:
    source = 'def f(x: int = 1) -> bool:\n    """Doc 1."""\n    return x > 0\n'
    on_line_3 = swf.find_mutants("m.py", source, {3})
    descriptions = {m.description for m in on_line_3}
    assert "Gt -> GtE" in descriptions
    assert "0 -> 1" in descriptions
    assert "return None" in descriptions
    assert all(m.lineno == 3 for m in on_line_3)
    assert swf.find_mutants("m.py", source, {2}) == []


def test_apply_mutant_produces_valid_python(swf: ModuleType) -> None:
    source = "def f(a, b):\n    if a and b:\n        return a + b\n    return -a\n"
    mutants = swf.find_mutants("m.py", source, {2, 3, 4})
    assert len(mutants) >= 4
    for mutant in mutants:
        mutated = swf.apply_mutant(source, mutant)
        ast.parse(mutated)
        assert mutated != ast.unparse(ast.parse(source))
