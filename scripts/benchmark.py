#!/usr/bin/env python3
"""Prepare, delegate, and independently evaluate isolated OpenCode benchmarks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "score-detector"
RUNS = ROOT / ".runs"
TASKS = {
    "stage1": ("tasks/stage1.md", None, ["test_stage1.py"]),
    "stage2": (
        "tasks/stage2.md",
        "fixtures/score_detector.py",
        ["test_stage1.py", "test_stage2.py"],
    ),
}
STUB = '''"""Implement Stage 1 contract. Standard library only."""


def detect_score_changes(
    observations: list[tuple[int, int | None]],
    min_consecutive: int = 3,
) -> list[tuple[int, int, int]]:
    raise NotImplementedError
'''
IGNORED_DIRECTORIES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def load_catalog() -> dict[str, dict[str, str]]:
    catalog = json.loads((ROOT / "benchmarks/models.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not catalog:
        raise ValueError("benchmarks/models.json must contain at least one model")
    for alias, entry in catalog.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("opencode_model"), str):
            raise ValueError(f"model {alias!r} is missing opencode_model")
    return catalog


def delegate_runner_candidates() -> list[Path]:
    candidates = []
    configured = os.environ.get("OPENCODE_DELEGATE_RUNNER")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            Path.home() / ".agents/skills/opencode-delegate/scripts/run_worker.py",
            Path.home() / ".codex/skills/opencode-delegate/scripts/run_worker.py",
        ]
    )
    return candidates


def find_delegate_runner() -> Path:
    for candidate in delegate_runner_candidates():
        if candidate.is_file():
            return candidate.resolve()
    checked = ", ".join(str(path) for path in delegate_runner_candidates())
    raise FileNotFoundError(
        "opencode-delegate runner not found; install the upstream Skill or set "
        f"OPENCODE_DELEGATE_RUNNER (checked: {checked})"
    )


def environment_with_opencode() -> tuple[dict[str, str], str | None]:
    env = os.environ.copy()
    found = shutil.which("opencode", path=env.get("PATH"))
    if found:
        return env, found
    try:
        login = subprocess.run(
            ["bash", "-lic", "command -v opencode"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return env, None
    candidate = login.stdout.strip().splitlines()
    if login.returncode == 0 and candidate and Path(candidate[-1]).is_file():
        found = candidate[-1]
        env["PATH"] = str(Path(found).parent) + os.pathsep + env.get("PATH", "")
        return env, found
    return env, None


def build_task(case: str, prompt: str) -> dict[str, object]:
    return {
        "objective": f"Implement the score detector {case} requirements in prompt.md.",
        "scope": [prompt, "Add worker-owned unittest coverage and run it."],
        "allowed_paths": ["score_detector.py", "test_score_detector_worker.py"],
        "constraints": [
            "Work only in this prepared directory.",
            "Use the Python standard library only.",
            "Do not access the independent evaluator outside this directory.",
            "Do not commit, push, merge, create branches, or read credentials.",
        ],
        "acceptance_criteria": [
            "score_detector.py satisfies every requirement in prompt.md.",
            "test_score_detector_worker.py covers normal and boundary behavior.",
            "All worker-owned tests pass.",
        ],
        "tests": [
            f'"{sys.executable}" -m unittest discover -s . -p "test_score_detector_worker.py" -v'
        ],
    }


def next_attempt(case: str, model: str) -> Path:
    attempts = RUNS / "logs" / case / model
    number = 1
    while (attempts / f"{number:03d}").exists():
        number += 1
    return attempts / f"{number:03d}"


def text_snapshot(root: Path) -> dict[str, str | None]:
    snapshot: dict[str, str | None] = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in IGNORED_DIRECTORIES)
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")):
                continue
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            try:
                snapshot[relative] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                snapshot[relative] = None
    return snapshot


def changed_files(
    before: dict[str, str | None], after: dict[str, str | None]
) -> list[str]:
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )


def path_is_allowed(path: str, rules: list[str]) -> bool:
    normalized = Path(path).as_posix()
    return any(
        normalized == Path(rule).as_posix().strip("/")
        or normalized.startswith(Path(rule).as_posix().strip("/") + "/")
        for rule in rules
    )


def write_diff(
    path: Path,
    before: dict[str, str | None],
    after: dict[str, str | None],
    changes: list[str],
) -> None:
    lines = []
    for relative in changes:
        old = before.get(relative)
        new = after.get(relative)
        if old is None and relative in before or new is None and relative in after:
            lines.append(f"Binary or unreadable change: {relative}\n")
            continue
        lines.extend(
            difflib.unified_diff(
                [] if old is None else old.splitlines(keepends=True),
                [] if new is None else new.splitlines(keepends=True),
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
    path.write_text("".join(lines), encoding="utf-8")


def extract_usage(log_path: Path) -> dict[str, Any]:
    sessions: set[str] = set()
    costs: list[float] = []
    tokens: dict[str, int] = {}
    events = 0

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lower = key.lower()
                if lower in {"sessionid", "session_id"} and isinstance(item, str):
                    sessions.add(item)
                elif lower == "cost" and isinstance(item, (int, float)) and not isinstance(item, bool):
                    costs.append(float(item))
                elif lower == "tokens" and isinstance(item, dict):
                    for token_key, count in item.items():
                        if isinstance(count, int) and not isinstance(count, bool):
                            tokens[token_key] = tokens.get(token_key, 0) + count
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    with log_path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            events += 1
            visit(event)
    return {
        "parsed_json_events": events,
        "session_ids": sorted(sessions),
        "observed_cost_total": round(sum(costs), 12) if costs else None,
        "observed_tokens": tokens,
        "source": "best-effort OpenCode JSONL fields; verify provider billing separately",
    }


def run_test_commands(
    commands: list[str], cwd: Path, output_dir: Path, timeout: int = 300
) -> list[dict[str, Any]]:
    results = []
    for index, command in enumerate(commands, 1):
        started = time.monotonic()
        log_path = output_dir / f"worker-test-{index:02d}.log"
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            output = completed.stdout + "\n" + completed.stderr
            exit_code = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
            output = (stdout or "") + "\n" + (stderr or "")
            exit_code = 124
            timed_out = True
        log_path.write_text(output, encoding="utf-8")
        results.append(
            {
                "command": command,
                "exit_code": exit_code,
                "passed": exit_code == 0,
                "timed_out": timed_out,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "log_path": str(log_path),
            }
        )
    return results


def delegate_command(
    runner: Path,
    work: Path,
    task_file: Path,
    model_id: str,
    timeout: int,
    dry_run: bool,
) -> list[str]:
    command = [
        sys.executable,
        str(runner),
        "--cwd",
        str(work),
        "--task-file",
        str(task_file),
        "--model",
        model_id,
        "--timeout",
        str(timeout),
    ]
    command.append("--dry-run" if dry_run else "--auto")
    return command


def main() -> int:
    catalog = load_catalog()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "dry-run", "execute", "evaluate"))
    parser.add_argument("--case", required=True, choices=TASKS)
    parser.add_argument("--model", required=True, choices=sorted(catalog))
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    model_id = catalog[args.model]["opencode_model"]
    work = RUNS / args.case / args.model

    if args.action == "prepare":
        if work.exists():
            parser.error(f"{work} already exists; retain it or remove it manually")
        work.mkdir(parents=True)
        prompt_path, fixture_path, _ = TASKS[args.case]
        shutil.copy2(BENCH / prompt_path, work / "prompt.md")
        if fixture_path:
            shutil.copy2(BENCH / fixture_path, work / "score_detector.py")
        else:
            (work / "score_detector.py").write_text(STUB, encoding="utf-8")
        task = build_task(args.case, (work / "prompt.md").read_text(encoding="utf-8"))
        (work / "task.json").write_text(
            json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        manifest = {
            "schema_version": 2,
            "case": args.case,
            "model_alias": args.model,
            "model_id": model_id,
            "baseline_sha256": hashlib.sha256((work / "score_detector.py").read_bytes()).hexdigest(),
            "prompt_sha256": hashlib.sha256((work / "prompt.md").read_bytes()).hexdigest(),
            "task_sha256": hashlib.sha256((work / "task.json").read_bytes()).hexdigest(),
        }
        (work / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Prepared: {work}")
        print(f"Model: {model_id}")
        print("Only execute calls a model; prepare, dry-run, and evaluate do not.")
        return 0

    if not work.is_dir() or not (work / "manifest.json").exists():
        parser.error("prepared workspace missing; run prepare first")
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if manifest["model_id"] != model_id or manifest["case"] != args.case:
        parser.error("manifest does not match the selected case/model")
    for filename, key in (("prompt.md", "prompt_sha256"), ("task.json", "task_sha256")):
        if hashlib.sha256((work / filename).read_bytes()).hexdigest() != manifest[key]:
            parser.error(f"{filename} changed after preparation; create a fresh workspace")

    if args.action in {"dry-run", "execute"}:
        if args.timeout < 1:
            parser.error("timeout must be positive")
        try:
            runner = find_delegate_runner()
        except FileNotFoundError as exc:
            parser.error(str(exc))
        env, opencode = environment_with_opencode()
        if opencode is None:
            parser.error("opencode not found on PATH or the WSL login-shell PATH")
        command = delegate_command(
            runner, work, work / "task.json", model_id, args.timeout, args.action == "dry-run"
        )
        if args.action == "dry-run":
            baseline = hashlib.sha256((work / "score_detector.py").read_bytes()).hexdigest()
            if baseline != manifest["baseline_sha256"]:
                parser.error("starter changed before dry-run; create a fresh workspace")
            completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
            return completed.returncode

        attempt = next_attempt(args.case, args.model)
        if attempt.name == "001":
            baseline = hashlib.sha256((work / "score_detector.py").read_bytes()).hexdigest()
            if baseline != manifest["baseline_sha256"]:
                parser.error("starter changed before first execution; create a fresh workspace")
        attempt.mkdir(parents=True)
        before = text_snapshot(work)
        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, check=False)
        stdout_path = attempt / "opencode.stdout.jsonl"
        stderr_path = attempt / "opencode.stderr.log"
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        after = text_snapshot(work)
        changes = changed_files(before, after)
        allowed_paths = json.loads((work / "task.json").read_text(encoding="utf-8")).get(
            "allowed_paths", []
        )
        unauthorized = [path for path in changes if not path_is_allowed(path, allowed_paths)]
        diff_path = attempt / "worker.diff"
        write_diff(diff_path, before, after, changes)
        worker_tests = []
        if completed.returncode == 0:
            task = json.loads((work / "task.json").read_text(encoding="utf-8"))
            worker_tests = run_test_commands(task["tests"], work, attempt)
        success = (
            completed.returncode == 0
            and not unauthorized
            and all(test["passed"] for test in worker_tests)
        )
        unresolved = []
        if completed.returncode != 0:
            unresolved.append(f"upstream delegate runner exited with {completed.returncode}")
        if unauthorized:
            unresolved.append("worker changed paths outside allowed_paths")
        if any(not test["passed"] for test in worker_tests):
            unresolved.append("one or more worker test commands failed")
        result = {
            "schema_version": 2,
            "status": "success" if success else "failed",
            "attempt": int(attempt.name),
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "model_alias": args.model,
            "model_id": model_id,
            "delegate_runner": str(runner),
            "opencode": opencode,
            "worker_exit_code": completed.returncode,
            "changed_files": changes,
            "unauthorized_changes": unauthorized,
            "diff_path": str(diff_path),
            "worker_tests": worker_tests,
            "usage": extract_usage(stdout_path),
            "unresolved_issues": unresolved,
            "logs": {"stdout": str(stdout_path), "stderr": str(stderr_path)},
        }
        (attempt / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if success else 1

    _, _, test_names = TASKS[args.case]
    checks = []
    for filename in test_names:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(work) + os.pathsep + env.get("PYTHONPATH", "")
        command = [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(BENCH / "evaluation"),
            "-p",
            filename,
            "-v",
        ]
        started = time.monotonic()
        completed = subprocess.run(
            command, cwd=work, capture_output=True, text=True, env=env, timeout=120
        )
        log_path = work / (filename + ".log")
        log_path.write_text(completed.stdout + "\n" + completed.stderr, encoding="utf-8")
        checks.append(
            {
                "suite": filename,
                "passed": completed.returncode == 0,
                "exit_code": completed.returncode,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "log_path": str(log_path),
            }
        )
    report = {
        "case": args.case,
        "model_alias": args.model,
        "model_id": model_id,
        "checks": checks,
        "all_passed": all(test["passed"] for test in checks),
        "note": "Independent tests only; provider billing and Codex review remain separate.",
    }
    (work / "evaluation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
