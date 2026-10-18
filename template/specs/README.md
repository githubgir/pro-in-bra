# Specs

Created by the software factory, one folder per issue id:

| File | Written by | Purpose |
|------|------------|---------|
| `spec.md` | factory-spec-writer | Approved specification with `REQ-nnn` requirements |
| `context.md` | factory-scout | Relevant brownfield code, conventions, risks |
| `reviews/*.md` | reviewers | Test and code review rounds (`tests-r1.md`, `code-r1.md`, ...) |
| `gate-log.md` | `swf` | Every gate run with pass/fail per check |
| `state.json` | `swf` | Phase, base commit, loop rounds, test lock hashes |

Commit these with the code: they are the audit trail of why the code looks the way it does.
