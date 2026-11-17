#!/usr/bin/env python3
"""Prepare, dry-run, execute, and independently evaluate OpenCode benchmark cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "score-detector"
RUNS = ROOT / ".runs"
DELEGATE = ROOT / "scripts" / "opencode_delegate.py"
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


def load_catalog() -> dict[str, dict[str, str]]:
    catalog = json.loads((ROOT / "benchmarks/models.json").read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not catalog:
        raise ValueError("benchmarks/models.json must contain at least one model")
    for alias, entry in catalog.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("opencode_model"), str):
            raise ValueError(f"model {alias!r} is missing opencode_model")
    return catalog


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


def main() -> int:
    catalog = load_catalog()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "dry-run", "execute", "evaluate"))
    parser.add_argument("--case", required=True, choices=TASKS)
    parser.add_argument("--model", required=True, choices=sorted(catalog))
    parser.add_argument("--timeout", type=int, default=1800, help="Seconds (execute only)")
    parser.add_argument("--opencode-bin", help="Explicit OpenCode executable")
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
        prompt = (work / "prompt.md").read_text(encoding="utf-8")
        task = build_task(args.case, prompt)
        (work / "task.json").write_text(
            json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        source_bytes = (work / "score_detector.py").read_bytes()
        manifest = {
            "schema_version": 1,
            "case": args.case,
            "model_alias": args.model,
            "model_id": model_id,
            "baseline_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "prompt_sha256": hashlib.sha256((work / "prompt.md").read_bytes()).hexdigest(),
            "task_sha256": hashlib.sha256((work / "task.json").read_bytes()).hexdigest(),
        }
        (work / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Prepared: {work}")
        print(f"Model: {model_id}")
        print(
            f"Next: {sys.executable} scripts/benchmark.py dry-run "
            f"--case {args.case} --model {args.model}"
        )
        print("CAUTION: only the execute action calls a model and may incur API charges.")
        return 0

    if not work.is_dir() or not (work / "manifest.json").exists():
        parser.error("prepared workspace missing; run prepare first")
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if manifest["model_id"] != model_id or manifest["case"] != args.case:
        parser.error("manifest does not match the selected case/model")
    if hashlib.sha256((work / "task.json").read_bytes()).hexdigest() != manifest["task_sha256"]:
        parser.error("task.json changed after preparation; create a fresh benchmark workspace")

    if args.action in {"dry-run", "execute"}:
        if args.timeout < 1:
            parser.error("timeout must be positive")
        command = [
            sys.executable,
            str(DELEGATE),
            "--cwd",
            str(work),
            "--task-file",
            str(work / "task.json"),
            "--model",
            model_id,
            "--timeout",
            str(args.timeout),
        ]
        if args.opencode_bin:
            command.extend(["--opencode-bin", args.opencode_bin])
        if args.action == "dry-run":
            command.append("--dry-run")
        else:
            attempt = next_attempt(args.case, args.model)
            command.extend(["--output-dir", str(attempt), "--auto"])
            print(f"Running {args.model} in {work}; logs: {attempt}")
            print("API fees and external tools may apply.")
        return subprocess.run(command, cwd=ROOT, check=False).returncode

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
        result = subprocess.run(
            command, cwd=work, capture_output=True, text=True, env=env, timeout=120
        )
        log_path = work / (filename + ".log")
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        checks.append(
            {
                "suite": filename,
                "passed": result.returncode == 0,
                "exit_code": result.returncode,
                "log_path": str(log_path),
            }
        )
    report = {
        "case": args.case,
        "model_alias": args.model,
        "model_id": model_id,
        "checks": checks,
        "all_passed": all(test["passed"] for test in checks),
        "note": "Independent tests only; billing, reliability, and Codex review remain separate.",
    }
    (work / "evaluation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
