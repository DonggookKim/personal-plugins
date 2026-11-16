# Stage 1 — implement a score-change detector

Implement the full function below in **score_detector.py**, Python 3.11 standard library only.

~~~python
def detect_score_changes(
    observations: list[tuple[int, int | None]],
    min_consecutive: int = 3,
) -> list[tuple[int, int, int]]:
    ...
~~~

## Contract

1. Observations: ordered (timestamp_ms, score); score is 0/1/2/None.
2. None breaks consecutiveness but does not change the current confirmed state.
3. A score becomes confirmed only after min_consecutive observations **in a row**.
4. The event timestamp is the **first timestamp in that run**, not its confirmation time.
5. The first confirmed stable score is the baseline and does **not** produce an event.
6. Return events as (timestamp_ms, old_score, new_score), chronological.
7. Reject decreasing timestamps with ValueError, but allow duplicates.
8. Reject min_consecutive < 1 with ValueError; check even on empty input.
9. Do not mutate the input. Empty and never-confirmed inputs return [].
10. Add your own unittest coverage for normal and boundary cases. Do not change the function signature or use dependencies.

## Submission

- Complete implementation in score_detector.py
- Test file named test_score_detector_worker.py
- Concise report: changed files, tests actually executed, issues or uncertain cases
- Do not edit paths outside this workspace. Do not commit, push or merge.
