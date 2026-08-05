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
            {"challenge_path", "revision", "enable_k3s_smoke_deploy"},
        )
        self.assertEqual(inputs["revision"]["type"], "string")
        self.assertEqual(inputs["enable_k3s_smoke_deploy"]["type"], "boolean")
        self.assertIn("REGISTRY: ghcr.io", text)
        self.assertNotIn("inputs.registry", text)
        self.assertEqual(
            set(workflow["jobs"]),
            {"validate", "build-scan-push", "aggregate", "k3s-smoke-deploy"},
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

    def test_challenge_supply_chain_keeps_production_runtime_ownership(self):
        text = (
            ROOT / ".github/workflows/challenge-supply-chain.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn(":latest", text)
        self.assertNotIn("render_challenge_manifest", text)
        self.assertIn("K3s smoke", text)
        self.assertIn("Runtime을 대체하지", (ROOT / "docs/aws-k3s-cd-smoke.md").read_text(encoding="utf-8"))

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
        self.assertEqual(workflow["permissions"]["id-token"], "write")
        self.assertIn(
            "./.github/workflows/challenge-supply-chain.yml",
            text,
        )
        self.assertIn("tests/fixtures/info-valid", text)
        self.assertIn("enable_k3s_smoke_deploy: false", text)
        self.assertIn("id-token: write", text)


if __name__ == "__main__":
    unittest.main()
