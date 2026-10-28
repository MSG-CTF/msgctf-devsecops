import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.execution_settings_contract import validate_env, validate_secret_env
from scripts.generate_publish_bundle import generate_bundle
from scripts.runtime_api_smoke_runner import build_create_request
from scripts.validate_info_spec import validate_spec
from tests.test_generate_publish_bundle import METADATA, RESULTS, EVIDENCE_ROOT, SOURCE_REF, SOURCE_SHA
from tests.test_validate_info_spec import FIXTURE


class ExecutionSettingsContractTests(unittest.TestCase):
    def test_flag_secret_alias_rejects_flag_embedded_in_image_context(self):
        with tempfile.TemporaryDirectory() as directory:
            challenge = Path(directory) / "info-valid"
            challenge.mkdir()
            raw = yaml.safe_load((FIXTURE / "info.yaml").read_text(encoding="utf-8"))
            raw["flag"] = "MSG{private-fixture-must-not-be-published}"
            container = raw["deployment"]["containers"][0]
            container["secret_env"] = {"FLAG": "flag"}
            build = challenge / container["build"]
            build.mkdir(parents=True)
            (build / "Dockerfile").write_text("FROM scratch\nCOPY app.txt /app.txt\n", encoding="utf-8")
            (build / "app.txt").write_text("prefix" + raw["flag"] + "suffix", encoding="utf-8")
            (challenge / "info.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "build context contains the challenge flag") as caught:
                validate_spec(challenge)
            self.assertNotIn(raw["flag"], str(caught.exception))

    def test_info_metadata_and_bundle_preserve_only_general_env_and_secret_names(self):
        with tempfile.TemporaryDirectory() as directory:
            challenge = Path(directory) / "info-valid"
            challenge.mkdir()
            raw = yaml.safe_load((FIXTURE / "info.yaml").read_text(encoding="utf-8"))
            container = raw["deployment"]["containers"][0]
            build = challenge / container["build"]
            build.mkdir(parents=True)
            (build / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            container["env"] = {"APP_MODE": "ctf", "FLAG_PATH": "/tmp/flag"}
            container["secret_env"] = {"FLAG": "flag", "INTERNAL_TOKEN": "internal_token"}
            raw["flag"] = "MSG{private-fixture-must-not-be-published}"
            (challenge / "info.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
            metadata = validate_spec(challenge)
        self.assertEqual(metadata["containers"][0]["secret_env"], container["secret_env"])
        self.assertEqual(metadata["containers"][0]["env"], container["env"])
        self.assertNotIn(raw["flag"], json.dumps(metadata))

        metadata = copy.deepcopy(METADATA)
        metadata["containers"][0].update({"env": container["env"], "secret_env": container["secret_env"]})
        bundle = generate_bundle(metadata, RESULTS, SOURCE_REF, SOURCE_SHA, 7, EVIDENCE_ROOT)
        emitted = bundle["artifact"]["workload"]["containers"][0]
        self.assertEqual(emitted["secret_env"], container["secret_env"])
        self.assertEqual(emitted["env"], container["env"])
        self.assertNotIn(raw["flag"], json.dumps(bundle))

    def test_general_env_reaches_direct_runtime_smoke(self):
        metadata = copy.deepcopy(METADATA)
        metadata["containers"][0]["env"] = {"APP_MODE": "ctf"}
        bundle = generate_bundle(metadata, RESULTS, SOURCE_REF, SOURCE_SHA, 7, EVIDENCE_ROOT)
        request = build_create_request(bundle["artifact"], target_id="local",
            instance_id="00000000-0000-4000-8000-000000000001",
            team_id="00000000-0000-4000-8000-000000000002")
        self.assertEqual(request["workload"]["containers"][0]["env"], {"APP_MODE": "ctf"})
        self.assertEqual(request["isolation_profile"], "WEB")

    def test_direct_ci_smoke_rejects_secret_requirements_instead_of_dropping_them(self):
        metadata = copy.deepcopy(METADATA)
        metadata["containers"][0]["secret_env"] = {"FLAG": "flag"}
        bundle = generate_bundle(metadata, RESULTS, SOURCE_REF, SOURCE_SHA, 7, EVIDENCE_ROOT)
        with self.assertRaisesRegex(ValueError, "Backend release"):
            build_create_request(bundle["artifact"], target_id="local",
                instance_id="00000000-0000-4000-8000-000000000001",
                team_id="00000000-0000-4000-8000-000000000002")

    def test_values_types_names_collisions_and_limits_fail_without_echo(self):
        invalid = (
            {"FLAG":"private-fixture"}, {"SECRET_KEY":"private-fixture"},
            {"APP_MODE":1}, {"APP_MODE":None}, {"lower":"private-fixture"},
            {"APP_MODE":"\x00"}, {"APP_MODE":"x"*4097},
            {f"V{index}":"x" for index in range(33)},
            {f"V{index}":"x"*4096 for index in range(4)},
        )
        for env in invalid:
            with self.subTest(names=list(env)):
                with self.assertRaises(ValueError) as caught:
                    validate_env(env)
                self.assertNotIn("private-fixture",str(caught.exception))
        with self.assertRaises(ValueError):
            validate_secret_env({"APP_MODE":"mode"}, {"APP_MODE":"plain"})
        with self.assertRaises(ValueError):
            validate_secret_env({"FLAG":"other_secret"}, {})
        with self.assertRaises(ValueError):
            validate_secret_env({"FLAG":"MSG{must-not-be-published}"}, {})

    def test_bundle_generator_revalidates_metadata(self):
        metadata = copy.deepcopy(METADATA)
        metadata["containers"][0]["env"] = {"FLAG":"private-fixture"}
        with self.assertRaisesRegex(ValueError,"secret_env"):
            generate_bundle(metadata,RESULTS,SOURCE_REF,SOURCE_SHA,7,EVIDENCE_ROOT)
