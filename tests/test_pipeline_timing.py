import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pipeline_timing.py"


class PipelineTimingTests(unittest.TestCase):
    def test_reports_build_scan_push_and_total_seconds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "timing-state.json"
            output = Path(temp_dir) / "timing.json"

            self._run("start", state, "build", 1_000_000_000)
            self._run("stop", state, "build", 3_500_000_000)
            self._run("start", state, "scan", 4_000_000_000)
            self._run("stop", state, "scan", 9_250_000_000)
            self._run("start", state, "push", 10_000_000_000)
            self._run("stop", state, "push", 11_750_000_000)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "report",
                    "--state",
                    str(state),
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                {
                    "build_seconds": 2.5,
                    "scan_seconds": 5.25,
                    "push_seconds": 1.75,
                    "total_seconds": 9.5,
                },
            )

    def test_rejects_clock_moving_before_phase_start(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "timing-state.json"
            self._run("start", state, "build", 2_000_000_000)

            result = self._run("stop", state, "build", 1_000_000_000, check=False)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("before phase start", result.stderr)

    def _run(self, command, state, phase, now_ns, check=True):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                command,
                "--state",
                str(state),
                "--phase",
                phase,
                "--now-ns",
                str(now_ns),
            ],
            check=check,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
