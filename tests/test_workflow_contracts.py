import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_workflow(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


class WorkflowContractTests(unittest.TestCase):
    def test_gitleaks_checks_current_files_and_reachable_git_history(self):
        for relative_path in (
            ".github/workflows/challenge-supply-chain.yml",
            ".github/workflows/challenge-branch-validation.yml",
        ):
            with self.subTest(workflow=relative_path):
                workflow = load_workflow(ROOT / relative_path)
                validate = workflow["jobs"]["validate"]
                checkout = next(
                    step
                    for step in validate["steps"]
                    if step.get("name") == "문제 저장소 가져오기"
                )
                scan = next(
                    step
                    for step in validate["steps"]
                    if step.get("name") == "저장소 Gitleaks 검사"
                )
                command = scan["run"]

                self.assertEqual(checkout["with"]["fetch-depth"], "0")
                self.assertIn("gitleaks git", command)
                self.assertIn(
                    '--log-opts="--full-history HEAD --diff-filter=tuxdb"',
                    command,
                )
                self.assertIn("gitleaks dir", command)
                self.assertGreaterEqual(command.count("--redact --verbose"), 2)
                self.assertNotIn("--all", command)

    def test_challenge_supply_chain_has_required_contract(self):
        path = ROOT / ".github/workflows/challenge-supply-chain.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("workflow_call", workflow["on"])
        self.assertNotIn("workflow_dispatch", workflow["on"])
        inputs = workflow["on"]["workflow_call"]["inputs"]
        self.assertEqual(
            set(inputs),
            {
                "challenge_path",
                "revision",
                "devsecops_ref",
                "publish_images",
                "enable_k3s_smoke_deploy",
                "runtime_target_id",
            },
        )
        self.assertEqual(inputs["revision"]["type"], "string")
        self.assertEqual(inputs["devsecops_ref"]["type"], "string")
        self.assertEqual(inputs["devsecops_ref"]["default"], "main")
        self.assertEqual(inputs["publish_images"]["type"], "boolean")
        self.assertEqual(inputs["publish_images"]["default"], "true")
        self.assertEqual(inputs["enable_k3s_smoke_deploy"]["type"], "boolean")
        self.assertEqual(inputs["runtime_target_id"]["type"], "string")
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
        self.assertEqual(
            workflow["jobs"]["validate"]["outputs"].get("artifact_scope"),
            "${{ steps.scope.outputs.artifact_scope }}",
        )
        self.assertEqual(
            workflow["jobs"]["validate"]["outputs"].get("devsecops_sha"),
            "${{ steps.tools.outputs.commit }}",
        )
        self.assertIn("REGISTRY: ghcr.io", text)
        self.assertNotIn("\n      registry:\n", text)
        self.assertNotIn("ref: main", text)
        self.assertNotIn("github.workflow_sha", text)
        self.assertEqual(text.count("ref: ${{ inputs.devsecops_ref }}"), 1)
        self.assertEqual(
            text.count("ref: ${{ needs.validate.outputs.devsecops_sha }}"),
            3,
        )
        self.assertIn(
            'echo "run_tag=${GITHUB_SHA}-${ARTIFACT_SCOPE}"',
            text,
        )
        self.assertEqual(text.count("${{ steps.image.outputs.run_tag }}"), 6)
        self.assertEqual(
            set(workflow["jobs"]),
            {
                "validate",
                "build-scan-push",
                "aggregate",
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
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
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

        metadata_upload = next(
            step
            for step in workflow["jobs"]["validate"]["steps"]
            if step.get("name") == "검증된 metadata 업로드"
        )
        self.assertEqual(
            metadata_upload["with"]["name"],
            "challenge-metadata-${{ steps.scope.outputs.artifact_scope }}",
        )
        container_upload = next(
            step
            for step in workflow["jobs"]["build-scan-push"]["steps"]
            if step.get("name") == "컨테이너 결과 업로드"
        )
        self.assertEqual(
            container_upload["with"]["name"],
            "container-result-${{ needs.validate.outputs.artifact_scope }}-${{ matrix.name }}",
        )
        self.assertIn("uuid.uuid4().hex", text)
        self.assertIn(
            "${{ needs.validate.outputs.artifact_scope }}-publish-bundle",
            text,
        )
        self.assertNotIn("publish_registry", workflow["on"]["workflow_call"]["inputs"])
        self.assertNotIn("publish-registry", workflow["jobs"])
        self.assertNotIn(
            "CHALLENGE_REGISTRY_TOKEN",
            workflow["on"]["workflow_call"].get("secrets", {}),
        )
        self.assertNotIn(
            "CHALLENGE_REGISTRY_URL",
            workflow["on"]["workflow_call"].get("secrets", {}),
        )
        for forbidden in ("Authorization: Bearer", "Idempotency-Key:", "curl --fail-with-body"):
            self.assertNotIn(forbidden, text)
        k3s_download = next(
            step
            for step in workflow["jobs"]["k3s-smoke-deploy"]["steps"]
            if step.get("name") == "발행 bundle 가져오기"
        )
        self.assertEqual(
            k3s_download["with"]["name"],
            "${{ needs.aggregate.outputs.publish_bundle_name }}",
        )
        for required in (
            "pipeline_timing.py start",
            "pipeline_timing.py stop",
            "pipeline_timing.py report",
            "--argjson timing",
        ):
            self.assertIn(required, text)

    def test_branch_validation_can_disable_all_publish_and_deploy_steps(self):
        path = ROOT / ".github/workflows/challenge-supply-chain.yml"
        workflow = load_workflow(path)

        build_steps = workflow["jobs"]["build-scan-push"]["steps"]
        protected_steps = {
            "OCI Registry 로그인",
            "GHCR push 시간 측정 시작",
            "검사한 동일 image 발행",
            "GHCR push 시간 측정 종료 및 보고서 생성",
            "컨테이너 발행 결과 생성",
            "컨테이너 결과 업로드",
        }
        found_steps = set()
        for step in build_steps:
            if step.get("name") in protected_steps:
                found_steps.add(step["name"])
                self.assertIn("inputs.publish_images", step.get("if", ""))
        self.assertEqual(found_steps, protected_steps)

        for job_name in ("aggregate", "k3s-smoke-deploy"):
            self.assertIn(
                "inputs.publish_images",
                workflow["jobs"][job_name].get("if", ""),
            )

    def test_challenge_supply_chain_keeps_production_runtime_ownership(self):
        path = ROOT / ".github/workflows/challenge-supply-chain.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")
        smoke = workflow["jobs"]["k3s-smoke-deploy"]

        self.assertNotIn(":latest", text)
        self.assertNotIn("render_challenge_manifest", text)
        self.assertNotIn("render_k3s_smoke_manifest.py", text)
        self.assertNotIn("kubectl", text)
        self.assertIn("runtime_api_smoke_runner.py", text)
        self.assertIn("inputs.runtime_target_id", text)
        self.assertIn("GHCR_PULL_SECRET_ARN", workflow["on"]["workflow_call"]["secrets"])
        self.assertNotIn("GHCR_PULL_SECRET_ARN", str(smoke))
        self.assertIn(
            "${GITHUB_REPOSITORY_ID}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
            str(smoke),
        )
        self.assertEqual(smoke["permissions"], {"contents": "read", "id-token": "write"})

    def test_branch_validation_workflow_has_no_publish_or_deploy_permissions(self):
        path = ROOT / ".github/workflows/challenge-branch-validation.yml"
        self.assertTrue(path.exists(), "branch 검증 reusable workflow가 필요합니다")
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(
            set(workflow["on"]["workflow_call"]["inputs"]),
            {"challenge_path", "source_ref", "devsecops_ref"},
        )
        self.assertNotIn("secrets", workflow["on"]["workflow_call"])
        self.assertEqual(set(workflow["jobs"]), {"validate", "build-scan"})
        for job in workflow["jobs"].values():
            self.assertEqual(job["permissions"], {"contents": "read"})

        for required in (
            "validate_info_spec.py",
            "Gitleaks",
            "docker/build-push-action@v6",
            "scanners: vuln",
            "scanners: secret",
            "format: cyclonedx",
        ):
            self.assertIn(required, text)
        for forbidden in (
            "docker/login-action",
            "docker push",
            "packages: write",
            "id-token: write",
            "secrets: inherit",
            "generate_publish_bundle.py",
            "CHALLENGE_REGISTRY",
            "runtime_api_smoke_runner.py",
        ):
            self.assertNotIn(forbidden, text)
        self.assertEqual(text.count("ref: ${{ inputs.source_ref }}"), 2)

    def test_repository_only_exposes_challenge_validation_workflows(self):
        workflows = {
            path.name
            for path in (ROOT / ".github/workflows").glob("*.yml")
        }

        self.assertEqual(
            workflows,
            {
                "challenge-branch-validation.yml",
                "challenge-supply-chain.yml",
                "pipeline-self-test.yml",
            },
        )

    def test_pipeline_self_test_calls_reusable_supply_chain(self):
        path = ROOT / ".github/workflows/pipeline-self-test.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertIn("push", workflow["on"])
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertIn(
            "./.github/workflows/challenge-supply-chain.yml",
            text,
        )
        self.assertIn(
            "./.github/workflows/challenge-branch-validation.yml",
            text,
        )
        self.assertIn("tests/fixtures/info-valid", text)
        self.assertIn("tests/fixtures/koth-template", text)
        self.assertEqual(text.count("devsecops_ref: ${{ github.sha }}"), 3)
        self.assertNotIn("publish_registry", text)
        self.assertIn("enable_k3s_smoke_deploy: false", text)
        self.assertIn("id-token: write", text)
        for job_name in ("sample-server-challenge", "koth-challenge"):
            self.assertNotIn("publish_registry", workflow["jobs"][job_name]["with"])
        branch_validation = workflow["jobs"]["branch-validation"]
        self.assertEqual(branch_validation["permissions"], {"contents": "read"})
        self.assertNotIn("secrets", branch_validation)
        self.assertIn("source_ref", branch_validation["with"])
        self.assertEqual(
            branch_validation["with"]["source_ref"],
            "${{ github.sha }}",
        )
        for job_name in ("sample-server-challenge", "koth-challenge"):
            self.assertIn(
                "github.ref == 'refs/heads/main'",
                workflow["jobs"][job_name].get("if", ""),
            )

    def test_caller_example_separates_branch_validation_from_main_publish(self):
        path = ROOT / "docs/challenge-caller-example.yml"
        workflow = load_workflow(path)
        text = path.read_text(encoding="utf-8")

        self.assertEqual(workflow["on"]["push"]["branches"], ["**"])
        self.assertEqual(workflow["on"]["pull_request"]["branches"], ["main"])
        self.assertEqual(
            workflow["concurrency"]["group"],
            "challenge-validation-${{ github.event_name }}-${{ github.event.pull_request.number || inputs.source_ref || github.ref_name }}",
        )
        dispatch = workflow["on"]["workflow_dispatch"]
        self.assertIsInstance(dispatch, dict)
        dispatch_inputs = dispatch["inputs"]
        self.assertEqual(set(dispatch_inputs), {"source_ref"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertIn("github.event.before", text)
        self.assertIn("github.event.pull_request.base.sha", text)
        self.assertIn("git merge-base origin/main", text)
        self.assertNotIn('if [ -n "${{ inputs.source_ref }}" ]; then', text)
        self.assertIn('if [ -n "$SOURCE_REF" ]; then', text)
        self.assertIn("SOURCE_REF: ${{ inputs.source_ref }}", text)
        self.assertIn('target_sha="$(git rev-parse HEAD)"', text)
        self.assertIn('git diff --name-only "$base" "$target_sha"', text)
        self.assertIn(
            'base="$(git merge-base "$PR_BASE_SHA" "$PR_HEAD_SHA")"',
            text,
        )
        self.assertIn('git diff --name-only "$base" "$PR_HEAD_SHA"', text)
        self.assertIn(
            "find . -mindepth 2 -maxdepth 2 -name info.yaml -print",
            text,
        )

        validation = workflow["jobs"]["validate-branch"]
        self.assertEqual(validation["permissions"], {"contents": "read"})
        self.assertNotIn("secrets", validation)
        self.assertRegex(
            validation["uses"],
            r"challenge-branch-validation\.yml@[0-9a-f]{40}$",
        )
        self.assertEqual(
            set(validation["with"]),
            {"challenge_path", "source_ref", "devsecops_ref"},
        )
        self.assertEqual(
            validation["with"]["source_ref"],
            "${{ inputs.source_ref || github.sha }}",
        )

        publish = workflow["jobs"]["publish-main"]
        self.assertEqual(publish["permissions"]["packages"], "write")
        self.assertEqual(publish["permissions"]["id-token"], "write")
        inputs = publish["with"]

        self.assertEqual(inputs["publish_images"], "true")
        self.assertNotIn("publish_registry", inputs)
        self.assertEqual(
            inputs["enable_k3s_smoke_deploy"],
            "${{ vars.ENABLE_RUNTIME_SMOKE == 'true' }}",
        )
        self.assertEqual(inputs["runtime_target_id"], "${{ vars.RUNTIME_TARGET_ID }}")
        self.assertRegex(
            publish["uses"],
            r"challenge-supply-chain\.yml@[0-9a-f]{40}$",
        )
        self.assertNotEqual(publish["secrets"], "inherit")
        self.assertEqual(
            set(publish["secrets"]),
            {
                "AWS_ROLE_TO_ASSUME",
                "AWS_REGION",
                "AWS_K3S_INSTANCE_ID",
                "AWS_CD_ARTIFACT_BUCKET",
            },
        )


if __name__ == "__main__":
    unittest.main()
