import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.audit_execution_settings import audit_challenge, deployment_requirements, discover_challenges, render_markdown


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

    def test_koth_requirements_preserve_declared_total_without_assigning_replicas(self):
        info = {"category": "koth", "deployment": {
            "runtime_type": "KUBERNETES", "architecture": "AMD64",
            "containers": [{"name": "web"}, {"name": "worker"}],
            "resource_profile": {"cpu_millicores": 6000, "memory_mib": 12288, "ephemeral_storage_mib": 8192},
        }}
        before = copy.deepcopy(info)
        result = deployment_requirements(info)
        self.assertEqual(result["resource_profile"], info["deployment"]["resource_profile"])
        self.assertEqual(result["container_count"], 2)
        self.assertIn("koth_release_mapping", result["review_required"])
        self.assertIn("koth_deployment_and_recovery_owner", result["review_required"])
        self.assertIn("koth_capacity_and_replica_plan", result["review_required"])
        self.assertNotIn("deployment_requirements_incomplete", result["review_required"])
        self.assertNotIn("replicas", result)
        self.assertNotIn("deployment_approved", result)
        self.assertEqual(info, before)

    def test_static_category_does_not_infer_windows_or_require_container_deployment(self):
        result = deployment_requirements({"category": "pwn", "name": "Windows exercise"})
        self.assertIsNone(result["runtime_type"])
        self.assertEqual(result["resource_profile"], {})
        self.assertEqual(result["review_required"], [])
        self.assertNotIn("windows", json.dumps(result).lower())

    def test_vm_requires_execution_contract_without_inferring_operating_system(self):
        result = deployment_requirements({"deployment": {"runtime_type": "VM"}})
        self.assertIn("vm_execution_contract", result["review_required"])
        self.assertIn("deployment_requirements_incomplete", result["review_required"])
        self.assertNotIn("operating_system", result)

    def test_invalid_resource_values_and_unknown_fields_do_not_reach_report(self):
        result = deployment_requirements({
            "category": "SECRET-CONTENT", "flag": "SECRET-CONTENT", "environment": "SECRET-CONTENT",
            "deployment": {"runtime_type": "SECRET-CONTENT", "architecture": "SECRET-CONTENT", "resource_profile": {
                "cpu_millicores": True, "memory_mib": -1, "ephemeral_storage_mib": "SECRET-CONTENT", "secret": "SECRET-CONTENT",
            }},
        })
        self.assertEqual(result["resource_profile"], {})
        self.assertIsNone(result["category"])
        self.assertIsNone(result["runtime_type"])
        self.assertIsNone(result["architecture"])
        self.assertNotIn("SECRET-CONTENT", json.dumps(result))

    def test_bad_typed_enums_are_not_used_as_dictionary_keys(self):
        result = deployment_requirements({"category": [], "deployment": {"runtime_type": {}, "architecture": []}})
        self.assertIsNone(result["runtime_type"])
        self.assertIsNone(result["architecture"])

    def test_deployment_only_does_not_inspect_compose_or_sources(self):
        self.write("compose.yaml", "services: {web: {environment: [FLAG=SECRET-CONTENT]}}")
        self.write("prob/for_organizer/app.py", 'os.getenv("SOURCE_KEY")')
        report = audit_challenge(self.root, deployment_only=True)
        self.assertEqual(report["audit_scope"], "INFO_ONLY")
        self.assertEqual(report["compose"], [])
        self.assertEqual(report["environment_references"], [])
        rendered = render_markdown([report], "a" * 40)
        self.assertIn("명세만 점검", rendered)
        self.assertIn("소스 미발견을 설정이 없다는 증거로 사용하지 않습니다", rendered)
        self.assertNotIn("SECRET-CONTENT", json.dumps(report) + rendered)

    def test_default_audit_continues_inspecting_organizer_sources(self):
        self.write("prob/for_organizer/app.py", 'os.getenv("SOURCE_KEY")')
        report = self.report()
        self.assertEqual(report["audit_scope"], "INFO_AND_ORGANIZER_SOURCES")
        self.assertEqual(report["environment_references"][0]["name"], "SOURCE_KEY")

    def test_windows_participant_executable_does_not_change_execution_contract(self):
        self.write("prob/for_user/WindowsChallenge.exe", "SECRET-CONTENT")
        self.write("info.yaml", "category: rev\n")
        report = self.report()
        self.assertFalse(report["is_server"])
        self.assertEqual(report["deployment_requirements"]["review_required"], [])
        self.assertNotIn("WindowsChallenge", json.dumps(report))

    def test_cli_outputs_sanitized_deployment_only_metadata(self):
        output = Path(self.temp.name) / "output"
        self.write("info.yaml", "category: koth\nflag: SECRET-CONTENT\n")
        script = Path(__file__).resolve().parents[1] / "scripts/audit_execution_settings.py"
        completed = subprocess.run([sys.executable, "-B", str(script), str(self.root), "--source-sha", "a" * 40,
                                    "--output-dir", str(output), "--deployment-only"], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads((output / "execution-settings.json").read_text())
        self.assertEqual(payload["challenges"][0]["audit_scope"], "INFO_ONLY")
        text = (output / "execution-settings.md").read_text() + json.dumps(payload) + completed.stdout + completed.stderr
        self.assertNotIn("SECRET-CONTENT", text)

    def test_markdown_can_render_reports_from_before_requirements_were_added(self):
        report = self.report()
        del report["deployment_requirements"]
        del report["audit_scope"]
        self.assertIn("web-test", render_markdown([report], "a" * 40))


if __name__ == "__main__":
    unittest.main()
