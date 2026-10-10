import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.audit_execution_settings import audit_challenge, discover_challenges, render_markdown


class ExecutionSettingsAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "web-test"
        self.root.mkdir()
        self.info = {"deployment": {"containers": [{"name": "web"}]}}
        self.write("info.yaml", yaml.safe_dump(self.info))

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def report(self):
        return audit_challenge(self.root)

    def test_compose_reports_names_not_secret_values_and_detects_network_segmentation(self):
        self.write("prob/for_organizer/compose.yaml", yaml.safe_dump({
            "services": {"web": {
                "environment": {"FLAG": "SECRET-CONTENT", "DB_HOST": "secret-host"},
                "command": "echo SECRET-CONTENT",
                "volumes": ["private:/secret"],
                "healthcheck": {"test": ["CMD", "SECRET-CONTENT"]},
                "networks": ["front", "back"],
            }},
            "networks": {"front": {}, "back": {"internal": True}},
        }))
        report = self.report()
        service = report["compose"][0]["services"][0]
        self.assertEqual(service["environment_names"], ["DB_HOST", "FLAG"])
        self.assertEqual(service["networks"], ["back", "front"])
        self.assertIn("command", service["execution_fields"])
        self.assertIn("network_segmentation", report["review_required"])
        self.assertIn("healthcheck", report["review_required"])
        text = json.dumps(report) + render_markdown([report], "a" * 40)
        for secret in ("SECRET-CONTENT", "secret-host", "/secret"):
            self.assertNotIn(secret, text)

    def test_environment_list_and_source_references_report_names_only(self):
        self.write("docker-compose.yml", "services:\n  web:\n    environment:\n      - FLAG=SECRET-CONTENT\n      - DB_HOST\n")
        self.write("prob/for_organizer/app.py", 'import os\nflag = os.environ["FLAG"]\nkey = os.getenv("AUTH_KEY", "SECRET-CONTENT")\n')
        report = self.report()
        self.assertEqual(report["compose"][0]["services"][0]["environment_names"], ["DB_HOST", "FLAG"])
        self.assertEqual([item["name"] for item in report["environment_references"]], ["AUTH_KEY", "FLAG"])
        self.assertNotIn("SECRET-CONTENT", json.dumps(report))

    def test_excludes_participant_files_exploits_and_symlinks(self):
        self.write("prob/for_user/docker-compose.yml", "services: {hidden: {environment: [HIDDEN=1]}}")
        self.write("exploit/solve.py", 'os.getenv("EXPLOIT_KEY")')
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "compose.yaml").write_text("services: {linked: {environment: [LINKED=1]}}")
        (self.root / "prob/for_organizer").mkdir(parents=True)
        (self.root / "prob/for_organizer/link").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.report()["compose"], [])
        self.assertEqual(self.report()["environment_references"], [])

    def test_malformed_yaml_does_not_echo_secret_content(self):
        self.write("compose.yaml", "services: [SECRET-CONTENT: [")
        report = self.report()
        self.assertEqual(report["compose"][0]["error"], "yaml_unparsed")
        self.assertNotIn("SECRET-CONTENT", json.dumps(report))

    def test_existing_healthcheck_is_identified_and_static_is_supported(self):
        self.info["deployment"]["healthcheck"] = {"container": "web", "port": 8080, "path": "/health"}
        self.write("info.yaml", yaml.safe_dump(self.info))
        self.assertTrue(self.report()["info_healthcheck_present"])
        self.write("info.yaml", "name: static\n")
        self.assertFalse(self.report()["is_server"])

    def test_environment_file_is_inspected_without_exposing_values(self):
        self.write("prob/for_organizer/.env", 'FLAG="SECRET-CONTENT"\nexport DB_HOST=private\n')
        report = self.report()
        self.assertEqual([item["name"] for item in report["environment_references"]], ["DB_HOST", "FLAG"])
        self.assertNotIn("SECRET-CONTENT", json.dumps(report))

    def test_repository_template_does_not_hide_actual_challenges(self):
        repository = Path(self.temp.name)
        (repository / "info.yaml").write_text("name: template\n", encoding="utf-8")
        second = repository / "misc-test"
        second.mkdir()
        (second / "info.yaml").write_text("name: static\n", encoding="utf-8")
        self.assertEqual(discover_challenges(repository), [second, self.root])
        self.assertEqual(len([audit_challenge(path) for path in discover_challenges(repository)]), 2)

    def test_discovery_preserves_single_challenge_input(self):
        self.assertEqual(discover_challenges(self.root), [self.root])

    def test_discovery_skips_linked_challenge_and_rejects_linked_root(self):
        repository = Path(self.temp.name)
        link = repository / "web-link"
        link.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(discover_challenges(repository), [self.root])
        with self.assertRaises(ValueError):
            discover_challenges(link)


if __name__ == "__main__":
    unittest.main()
