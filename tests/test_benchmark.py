from __future__ import annotations

import importlib.util
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
