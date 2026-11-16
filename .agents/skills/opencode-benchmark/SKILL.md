---
name: opencode-benchmark
description: Benchmark OpenCode implementation workers through identical isolated score-detector tasks; Codex prepares specifications, delegates edits, and independently reviews results.
---

# OpenCode implementation benchmark (PoC)

## Trigger

Use when the user explicitly requests **OpenCode model comparison / benchmark** or to validate a Codex → OpenCode delegation workflow. Do not invoke automatically for ordinary implementation work until the PoC is approved.

## Responsibility boundary

- **Codex:** requirements, model-independent task spec, task split, orchestration, independent tests, diff review, and result assessment.
- **OpenCode:** edits the isolated worker's \`score_detector.py\`, tests its own changes, and reports limitations.
- **User:** decides whether to incur API cost and whether to expand the workflow to MKM.

## Execution (no API calls unless requested)

1. Read \`README.md\`, \`benchmarks/models.json\`, and \`benchmarks/score-detector/README.md\`.
2. Inspect \`opencode --version\`, \`opencode run --help\`, available models, and provider authentication **without printing secrets**.
3. Prefer \`python scripts/benchmark.py prepare --case stage1 --model <alias>\` to create isolated input. Repeat for the three aliases.
4. **Only on explicit user request** run \`python scripts/benchmark.py execute --case stage1 --model <alias>\`. Capture the OpenCode event log. Do not claim that a dry run is a model result.
5. Run \`python scripts/benchmark.py evaluate --case stage1 --model <alias>\`. Evaluate stage2 identically with fresh folders.
6. Compare tests, diff scope, failed requirements, rework attempts, token usage and OpenRouter **billed cost** separately. For model quality, do not count API errors/quotas as code bugs; report them as availability failures.
7. Codex may ask for a bounded fix, but retain the first-attempt score separately from final-after-rework score. Never let a worker rewrite the independent evaluator.
8. Report model alias + resolved provider/model ID, model/provider version, test suite version, base file hash, start time, success/failure, counts, attempts, cost source, and privacy caveats.

## Fair comparison

- Same prompt, starter, Python version, tool policy, max runtime, and independent tests.
- Models start from the same source state; no shared context or previous model output.
- If a model cannot call shell/edit tools, record an integration failure; do not silently substitute another model.
- Task 2 (extension) starts from the **common provided baseline**, not each model's Task 1 implementation. This isolates modification ability from errors in task 1.
- Keep worker folders separate from the evaluator. The repository's public evaluator is **not secret**; isolation prevents accidental exposure in the model's working directory.
- API spend cap must be set at the provider/account level; local timeout is not a financial limit.
- No push, merge, credential export, confidential inputs or changes to MKM during this PoC.

## Follow-up

If benchmark passes, open a separate implementation PR for **bounded commit delegation** and add robust worktree sandboxing, retry/session lifecycle, and cost telemetry. This Skill itself is intentionally small and does not force implementation delegation yet.
