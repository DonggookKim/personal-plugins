# Stage 2 — extend an existing score detector without regressions

A correct baseline score_detector.py is provided. Preserve the old behavior and the two existing positional parameters. **Do not replace the existing function with an unrelated implementation.**

Add these keyword-only arguments:

~~~python
def detect_score_changes(
    observations: list[tuple[int, int | None]],
    min_consecutive: int = 3,
    *,
    reset_timestamps: set[int] | None = None,
    threshold_schedule: list[tuple[int, int]] | None = None,
) -> list[tuple[int, int, int]]:
    ...
~~~

## A. Scoreboard reset

- At any reset time, discard confirmed state and current candidate run. Reset alone is not an event.
- A reset applies immediately **before** an observation whose timestamp equals the reset time.
- A reset between observation times applies before the next observation.
- For multiple equal-time observations, apply each reset once only.
- Multiple reset times between two observations must all be handled.
- The first stable run after reset is a new baseline, not a transition.
- If there is no observation after reset, emit nothing extra.

Example: [(0,0),(10,0),(20,0),(30,1),(40,1),(50,1),(60,2),(70,2),(80,2)], reset_timestamps={55} produces [(30,0,1)] only.

## B. Time-dependent threshold

- Schedule items: (effective_from_ms, required_consecutive).
- effective_from_ms must be strictly increasing. Each threshold is an integer >= 1 (bool is not accepted).
- At the **start of each candidate run**, choose the latest schedule item with effective_from_ms <= run start; otherwise use min_consecutive.
- A threshold change in the middle of a run does **not** change its requirement.
- After None, a different score, or reset, a new run gets a fresh threshold.
- The schedule stays in force across resets.
- Invalid schedules / thresholds raise ValueError, including on empty observations.

Example: schedule=[(0,2),(100,3)], observations=[(0,0),(10,0),(90,1),(110,1),(120,2),(130,2),(140,2)] produces [(90,0,1),(120,1,2)].

## Invariants & output

- Same timestamp handling, None semantics, event tuple format, input immutability, and error behavior as Stage 1.
- Both new arguments are keyword-only.
- Target O(n + r + s) for presorted inputs; since resets arrive as a set, sorting may add O(r log r). Explain actual complexity honestly.
- No external dependencies.
- Create/extend unittest tests covering: old behavior, reset boundaries, equal timestamps, unfinished runs, threshold changes during runs, malformed schedules, and both features together.
- Return modified score_detector.py, test_score_detector_worker.py and a concise summary of tests actually run. No commit/push/merge or unrelated files.
