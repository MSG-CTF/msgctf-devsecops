import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.healthcheck_contract import validate_healthcheck


class HealthcheckContractTests(unittest.TestCase):
    def test_rejects_invalid_unicode_path_without_echoing_it(self):
        path = "/sensitive-value\ud800"
        with self.assertRaisesRegex(ValueError, "healthcheck.path") as raised:
            validate_healthcheck(
                {"container": "web", "port": 8080, "path": path},
                [{"name": "web", "ports": [8080]}],
            )
        self.assertNotIn("sensitive-value", str(raised.exception))

    def test_rejects_unknown_field_without_echoing_secret_values(self):
        with self.assertRaisesRegex(ValueError, "unsupported fields") as raised:
            validate_healthcheck(
                {"container": "web", "port": 8080, "path": "/", "secret-key": "secret-value"},
                [{"name": "web", "ports": [8080]}],
            )
        self.assertNotIn("secret-key", str(raised.exception))
        self.assertNotIn("secret-value", str(raised.exception))

    def test_staged_runner_imports_without_repository_or_site_packages(self):
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("runtime_api_smoke_runner.py", "healthcheck_contract.py"):
                shutil.copyfile(scripts / name, root / name)
            result = subprocess.run(
                [sys.executable, "-S", str(root / "runtime_api_smoke_runner.py"), "--help"],
                cwd=root,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--artifact", result.stdout)
