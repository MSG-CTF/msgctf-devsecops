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

    def test_component_workflow_has_required_contract(self):
        path = ROOT / ".github/workflows/component-cicd.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("workflow_call", workflow["on"])
        self.assertEqual(
            set(workflow["on"]["workflow_call"]["inputs"]),
            {
                "component_name",
                "context",
                "dockerfile",
                "test_command",
                "push_image",
            },
        )
        self.assertIn("REGISTRY: ghcr.io", text)
        self.assertNotIn("inputs.registry", text)
        for required in (
            "Gitleaks",
            "Trivy",
            "format: cyclonedx",
            "packages: write",
            "github.run_id",
            "github.run_attempt",
        ):
            self.assertIn(required, text)
        self.assertNotIn(":latest", text)

    def test_legacy_workflows_are_not_automatic(self):
        challenge_path = ROOT / ".github/workflows/challenge-deployment.yml"
        platform_path = ROOT / ".github/workflows/platform-cicd.yml"
        challenge = load_workflow(challenge_path)
        platform = load_workflow(platform_path)

        self.assertEqual(
            set(challenge["on"]),
            {"workflow_call", "workflow_dispatch"},
        )
        self.assertEqual(set(platform["on"]), {"workflow_dispatch"})
        self.assertNotIn(":latest", challenge_path.read_text(encoding="utf-8"))
        platform_text = platform_path.read_text(encoding="utf-8")
        self.assertNotIn(":latest", platform_text)
        self.assertNotIn("deploy-gke", platform_text)
        self.assertNotIn("kubectl", platform_text)


if __name__ == "__main__":
    unittest.main()
