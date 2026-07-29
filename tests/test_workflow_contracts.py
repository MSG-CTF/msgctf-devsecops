import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_workflow(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


class WorkflowContractTests(unittest.TestCase):
    def test_challenge_supply_chain_has_required_contract(self):
        path = ROOT / ".github/workflows/challenge-supply-chain.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("workflow_call", workflow["on"])
        inputs = workflow["on"]["workflow_call"]["inputs"]
        self.assertEqual(
            set(inputs),
            {"challenge_path", "revision"},
        )
        self.assertIn("REGISTRY: ghcr.io", text)
        self.assertNotIn("inputs.registry", text)
        self.assertEqual(
            set(workflow["jobs"]),
            {"validate", "build-scan-push", "aggregate"},
        )
        for required in (
            "validate_info_spec.py",
            "Gitleaks",
            "scanners: vuln",
            "scanners: secret",
            "format: cyclonedx",
            "generate_publish_bundle.py",
            "github.run_id",
            "github.run_attempt",
        ):
            self.assertIn(required, text)

    def test_challenge_supply_chain_respects_runtime_ownership(self):
        text = (
            ROOT / ".github/workflows/challenge-supply-chain.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn(":latest", text)
        self.assertNotIn("kubectl", text)
        self.assertNotIn("render_challenge_manifest", text)

    def test_repository_only_exposes_challenge_validation_workflows(self):
        workflows = {
            path.name
            for path in (ROOT / ".github/workflows").glob("*.yml")
        }

        self.assertEqual(
            workflows,
            {"challenge-supply-chain.yml", "pipeline-self-test.yml"},
        )

    def test_pipeline_self_test_calls_reusable_supply_chain(self):
        path = ROOT / ".github/workflows/pipeline-self-test.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("push", workflow["on"])
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertIn(
            "./.github/workflows/challenge-supply-chain.yml",
            text,
        )
        self.assertIn("tests/fixtures/info-valid", text)


if __name__ == "__main__":
    unittest.main()
