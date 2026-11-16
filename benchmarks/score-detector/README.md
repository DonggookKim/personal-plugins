# Score Detector: two-stage coding benchmark

Python 3.11 + standard library only. Goal: test **implementation accuracy, regression preservation, test quality, and instruction compliance**, not response speed.

## Shared contract

Input: sorted (timestamp_ms, score) observations where score is 0, 1, 2, or None. New state requires N consecutive observations. None breaks a run but not the stable state. Timestamp of an event is **first observation of the confirmed run**. Initial stable state never emits an event. Duplicate timestamps allowed, decreasing timestamps must raise ValueError, no input mutation.

- [Stage 1 — write the detector](tasks/stage1.md): start from a stub; implement the baseline contract and own unit tests.
- [Stage 2 — extend the detector](tasks/stage2.md): start from the **shared** stable baseline, add reset markers and threshold schedule while keeping the old positional API. Must retain all stage 1 behavior.

## Experimental discipline

Each model gets a clean \`.runs/<stage>/<alias>\` working directory with only a prompt and starter; common evaluator is outside this directory. Run Python unit tests against worker output, not the worker's self-reported result. Model testing is separate from provider availability testing.

**Not cryptographically hidden:** the evaluator is in this public GitHub repository. Codex should not attach it to the worker prompt or working directory; if stronger blind evaluation is needed, keep new held-out cases outside the public repository.

### Metrics

| Metric | Measure |
| --- | --- |
| Correctness | Passed/failed independent unit tests; requirement violations |
| Robustness | Existing behavior regression, timestamp and reset edge cases |
| Scope | Modified files, unauthorized extra changes |
| Effort | Model calls, rework attempts, timeout, elapsed time |
| Cost | Provider billed amount, input/output/cache tokens, rate limit failures |

The evaluator is a practical regression suite, **not** a proof of correctness. Stage 1 and 2 are small; later MKM-like multi-file integration cases should be added before picking a default implementation model.

### Running

~~~bash
python scripts/benchmark.py prepare --case stage2 --model deepseek
python scripts/benchmark.py execute --case stage2 --model deepseek
python scripts/benchmark.py evaluate --case stage2 --model deepseek
~~~

Always verify billing/privacy and the model ID before \`execute\`. Results and logs stay in ignored \`.runs/\`. The evaluator can run without OpenCode if a candidate code file is manually copied into the prepared workspace.
