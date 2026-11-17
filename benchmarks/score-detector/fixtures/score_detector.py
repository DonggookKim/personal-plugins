"""Common unmodified baseline for Stage 2. Python 3.11 standard library."""


def detect_score_changes(
    observations: list[tuple[int, int | None]],
    min_consecutive: int = 3,
) -> list[tuple[int, int, int]]:
    if min_consecutive < 1:
        raise ValueError("min_consecutive must be >= 1")

    events: list[tuple[int, int, int]] = []
    stable: int | None = None
    previous_ts: int | None = None
    run_score: int | None = None
    run_count = 0
    run_start_ts = 0

    for ts, score in observations:
        if previous_ts is not None and ts < previous_ts:
            raise ValueError("timestamps must be ordered")
        previous_ts = ts

        if score is None:
            run_score = None
            run_count = 0
            continue

        if score == run_score:
            run_count += 1
        else:
            run_score = score
            run_count = 1
            run_start_ts = ts

        if run_count == min_consecutive and stable != score:
            if stable is not None:
                events.append((run_start_ts, stable, score))
            stable = score

    return events
