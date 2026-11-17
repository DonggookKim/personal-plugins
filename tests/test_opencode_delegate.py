from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "opencode_delegate.py"


def write_task(path: Path, allowed_paths: list[str] | None = None) -> None:
    path.write_text(
        json.dumps(
            {
                "objective": "Replace the marker text.",
                "scope": ["target.txt"],
                "allowed_paths": allowed_paths or ["target.txt"],
                "constraints": ["Do not commit."],
                "acceptance_criteria": ["target.txt contains changed."],
                "tests": [
                    f'"{sys.executable}" -c "from pathlib import Path; '
                    "assert Path('target.txt').read_text() == 'changed'\""
                ],
            }
        ),
        encoding="utf-8",
    )


class DelegateRunnerTests(unittest.TestCase):
    def test_dry_run_does_not_require_installed_opencode(self) -> None:
        with tempfile.TemporaryDirectory(dir="/mnt/d/CodexTemp/WSL") as temporary:
            root = Path(temporary)
            task = root / "task.json"
            write_task(task)
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--cwd",
                    str(root),
                    "--task-file",
                    str(task),
                    "--model",
                    "openrouter/example/model",
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["command"][-1], "<structured task prompt>")

    def test_records_changes_tests_session_and_usage(self) -> None:
        with tempfile.TemporaryDirectory(dir="/mnt/d/CodexTemp/WSL") as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            (work / "target.txt").write_text("before", encoding="utf-8")
            task = root / "task.json"
            write_task(task)
            fake = root / "fake-opencode"
            fake.write_text(
                "#!/bin/sh\n"
                "printf changed > target.txt\n"
                "printf '%s\\n' '{\"sessionID\":\"session-1\",\"cost\":0.25,"
                "\"tokens\":{\"input\":4,\"output\":2}}'\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            output = root / "attempt-001"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--cwd",
                    str(work),
                    "--task-file",
                    str(task),
                    "--output-dir",
                    str(output),
                    "--opencode-bin",
                    str(fake),
                    "--model",
                    "openrouter/example/model",
                    "--auto",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["changed_files"], ["target.txt"])
            self.assertTrue(payload["tests"][0]["passed"])
            self.assertEqual(payload["usage"]["session_ids"], ["session-1"])
            self.assertEqual(payload["usage"]["observed_cost_total"], 0.25)

    def test_fails_when_worker_changes_disallowed_path(self) -> None:
        with tempfile.TemporaryDirectory(dir="/mnt/d/CodexTemp/WSL") as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            (work / "target.txt").write_text("before", encoding="utf-8")
            task = root / "task.json"
            write_task(task)
            fake = root / "fake-opencode"
            fake.write_text(
                "#!/bin/sh\nprintf changed > target.txt\nprintf bad > outside.txt\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            output = root / "attempt-001"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--cwd",
                    str(work),
                    "--task-file",
                    str(task),
                    "--output-dir",
                    str(output),
                    "--opencode-bin",
                    str(fake),
                    "--skip-tests",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["unauthorized_changes"], ["outside.txt"])

    def test_ignores_python_cache_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(dir="/mnt/d/CodexTemp/WSL") as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            (work / "target.txt").write_text("before", encoding="utf-8")
            task = root / "task.json"
            write_task(task)
            fake = root / "fake-opencode"
            fake.write_text(
                "#!/bin/sh\nprintf changed > target.txt\n"
                "mkdir __pycache__\nprintf cache > __pycache__/generated.pyc\n",
                encoding="utf-8",
            )
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            output = root / "attempt-001"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER),
                    "--cwd",
                    str(work),
                    "--task-file",
                    str(task),
                    "--output-dir",
                    str(output),
                    "--opencode-bin",
                    str(fake),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["changed_files"], ["target.txt"])


if __name__ == "__main__":
    unittest.main()
