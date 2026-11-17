from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "benchmark_runner", ROOT / "scripts" / "benchmark.py"
)
assert SPEC and SPEC.loader
BENCHMARK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCHMARK)


class BenchmarkTests(unittest.TestCase):
    def test_model_aliases_come_from_catalog(self) -> None:
        catalog = BENCHMARK.load_catalog()
        self.assertEqual(set(catalog), {"deepseek", "glm", "nemotron"})
        for entry in catalog.values():
            self.assertTrue(entry["opencode_model"].startswith("openrouter/"))

    def test_task_keeps_evaluator_outside_worker_scope(self) -> None:
        task = BENCHMARK.build_task("stage1", "contract text")
        self.assertEqual(
            task["allowed_paths"],
            ["score_detector.py", "test_score_detector_worker.py"],
        )
        self.assertNotIn("evaluation", " ".join(task["allowed_paths"]))

    def test_delegate_command_uses_upstream_runner_interface(self) -> None:
        command = BENCHMARK.delegate_command(
            Path("/skills/opencode-delegate/scripts/run_worker.py"),
            Path("/work"),
            Path("/work/task.json"),
            "openrouter/example/model",
            90,
            True,
        )
        self.assertIn("run_worker.py", command[1])
        self.assertEqual(command[command.index("--model") + 1], "openrouter/example/model")
        self.assertEqual(command[-1], "--dry-run")

    def test_usage_parser_records_session_cost_and_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "events.jsonl"
            log.write_text(
                json.dumps(
                    {
                        "sessionID": "session-1",
                        "cost": 0.25,
                        "tokens": {"input": 4, "output": 2},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            usage = BENCHMARK.extract_usage(log)
            self.assertEqual(usage["session_ids"], ["session-1"])
            self.assertEqual(usage["observed_cost_total"], 0.25)
            self.assertEqual(usage["observed_tokens"], {"input": 4, "output": 2})


if __name__ == "__main__":
    unittest.main()
