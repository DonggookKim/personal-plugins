"""Local OpenCode comparison harness. No API calls except explicit 'execute' action."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "score-detector"
RUNS = ROOT / ".runs"
TASKS = {
    "stage1": ("tasks/stage1.md", None, ["test_stage1.py"]),
    "stage2": ("tasks/stage2.md", "fixtures/score_detector.py",
               ["test_stage1.py", "test_stage2.py"]),
}
STUB = '''"""Implement Stage 1 contract. Standard library only."""


def detect_score_changes(
    observations: list[tuple[int, int | None]],
    min_consecutive: int = 3,
) -> list[tuple[int, int, int]]:
    raise NotImplementedError
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute", "evaluate"))
    parser.add_argument("--case", required=True, choices=TASKS)
    parser.add_argument("--model", required=True, choices=("deepseek", "glm", "nemotron"))
    parser.add_argument("--timeout", type=int, default=1800, help="Seconds (execute only)")
    args = parser.parse_args()

    catalog = json.loads((ROOT / "benchmarks/models.json").read_text(encoding="utf-8"))
    model_id = catalog[args.model]["opencode_model"]
    work = RUNS / args.case / args.model

    if args.action == "prepare":
        if work.exists():
            parser.error(f"{work} already exists; remove it manually before starting a fresh run")
        work.mkdir(parents=True)
        prompt_path, fixture_path, _ = TASKS[args.case]
        shutil.copy2(BENCH / prompt_path, work / "prompt.md")
        if fixture_path:
            shutil.copy2(BENCH / fixture_path, work / "score_detector.py")
        else:
            (work / "score_detector.py").write_text(STUB, encoding="utf-8")
        source_bytes = (work / "score_detector.py").read_bytes()
        manifest = {
            "case": args.case, "model_alias": args.model, "model_id": model_id,
            "baseline_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "prompt_sha256": hashlib.sha256((work / "prompt.md").read_bytes()).hexdigest()
        }
        (work / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Prepared: {work}")
        print(f"Model: {model_id}")
        print(f"Next: python scripts/benchmark.py execute --case {args.case} --model {args.model}")
        print("CAUTION: execute calls a model and may incur API charges.")
        return 0

    if not work.is_dir() or not (work / "manifest.json").exists():
        parser.error("Prepared workspace missing. Run 'prepare' first.")
    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if manifest["model_id"] != model_id or manifest["case"] != args.case:
        parser.error("Manifest mismatch; aborting.")

    if args.action == "execute":
        if args.timeout < 1:
            parser.error("Timeout must be positive.")
        if (work / "opencode.stdout.jsonl").exists():
            parser.error("An execution log exists; do not overwrite first-attempt evidence.")
        if shutil.which("opencode") is None:
            parser.error("opencode CLI not on PATH.")
        command = [
            "opencode", "run", "--agent", "build", "--model", model_id,
            "--format", "json", "--file", "prompt.md",
            "Implement the requirements in prompt.md in this working directory. "
            "Write score_detector.py and your own unittest file. Do not access "
            "independent evaluator files, push, merge, or edit outside this folder.",
        ]
        print(f"Running {args.model} in {work}. API fees and external tools may apply.")
        start = time.monotonic()
        timed_out = False
        try:
            result = subprocess.run(
                command, cwd=work, capture_output=True, timeout=args.timeout
            )
            stdout, stderr, return_code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, return_code = exc.stdout or b"", exc.stderr or b"", 124
            timed_out = True
        (work / "opencode.stdout.jsonl").write_bytes(stdout)
        (work / "opencode.stderr.log").write_bytes(stderr)
        record = {
            "exit_code": return_code, "timeout": timed_out,
            "elapsed_seconds": round(time.monotonic() - start, 2),
            "note": "OpenRouter billed amount must be verified separately."
        }
        (work / "execution.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps(record, indent=2))
        return 0 if return_code == 0 else 1

    _, _, test_names = TASKS[args.case]
    checks = []
    for filename in test_names:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(work) + os.pathsep + env.get("PYTHONPATH", "")
        command = [
            sys.executable, "-m", "unittest", "discover",
            "-s", str(BENCH / "evaluation"), "-p", filename, "-v"
        ]
        result = subprocess.run(
            command, cwd=work, capture_output=True, text=True, env=env, timeout=120
        )
        (work / (filename + ".log")).write_text(
            result.stdout + "\n" + result.stderr, encoding="utf-8"
        )
        checks.append({"suite": filename, "passed": result.returncode == 0,
                       "exit_code": result.returncode})
    report = {
        "case": args.case, "model_alias": args.model,
        "model_id": model_id, "checks": checks,
        "all_passed": all(test["passed"] for test in checks),
        "note": "This does not include OpenRouter billing, reliability, or code review."
    }
    (work / "evaluation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
