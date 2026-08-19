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
                "publish_registry",
                "enable_k3s_smoke_deploy",
            },
        )
        self.assertEqual(inputs["revision"]["type"], "string")
        self.assertEqual(inputs["publish_registry"]["type"], "boolean")
        self.assertEqual(inputs["publish_registry"]["default"], "false")
        self.assertEqual(inputs["enable_k3s_smoke_deploy"]["type"], "boolean")
        outputs = workflow["on"]["workflow_call"]["outputs"]
        self.assertEqual(
            set(outputs),
            {"challenge_slug", "publish_bundle_name"},
        )
        self.assertEqual(
            outputs["challenge_slug"]["value"],
            "${{ jobs.aggregate.outputs.challenge_slug }}",
        )
        self.assertEqual(
            outputs["publish_bundle_name"]["value"],
            "${{ jobs.aggregate.outputs.publish_bundle_name }}",
        )
        aggregate_outputs = workflow["jobs"]["aggregate"]["outputs"]
        self.assertEqual(
            aggregate_outputs["publish_bundle_name"],
            "${{ steps.summary.outputs.bundle_name }}",
        )
        self.assertIn("REGISTRY: ghcr.io", text)
        self.assertNotIn("\n      registry:\n", text)
        self.assertNotIn("ref: main", text)
        self.assertEqual(text.count("ref: ${{ github.workflow_sha }}"), 3)
        self.assertEqual(
            set(workflow["jobs"]),
            {
                "validate",
                "build-scan-push",
                "aggregate",
                "publish-registry",
                "k3s-smoke-deploy",
            },
        )
        for required in (
            "validate_info_spec.py",
            "Gitleaks",
            "scanners: vuln",
            "scanners: secret",
            "format: cyclonedx",
            "generate_publish_bundle.py",
            "render_publish_summary.py",
            "GITHUB_STEP_SUMMARY",
            "github.run_id",
            "github.run_attempt",
        ):
            self.assertIn(required, text)

        upload = next(
            step
            for step in workflow["jobs"]["aggregate"]["steps"]
            if step.get("name") == "Atomic Publish bundle 업로드"
        )
        self.assertEqual(upload["uses"], "actions/upload-artifact@v4")
        self.assertEqual(upload["with"]["retention-days"], "90")
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        self.assertEqual(
            upload["with"]["name"],
            "${{ steps.summary.outputs.bundle_name }}",
        )

        publish = workflow["jobs"]["publish-registry"]
        self.assertEqual(publish["needs"], ["aggregate"])
        self.assertIn("inputs.publish_registry", publish["if"])
        self.assertEqual(publish["permissions"], {"contents": "read"})
        self.assertIn("CHALLENGE_REGISTRY_TOKEN", workflow["on"]["workflow_call"]["secrets"])
        self.assertIn("CHALLENGE_REGISTRY_URL", workflow["on"]["workflow_call"]["secrets"])

        publish_run = next(
            step["run"]
            for step in publish["steps"]
            if step.get("name") == "Challenge Registry revision 등록"
        )
        validation_run = next(
            step["run"]
            for step in publish["steps"]
            if step.get("name") == "Challenge Registry 연결 설정 검증"
        )
        self.assertIn("https://", validation_run)
        for required in (
            "registry-publish.json",
            "Authorization: Bearer",
            "Idempotency-Key:",
            "sha256sum dist/registry-publish.json",
            "--fail-with-body",
            "--retry 3",
        ):
            self.assertIn(required, publish_run)

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
        self.assertIn("publish_registry: false", text)
        self.assertIn("enable_k3s_smoke_deploy: false", text)
        self.assertIn("id-token: write", text)


if __name__ == "__main__":
    unittest.main()
