import unittest

from scripts.render_k3s_smoke_manifest import render_manifest


DIGEST = "sha256:" + "a" * 64
ARTIFACT = {
    "challenge_slug": "pwn-random6",
    "revision": 7,
    "runtime_type": "KUBERNETES",
    "architecture": "AMD64",
    "workload": {
        "containers": [
            {
                "name": "random6",
                "image": f"ghcr.io/msg-ctf/challenges/pwn-random6/random6@{DIGEST}",
                "ports": [{"port": 6666, "public": True}],
            }
        ]
    },
    "resource_profile": {
        "cpu_millicores": 500,
        "memory_mib": 256,
        "ephemeral_storage_mib": 512,
    },
}


class RenderK3sSmokeManifestTests(unittest.TestCase):
    def test_renders_isolated_deployment_and_service_for_digest_image(self):
        manifest = render_manifest(
            ARTIFACT,
            namespace="ci-smoke-pwn-random6-123",
            image_pull_secret="ghcr-pull",
        )

        deployment, service = manifest["items"]
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        pod_spec = deployment["spec"]["template"]["spec"]

        self.assertEqual(deployment["kind"], "Deployment")
        self.assertEqual(deployment["metadata"]["namespace"], "ci-smoke-pwn-random6-123")
        self.assertEqual(container["image"], ARTIFACT["workload"]["containers"][0]["image"])
        self.assertEqual(container["resources"]["limits"]["cpu"], "500m")
        self.assertEqual(container["resources"]["limits"]["memory"], "256Mi")
        self.assertEqual(container["securityContext"]["allowPrivilegeEscalation"], False)
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertFalse(pod_spec["automountServiceAccountToken"])
        self.assertEqual(pod_spec["imagePullSecrets"], [{"name": "ghcr-pull"}])
        self.assertEqual(service["spec"]["ports"], [{"name": "tcp-6666", "port": 6666, "targetPort": 6666, "protocol": "TCP"}])

    def test_rejects_artifact_for_other_runtime(self):
        artifact = dict(ARTIFACT, runtime_type="DOCKER")

        with self.assertRaisesRegex(ValueError, "KUBERNETES"):
            render_manifest(artifact, "ci-smoke-random6-1", "ghcr-pull")

    def test_rejects_artifact_without_public_port(self):
        artifact = dict(ARTIFACT)
        artifact["workload"] = {
            "containers": [
                dict(
                    ARTIFACT["workload"]["containers"][0],
                    ports=[{"port": 6666, "public": False}],
                )
            ]
        }

        with self.assertRaisesRegex(ValueError, "public"):
            render_manifest(artifact, "ci-smoke-random6-1", "ghcr-pull")


if __name__ == "__main__":
    unittest.main()
