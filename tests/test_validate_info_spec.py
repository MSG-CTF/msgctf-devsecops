import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.validate_info_spec import container_matrix, validate_spec


FIXTURE = Path(__file__).parent / "fixtures" / "info-valid"


class ValidateInfoSpecTests(unittest.TestCase):
    def test_valid_spec_is_sanitized_and_build_path_is_normalized(self):
        metadata = validate_spec(FIXTURE)

        self.assertEqual(metadata["challenge_slug"], "info-valid")
        self.assertEqual(metadata["runtime_type"], "KUBERNETES")
        self.assertEqual(metadata["architecture"], "AMD64")
        self.assertEqual(metadata["containers"][0]["build"], "prob/for_organizer/web")
        self.assertNotIn("flag", json.dumps(metadata))

    def test_container_matrix_contains_build_and_external_image(self):
        matrix = container_matrix(validate_spec(FIXTURE))

        self.assertEqual(
            matrix,
            {
                "include": [
                    {
                        "name": "web",
                        "source_type": "build",
                        "source": "prob/for_organizer/web",
                    },
                    {
                        "name": "helper",
                        "source_type": "image",
                        "source": "busybox:1.36.1-musl",
                    },
                ]
            },
        )

    def test_static_challenge_without_deployment_has_empty_container_matrix(self):
        raw = self._raw_fixture()
        del raw["deployment"]

        metadata = self._validate_raw(raw)

        self.assertFalse(metadata["is_server"])
        self.assertNotIn("runtime_type", metadata)
        self.assertEqual(container_matrix(metadata), {"include": []})
        self.assertNotIn("flag", json.dumps(metadata))

    def test_server_challenge_is_marked_as_server(self):
        metadata = validate_spec(FIXTURE)

        self.assertTrue(metadata["is_server"])

    def test_rejects_duplicate_container_names(self):
        raw = self._raw_fixture()
        raw["deployment"]["containers"][1]["name"] = "web"

        with self.assertRaisesRegex(ValueError, "container name"):
            self._validate_raw(raw)

    def test_rejects_build_path_outside_challenge_directory(self):
        raw = self._raw_fixture()
        raw["deployment"]["containers"][0]["build"] = "../outside"

        with self.assertRaisesRegex(ValueError, "inside the challenge directory"):
            self._validate_raw(raw)

    def test_rejects_missing_dockerfile(self):
        raw = self._raw_fixture()
        raw["deployment"]["containers"][0]["build"] = "prob/for_organizer/no-dockerfile"

        with self.assertRaisesRegex(ValueError, "Dockerfile"):
            self._validate_raw(raw, empty_build_directory="prob/for_organizer/no-dockerfile")

    def test_rejects_invalid_runtime_type(self):
        raw = self._raw_fixture()
        raw["deployment"]["runtime_type"] = "NOMAD"

        with self.assertRaisesRegex(ValueError, "runtime_type"):
            self._validate_raw(raw)

    def test_rejects_non_lowercase_category(self):
        raw = self._raw_fixture()
        raw["category"] = "Web"

        with self.assertRaisesRegex(ValueError, "category"):
            self._validate_raw(raw)

    def test_rejects_invalid_port(self):
        raw = self._raw_fixture()
        raw["deployment"]["containers"][0]["ports"] = [0]

        with self.assertRaisesRegex(ValueError, "1..65535"):
            self._validate_raw(raw)

    def test_rejects_non_positive_resource(self):
        raw = self._raw_fixture()
        raw["deployment"]["resource_profile"]["memory_mib"] = 0

        with self.assertRaisesRegex(ValueError, "memory_mib"):
            self._validate_raw(raw)

    def test_rejects_external_image_with_latest_tag(self):
        raw = self._raw_fixture()
        raw["deployment"]["containers"][1]["image"] = "postgres:latest"

        with self.assertRaisesRegex(ValueError, "latest"):
            self._validate_raw(raw)

    def test_rejects_external_image_without_tag_or_digest(self):
        raw = self._raw_fixture()
        raw["deployment"]["containers"][1]["image"] = "postgres"

        with self.assertRaisesRegex(ValueError, "tag or digest"):
            self._validate_raw(raw)

    def test_rejects_healthcheck_for_unknown_container(self):
        raw = self._raw_fixture()
        raw["deployment"]["healthcheck"]["container"] = "worker"

        with self.assertRaisesRegex(ValueError, "healthcheck.container"):
            self._validate_raw(raw)

    def _raw_fixture(self):
        return copy.deepcopy(yaml.safe_load((FIXTURE / "info.yaml").read_text()))

    def _validate_raw(self, raw, empty_build_directory=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            challenge = Path(temp_dir) / "challenge"
            challenge.mkdir()
            (challenge / "info.yaml").write_text(
                yaml.safe_dump(raw, allow_unicode=True),
                encoding="utf-8",
            )
            source = FIXTURE / "prob" / "for_organizer" / "web" / "Dockerfile"
            destination = challenge / "prob" / "for_organizer" / "web"
            destination.mkdir(parents=True)
            destination.joinpath("Dockerfile").write_text(
                source.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            if empty_build_directory:
                challenge.joinpath(empty_build_directory).mkdir(parents=True)
            return validate_spec(challenge)


if __name__ == "__main__":
    unittest.main()
