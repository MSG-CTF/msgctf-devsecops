import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_publish_bundle import generate_bundle


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
METADATA = {
    "schema_version": "2.0",
    "challenge_slug": "web-notebook",
    "name": "Web Notebook",
    "category": "web",
    "runtime_type": "KUBERNETES",
    "architecture": "AMD64",
    "containers": [
        {
            "name": "web",
            "build": "prob/for_organizer/web",
            "ports": [8080, 9090],
            "expose": True,
        },
        {
            "name": "db",
            "image": "postgres:16",
            "ports": [5432],
            "expose": False,
        },
    ],
    "healthcheck": {"container": "web", "port": 9090, "path": "/healthz"},
    "resource_profile": {
        "cpu_millicores": 700,
        "memory_mib": 768,
        "ephemeral_storage_mib": 1024,
    },
}
RESULTS = [
    {
        "name": "web",
        "image": f"ghcr.io/msg-ctf/challenges/web-notebook/web@{DIGEST_A}",
        "source_digest": DIGEST_A,
        "sbom": "results/web/sbom/web.cdx.json",
        "scan_result": "PASS",
    },
    {
        "name": "db",
        "image": f"ghcr.io/msg-ctf/challenges/web-notebook/db@{DIGEST_B}",
        "source_digest": DIGEST_B,
        "sbom": "results/db/sbom/db.cdx.json",
        "scan_result": "PASS",
    },
]
EVIDENCE_ROOT = Path(__file__).parent / "fixtures" / "publish-evidence"


class GeneratePublishBundleTests(unittest.TestCase):
    def test_generates_runtime_artifact_and_registry_publish_document(self):
        bundle = generate_bundle(METADATA, RESULTS, "abc123", 3, EVIDENCE_ROOT)

        artifact = bundle["artifact"]
        publish = bundle["registry_publish"]
        self.assertEqual(artifact["schema_version"], "2.0")
        self.assertEqual(artifact["revision"], 3)
        self.assertEqual(
            artifact["workload"]["containers"][0]["ports"],
            [
                {"port": 8080, "public": True},
                {"port": 9090, "public": True},
            ],
        )
        self.assertTrue(
            all(
                "@sha256:" in container["image"]
                for container in artifact["workload"]["containers"]
            )
        )
        self.assertEqual(publish["operation"], "publish_revision")
        self.assertTrue(publish["activate"])
        self.assertEqual(publish["revision"], 3)
        self.assertEqual(publish["workload"], artifact["workload"])

    def test_preserves_healthcheck_and_sbom_evidence(self):
        bundle = generate_bundle(METADATA, RESULTS, "abc123", 1, EVIDENCE_ROOT)

        self.assertEqual(
            bundle["artifact"]["workload"]["healthcheck"],
            METADATA["healthcheck"],
        )
        self.assertEqual(
            bundle["artifact"]["evidence"]["containers"][0]["sbom"],
            "results/web/sbom/web.cdx.json",
        )

    def test_never_includes_flag(self):
        metadata = dict(METADATA, flag="msgctf2026{secret}")

        bundle = generate_bundle(metadata, RESULTS, "abc123", 1, EVIDENCE_ROOT)

        self.assertNotIn("msgctf2026", json.dumps(bundle))
        self.assertNotIn('"flag"', json.dumps(bundle))

    def test_rejects_tag_only_image(self):
        results = [dict(RESULTS[0], image="ghcr.io/msg-ctf/web:tag"), RESULTS[1]]

        with self.assertRaisesRegex(ValueError, "digest-pinned"):
            generate_bundle(METADATA, results, "abc123", 1, EVIDENCE_ROOT)

    def test_accepts_digest_image_from_registry_with_port(self):
        results = [
            dict(
                RESULTS[0],
                image=f"registry.internal:5000/challenges/web/web@{DIGEST_A}",
            ),
            RESULTS[1],
        ]

        bundle = generate_bundle(
            METADATA,
            results,
            "abc123",
            1,
            EVIDENCE_ROOT,
        )

        self.assertEqual(
            bundle["artifact"]["workload"]["containers"][0]["image"],
            results[0]["image"],
        )

    def test_rejects_missing_container_result(self):
        with self.assertRaisesRegex(ValueError, "result set"):
            generate_bundle(METADATA, RESULTS[:1], "abc123", 1, EVIDENCE_ROOT)

    def test_rejects_non_pass_scan_result(self):
        results = [dict(RESULTS[0], scan_result="FAIL"), RESULTS[1]]

        with self.assertRaisesRegex(ValueError, "scan_result"):
            generate_bundle(METADATA, results, "abc123", 1, EVIDENCE_ROOT)

    def test_rejects_missing_sbom_reference(self):
        results = [dict(RESULTS[0], sbom=""), RESULTS[1]]

        with self.assertRaisesRegex(ValueError, "SBOM"):
            generate_bundle(METADATA, results, "abc123", 1, EVIDENCE_ROOT)

    def test_rejects_sbom_reference_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "SBOM file"):
                generate_bundle(METADATA, RESULTS, "abc123", 1, Path(temp_dir))

    def test_rejects_non_cyclonedx_sbom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_root = Path(temp_dir)
            for result in RESULTS:
                path = evidence_root / result["sbom"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"bomFormat":"SPDX"}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "CycloneDX"):
                generate_bundle(METADATA, RESULTS, "abc123", 1, evidence_root)

    def test_rejects_non_positive_revision(self):
        with self.assertRaisesRegex(ValueError, "revision"):
            generate_bundle(METADATA, RESULTS, "abc123", 0, EVIDENCE_ROOT)


if __name__ == "__main__":
    unittest.main()
