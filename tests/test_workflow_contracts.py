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
            {
                "challenge_path",
                "revision",
                "enable_k3s_smoke_deploy",
                "source_repository",
                "source_ref",
                "publish_image",
            },
        )
        self.assertEqual(inputs["revision"]["type"], "string")
        self.assertEqual(inputs["enable_k3s_smoke_deploy"]["type"], "boolean")
        self.assertEqual(inputs["publish_image"]["type"], "boolean")
        self.assertEqual(inputs["publish_image"]["default"], "true")
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

    def test_challenge_supply_chain_supports_external_dry_run(self):
        path = ROOT / ".github/workflows/challenge-supply-chain.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        inputs = workflow["on"]["workflow_call"]["inputs"]
        self.assertEqual(inputs["source_repository"]["default"], "")
        self.assertEqual(inputs["source_ref"]["default"], "")
        self.assertIn("CHALLENGE_REPOSITORY_TOKEN", workflow["on"]["workflow_call"]["secrets"])
        self.assertIn("inputs.source_repository", text)
        self.assertIn("inputs.source_ref", text)
        self.assertIn("inputs.publish_image", text)
        self.assertIn("inputs.publish_image &&", text)

    def test_public_external_repository_uses_anonymous_read_only_checkout(self):
        path = ROOT / ".github/workflows/challenge-supply-chain.yml"
        text = path.read_text(encoding="utf-8")

        self.assertIn("외부 공개 문제 저장소 가져오기", text)
        self.assertIn("git clone --no-checkout", text)
        self.assertIn("env.HAS_CHALLENGE_REPOSITORY_TOKEN != 'true'", text)
        self.assertIn("외부 비공개 문제 저장소 가져오기", text)
        self.assertIn("env.HAS_CHALLENGE_REPOSITORY_TOKEN == 'true'", text)

    def test_external_challenge_smoke_workflow_uses_dry_run(self):
        path = ROOT / ".github/workflows/external-challenge-smoke.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertIn("pull_request", workflow["on"])
        self.assertEqual(set(workflow["jobs"]), {"pwn-random6"})
        self.assertEqual(
            workflow["jobs"]["pwn-random6"]["permissions"],
            {
                "contents": "read",
                "packages": "write",
                "security-events": "write",
                "id-token": "write",
            },
        )
        self.assertIn("./.github/workflows/challenge-supply-chain.yml", text)
        self.assertIn("MSG-CTF/2026_MSG_CTF", text)
        self.assertIn("pwn-random6", text)
        self.assertIn("publish_image: false", text)
        self.assertNotIn("CHALLENGE_REPOSITORY_TOKEN", text)

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
            {
                "challenge-supply-chain.yml",
                "external-challenge-smoke.yml",
                "pipeline-self-test.yml",
            },
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
