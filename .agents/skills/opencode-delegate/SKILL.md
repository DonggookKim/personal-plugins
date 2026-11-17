---
name: opencode-delegate
description: Delegate bounded implementation work to an installed OpenCode CLI while Codex owns the specification, diff review, independent tests, and integration. Use for substantial implementation explicitly suited to OpenCode; not for credential handling, destructive operations, or unbounded changes.
---

# OpenCode implementation delegation

Use OpenCode as an implementation worker. Codex remains responsible for repository analysis, authorization boundaries, acceptance criteria, independent verification, commits, and the user-facing result.

This skill adapts the MIT-licensed `noorbakhsh09/opencode-delegate-skill`; see `THIRD_PARTY_NOTICES.md` at the repository root.

## Before delegating

1. Read repository instructions and inspect the relevant code and Git status.
2. Split the request into a cohesive implementation unit. Prefer a clean dedicated Git worktree for a real repository and a separate directory for every concurrent worker.
3. Never send secrets, credentials, private data, destructive operations, or authority the user did not grant. OpenCode must not commit, push, merge, or change branches.
4. Write a JSON task file outside the target worktree when practical:

```json
{
  "objective": "Concrete implementation outcome",
  "scope": ["Components and behavior in scope"],
  "allowed_paths": ["src/component", "tests/test_component.py"],
  "constraints": ["Existing contracts and forbidden changes"],
  "acceptance_criteria": ["Observable completion conditions"],
  "tests": ["python -m unittest tests.test_component -v"]
}
```

`allowed_paths` is optional. When present, the runner reports any changed file outside those prefixes as a failure. This is post-run detection, not an OS sandbox.

## Validate without a model call

Run the common wrapper in dry-run mode. It validates the task and prints a redacted command even when OpenCode is unavailable:

```bash
python3 scripts/opencode_delegate.py \
  --cwd /absolute/path/to/worktree \
  --task-file /absolute/path/to/task.json \
  --model provider/model \
  --dry-run
```

## Execute

Only after the user has authorized the implementation and any provider cost:

```bash
python3 scripts/opencode_delegate.py \
  --cwd /absolute/path/to/worktree \
  --task-file /absolute/path/to/task.json \
  --output-dir /absolute/path/outside-worktree/logs/attempt-001 \
  --model provider/model \
  --timeout 1800 \
  --auto
```

The output directory must be outside the worker directory so evidence does not contaminate its diff or context. Use the OpenCode executable from the same OS/filesystem environment as the worktree. If PATH discovery is insufficient, pass `--opencode-bin`. Do not reuse an output directory: a correction attempt gets `attempt-002`, preserving earlier evidence. Avoid `--allow-dirty`; when it is necessary, the runner records both Git states but cannot attribute pre-existing changes as confidently.

## Review and integrate

1. Read `result.json`, the full `git.diff`, logs, changed-file list, test results, session IDs, and best-effort usage fields.
2. Inspect the repository's actual Git diff and run relevant tests independently. Provider billing is authoritative for cost; event-log cost is only a hint.
3. Reject commits, branch changes, unrelated paths, unsafe code, unverifiable claims, and contract regressions.
4. Re-delegate only with a concrete defect and bounded correction spec. Preserve the earlier attempt. Stop after two correction attempts unless the user asks to continue.
5. Codex may commit a verified implementation unit when the user requested commit management. OpenCode never commits or pushes.
