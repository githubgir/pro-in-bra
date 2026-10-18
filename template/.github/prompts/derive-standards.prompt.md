---
agent: agent
description: Learn this repository's real conventions and record them in docs/coding-standards.md section 5.
tools: ['read', 'search', 'execute', 'edit', 'vscode/askQuestions']
---

Study this repository and update **section 5 "Repository-specific conventions"**
of `docs/coding-standards.md`. Do not change sections 1-4.

1. Sample broadly: the main packages, the 10 most recently changed Python files
   (`git log --name-only --pretty=format: -n 50 -- '*.py' | sort | uniq -c | sort -rn`),
   `pyproject.toml`/`setup.cfg`, `tests/conftest.py` and representative tests.
2. Record conventions that are **consistent and deliberate**, with a file
   reference as evidence for each, e.g.:
   - data shapes (dates x assets frames, long format, xarray), units, return types;
   - naming (variables, modules, test files), package layout, public API style;
   - error types, logging, config access, dependency injection patterns;
   - numeric idioms (annualisation constants, NaN handling, calendar handling);
   - test fixtures to reuse, comparison helpers, markers, slow-test handling.
3. Where the repo contradicts sections 1-4, list it under "Deviations" and ask
   me (one question at a time) whether to keep the repo convention or the
   standard for new code.
4. Also set `src_paths`/`test_paths`/`base_branch` in `.factory/config.toml`
   if they do not match this repo, and tell me what you changed.

Keep the section concise: bullets, each with a `path:line` example.
