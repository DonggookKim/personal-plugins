#!/usr/bin/env python3
"""Run one structured implementation task through OpenCode and record evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


REQUIRED_FIELDS = (
    "objective",
    "scope",
    "constraints",
    "acceptance_criteria",
    "tests",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True, help="Worker directory")
    parser.add_argument("--task-file", required=True, help="Structured task JSON")
    parser.add_argument("--output-dir", help="New directory for logs and result.json")
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENCODE_DELEGATE_MODEL", "opencode/big-pickle"),
    )
    parser.add_argument(
        "--agent", default=os.environ.get("OPENCODE_DELEGATE_AGENT", "build")
    )
    parser.add_argument("--opencode-bin", help="OpenCode executable; default: PATH lookup")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--test-timeout", type=int, default=300)
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Allow OpenCode to approve task-authorized tools non-interactively",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow a dirty Git worktree (baseline is still recorded)",
    )
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print redacted invocation metadata; do not call OpenCode",
    )
    return parser.parse_args()


def load_task(path: Path) -> dict[str, Any]:
    try:
        task = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid task JSON: {exc}") from exc
    if not isinstance(task, dict):
        raise ValueError("task JSON must be an object")
    missing = [field for field in REQUIRED_FIELDS if field not in task]
    if missing:
        raise ValueError(f"task JSON is missing fields: {', '.join(missing)}")
    if not isinstance(task["objective"], str) or not task["objective"].strip():
        raise ValueError("objective must be a non-empty string")
    for field in REQUIRED_FIELDS[1:]:
        value = task[field]
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(f"{field} must be an array of non-empty strings")
    allowed = task.get("allowed_paths", [])
    if not isinstance(allowed, list) or not all(
        isinstance(item, str) and item.strip() for item in allowed
    ):
        raise ValueError("allowed_paths must be an array of non-empty strings")
    return task


def build_prompt(task: dict[str, Any]) -> str:
    def section(title: str, values: list[str]) -> str:
        body = "\n".join(f"- {value}" for value in values) or "- None specified"
        return f"{title}:\n{body}"

    sections = [
        "You are an implementation worker supervised by Codex. Work only on the bounded task below.",
        f"OBJECTIVE:\n{task['objective']}",
        section("SCOPE", task["scope"]),
        section("ALLOWED PATHS", task.get("allowed_paths", [])),
        section("CONSTRAINTS", task["constraints"]),
        section("ACCEPTANCE CRITERIA", task["acceptance_criteria"]),
        section("TARGETED TESTS", task["tests"]),
        (
            "Do not modify unrelated files, revert pre-existing work, commit, push, merge, "
            "create branches, read credentials, or perform destructive operations. Inspect "
            "existing conventions before editing. Stop and report if a material decision, "
            "missing access, or destructive operation would be required. When done, report "
            "changed files, tests actually run, failures, and unresolved risks."
        ),
    ]
    return "\n\n".join(sections)


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def git_state(cwd: Path) -> dict[str, Any] | None:
    root = git(cwd, "rev-parse", "--show-toplevel")
    if root.returncode != 0:
        return None
    head = git(cwd, "rev-parse", "HEAD")
    status = git(cwd, "status", "--porcelain=v1", "--untracked-files=all")
    branch = git(cwd, "branch", "--show-current")
    return {
        "root": root.stdout.strip(),
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "branch": branch.stdout.strip() if branch.returncode == 0 else None,
        "status": status.stdout.splitlines(),
    }


def file_snapshot(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    ignored_directories = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in ignored_directories)
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")):
                continue
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            try:
                if path.is_symlink():
                    snapshot[relative] = "symlink:" + os.readlink(path)
                else:
                    digest = hashlib.sha256()
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                    snapshot[relative] = digest.hexdigest()
            except OSError as exc:
                snapshot[relative] = f"unreadable:{type(exc).__name__}"
    return snapshot


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )


def path_is_allowed(path: str, rules: list[str]) -> bool:
    normalized = Path(path).as_posix()
    for rule in rules:
        prefix = Path(rule).as_posix().strip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def extract_usage(log_path: Path) -> dict[str, Any]:
    sessions: set[str] = set()
    costs: list[float] = []
    token_totals: dict[str, int] = {}
    parsed_events = 0

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lower = key.lower()
                if lower in {"sessionid", "session_id"} and isinstance(item, str):
                    sessions.add(item)
                if lower == "cost" and isinstance(item, (int, float)) and not isinstance(item, bool):
                    costs.append(float(item))
                if lower == "tokens" and isinstance(item, dict):
                    for token_key, count in item.items():
                        if isinstance(count, int) and not isinstance(count, bool):
                            token_totals[token_key] = token_totals.get(token_key, 0) + count
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    try:
        with log_path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                parsed_events += 1
                visit(event)
    except OSError:
        pass
    return {
        "parsed_json_events": parsed_events,
        "session_ids": sorted(sessions),
        "observed_cost_total": round(sum(costs), 12) if costs else None,
        "observed_tokens": token_totals,
        "source": "best-effort OpenCode JSONL fields; verify provider billing separately",
    }


def run_tests(
    commands: list[str], cwd: Path, output_dir: Path, timeout: int
) -> list[dict[str, Any]]:
    results = []
    for index, command in enumerate(commands, 1):
        started = time.monotonic()
        log_path = output_dir / f"test-{index:02d}.log"
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
            code = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
            output = (stdout or "") + "\n" + (stderr or "")
            code = 124
            timed_out = True
        log_path.write_text(output, encoding="utf-8")
        results.append(
            {
                "command": command,
                "exit_code": code,
                "passed": code == 0,
                "timed_out": timed_out,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "log_path": str(log_path),
            }
        )
    return results


def record_preflight_failure(
    output_dir: Path,
    cwd: Path,
    model: str,
    agent: str,
    exit_code: int,
    message: str,
    baseline_git: dict[str, Any] | None,
) -> int:
    output_dir.mkdir(parents=True)
    stdout_path = output_dir / "opencode.stdout.jsonl"
    stderr_path = output_dir / "opencode.stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text(message + "\n", encoding="utf-8")
    result = {
        "schema_version": 1,
        "status": "failed",
        "phase": "preflight",
        "started_at": None,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": 0,
        "cwd": str(cwd),
        "model": model,
        "agent": agent,
        "worker_exit_code": exit_code,
        "timed_out": False,
        "changed_files": [],
        "unauthorized_changes": [],
        "git_head_changed": False,
        "git_before": baseline_git,
        "git_after": baseline_git,
        "diff_path": None,
        "tests": [],
        "usage": {
            "parsed_json_events": 0,
            "session_ids": [],
            "observed_cost_total": None,
            "observed_tokens": {},
            "source": "OpenCode was not started",
        },
        "unresolved_issues": [message],
        "logs": {
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "result": str(output_dir / "result.json"),
        },
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return exit_code


def main() -> int:
    args = parse_args()
    cwd = Path(args.cwd).expanduser().resolve()
    task_file = Path(args.task_file).expanduser().resolve()
    if not cwd.is_dir():
        print(f"error: worker directory does not exist: {cwd}", file=sys.stderr)
        return 2
    if args.timeout < 1 or args.test_timeout < 1:
        print("error: timeouts must be positive", file=sys.stderr)
        return 2
    try:
        task = load_task(task_file)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    resolved_binary = args.opencode_bin or shutil.which("opencode")
    command_binary = resolved_binary or "opencode"
    command = [
        command_binary,
        "run",
        "--standalone",
        "--model",
        args.model,
        "--agent",
        args.agent,
        "--format",
        "json",
    ]
    if args.auto:
        command.append("--auto")
    command.append(build_prompt(task))

    redacted_command = command[:-1] + ["<structured task prompt>"]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "command": redacted_command,
                    "cwd": str(cwd),
                    "task_file": str(task_file),
                    "model": args.model,
                    "timeout": args.timeout,
                    "opencode_available": resolved_binary is not None,
                    "tests": [] if args.skip_tests else task["tests"],
                },
                indent=2,
            )
        )
        return 0

    if not args.output_dir:
        print("error: --output-dir is required unless --dry-run is used", file=sys.stderr)
        return 2
    output_dir = Path(args.output_dir).expanduser().resolve()
    if output_dir.exists():
        print(f"error: output directory already exists: {output_dir}", file=sys.stderr)
        return 2
    try:
        output_dir.relative_to(cwd)
    except ValueError:
        pass
    else:
        print("error: --output-dir must be outside the worker directory", file=sys.stderr)
        return 2
    baseline_git = git_state(cwd)
    if resolved_binary is None:
        return record_preflight_failure(
            output_dir,
            cwd,
            args.model,
            args.agent,
            127,
            "opencode is not available on PATH; use --opencode-bin",
            baseline_git,
        )
    if baseline_git and baseline_git["status"] and not args.allow_dirty:
        return record_preflight_failure(
            output_dir,
            cwd,
            args.model,
            args.agent,
            2,
            "Git worktree is dirty; use an isolated worktree or --allow-dirty",
            baseline_git,
        )

    output_dir.mkdir(parents=True)
    before = file_snapshot(cwd)
    (output_dir / "task.json").write_text(
        json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "invocation.json").write_text(
        json.dumps(
            {
                "command": redacted_command,
                "cwd": str(cwd),
                "model": args.model,
                "agent": args.agent,
                "timeout": args.timeout,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        worker_exit = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        worker_exit = 124
        timed_out = True
    except OSError as exc:
        stdout = b""
        stderr = str(exc).encode()
        worker_exit = 126
    stdout_path = output_dir / "opencode.stdout.jsonl"
    stderr_path = output_dir / "opencode.stderr.log"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)

    after = file_snapshot(cwd)
    changes = changed_files(before, after)
    final_git = git_state(cwd)
    diff_path = output_dir / "git.diff"
    if final_git:
        diff = git(cwd, "diff", "--binary", "--no-ext-diff")
        diff_path.write_text(diff.stdout, encoding="utf-8")
    else:
        diff_path.write_text("Not a Git worktree; see changed_files in result.json.\n", encoding="utf-8")

    allowed_paths = task.get("allowed_paths", [])
    unauthorized = (
        [path for path in changes if not path_is_allowed(path, allowed_paths)]
        if allowed_paths
        else []
    )
    head_changed = bool(
        baseline_git
        and final_git
        and baseline_git.get("head") != final_git.get("head")
    )
    tests = []
    if worker_exit == 0 and not args.skip_tests:
        tests = run_tests(task["tests"], cwd, output_dir, args.test_timeout)

    unresolved = []
    if timed_out:
        unresolved.append("OpenCode timed out; partial changes were preserved.")
    elif worker_exit != 0:
        unresolved.append(f"OpenCode exited with status {worker_exit}; inspect stderr log.")
    if head_changed:
        unresolved.append("Worker changed Git HEAD, violating the no-commit policy.")
    if unauthorized:
        unresolved.append("Worker changed paths outside allowed_paths.")
    if any(not item["passed"] for item in tests):
        unresolved.append("One or more post-worker test commands failed.")

    success = (
        worker_exit == 0
        and not head_changed
        and not unauthorized
        and all(item["passed"] for item in tests)
    )
    result = {
        "schema_version": 1,
        "status": "success" if success else "failed",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "cwd": str(cwd),
        "model": args.model,
        "agent": args.agent,
        "worker_exit_code": worker_exit,
        "timed_out": timed_out,
        "changed_files": changes,
        "unauthorized_changes": unauthorized,
        "git_head_changed": head_changed,
        "git_before": baseline_git,
        "git_after": final_git,
        "diff_path": str(diff_path),
        "tests": tests,
        "usage": extract_usage(stdout_path),
        "unresolved_issues": unresolved,
        "logs": {
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "result": str(output_dir / "result.json"),
        },
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
