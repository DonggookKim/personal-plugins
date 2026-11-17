from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "opencode_delegate.py"
TEST_TEMP_ROOT = os.environ.get("CODEX_TEST_TMPDIR")


def temporary_directory() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)


def write_fake_opencode(root: Path, source: str) -> Path:
    implementation = root / "fake_opencode_impl.py"
    implementation.write_text(source, encoding="utf-8")
    if os.name == "nt":
        launcher = root / "fake-opencode.cmd"
        launcher.write_text(
            f'@"{sys.executable}" "{implementation}" %*\r\n', encoding="utf-8"
        )
    else:
        launcher = root / "fake-opencode"
        launcher.write_text(
            f'#!{sys.executable}\nexec(compile(open({str(implementation)!r}, "rb").read(), '
            f'{str(implementation)!r}, "exec"))\n',
            encoding="utf-8",
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


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
        with temporary_directory() as temporary:
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

    def test_records_missing_opencode_as_preflight_failure(self) -> None:
        with temporary_directory() as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            task = root / "task.json"
            write_task(task)
            output = root / "attempt-001"
            env = os.environ.copy()
            git_binary = shutil.which("git")
            self.assertIsNotNone(git_binary)
            env["PATH"] = str(Path(git_binary).parent)
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
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(result.returncode, 127)
            payload = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["phase"], "preflight")
            self.assertEqual(payload["changed_files"], [])
            self.assertIn("not available", payload["unresolved_issues"][0])

    def test_records_changes_tests_session_and_usage(self) -> None:
        with temporary_directory() as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            (work / "target.txt").write_text("before", encoding="utf-8")
            task = root / "task.json"
            write_task(task)
            fake = write_fake_opencode(
                root,
                "import json\n"
                "from pathlib import Path\n"
                "Path('target.txt').write_text('changed')\n"
                "print(json.dumps({'sessionID': 'session-1', 'cost': 0.25, "
                "'tokens': {'input': 4, 'output': 2}}))\n",
            )
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
        with temporary_directory() as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            (work / "target.txt").write_text("before", encoding="utf-8")
            task = root / "task.json"
            write_task(task)
            fake = write_fake_opencode(
                root,
                "from pathlib import Path\n"
                "Path('target.txt').write_text('changed')\n"
                "Path('outside.txt').write_text('bad')\n",
            )
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
        with temporary_directory() as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            (work / "target.txt").write_text("before", encoding="utf-8")
            task = root / "task.json"
            write_task(task)
            fake = write_fake_opencode(
                root,
                "from pathlib import Path\n"
                "Path('target.txt').write_text('changed')\n"
                "Path('__pycache__').mkdir()\n"
                "Path('__pycache__/generated.pyc').write_text('cache')\n",
            )
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
