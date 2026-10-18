---
agent: agent
description: Turn a rough idea into an issue file under issues/ (no code, no spec yet).
argument-hint: your idea in a sentence or two
tools: ['read', 'search', 'edit', 'vscode/askQuestions']
---

Create a new issue file from this idea: ${input:idea:describe the idea}

1. Propose an id (`FEAT-<short-slug>` unless I name one) and ask me to confirm
   it with a single question.
2. Copy `.factory/templates/issue.md` to `issues/<ID>.md` and fill it from the
   idea. Do not invent requirements; put unknowns under "Open questions".
3. Ask at most two clarifying questions, one at a time, only if the problem
   statement itself is unclear. Detailed questions belong to the factory interview.
4. Finish by telling me to run `/factory-start issues/<ID>.md`.
