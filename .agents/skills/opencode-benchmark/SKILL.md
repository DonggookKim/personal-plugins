---
name: opencode-benchmark
description: Compare configured OpenCode implementation models on identical isolated score-detector tasks while Codex independently evaluates and reviews each result. Use for this repository's two-stage OpenCode model benchmark, not ordinary project implementation.
---

# OpenCode model benchmark

Use the shared `scripts/opencode_delegate.py` runner through `scripts/benchmark.py`; do not add another OpenCode execution path. For ordinary project work use the sibling `opencode-delegate` Skill.

## Responsibility boundary

- Codex owns the common task, isolation, independent evaluator, diff review, and result assessment.
- OpenCode edits only its prepared worker directory and runs worker-owned tests.
- The user authorizes provider calls/cost and decides final model adoption.

## No-cost preparation

1. Read `README.md`, `benchmarks/models.json`, and `benchmarks/score-detector/README.md`.
2. Confirm Python 3.11+, Git, `opencode --version`, `opencode run --help`, provider authentication, and `opencode models` without printing secrets. If Codex and OpenCode run in different Windows/WSL environments, stop actual execution until both can access the same worker path.
3. For each alias, run `python scripts/benchmark.py prepare --case <stage> --model <alias>` and then `dry-run`. These actions must not call a model.
4. Confirm every manifest has the intended model ID and identical hashes for the same stage.

## Paid/external execution

Run `execute` only after explicit authorization for the relevant provider/model. `execute` uses the common delegation wrapper, writes a fresh numbered log attempt, and never overwrites the first result. A timeout is not a spend cap; account-level limits remain required.

After an attempt, run `evaluate`, inspect `result.json`, the actual changed files, worker tests, independent tests, and the full code. Record Codex review findings separately. A dry-run, prepared workspace, provider error, or worker-authored test claim is not a successful model result.

## Fair comparison invariants

- Same stage prompt, starter hash, Python version, permissions, timeout, and independent tests.
- Separate worker directories and logs for each model; do not give a worker another model's output.
- Stage 2 always starts from the common fixture, not a model's Stage 1 implementation.
- The evaluator remains outside the worker directory. It is public, not cryptographically hidden.
- Preserve first-attempt and post-rework scores separately. Classify quota, auth, unavailable model, and missing tool support as integration/availability failures rather than code defects.
- Compare provider-billed cost separately from best-effort OpenCode event usage.
- No confidential input, commit, push, merge, or MKM modification.

## Report

For every attempt record stage, alias, resolved provider/model ID, manifest hashes, environment versions, timestamps, worker exit/timeout, changed files, scope violations, worker tests, independent tests, Codex review, retry number, session IDs, usage fields, billed-cost source, and privacy caveats. State clearly which models were merely prepared and which were actually called.
