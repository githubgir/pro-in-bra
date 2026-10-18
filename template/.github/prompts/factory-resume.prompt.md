---
agent: factory-orchestrator
description: Resume a factory run from its recorded phase.
argument-hint: spec id, e.g. ABC-123
---

Resume the factory for spec `${input:spec:ABC-123}`.

1. Run `python .factory/swf.py status ${input:spec}` and read `specs/${input:spec}/gate-log.md`
   and the latest files in `specs/${input:spec}/reviews/`.
2. Tell me in three lines where we are and what happens next.
3. Continue from the recorded phase. If the phase is `escalated`, start with the escalation question.
