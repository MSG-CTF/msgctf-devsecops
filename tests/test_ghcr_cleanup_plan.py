import copy
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.ghcr_cleanup_plan import build_plan, collect_inventory, main


NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
DIGEST = "sha256:" + "a" * 64


def version(number, date="2026-08-01T00:00:00Z", tags=None):
    return {
        "id": number,
        "name": "sha256:" + f"{number:064x}",
        "created_at": date,
        "updated_at": date,
        "metadata": {"package_type": "container", "container": {
            "tags": [f"commit-{number}"] if tags is None else tags,
        }},
    }


def inventory(name="challenges/web-demo/web", versions=None):
    return {
        "schema_version": "1.0", "organization": "MSG-CTF",
        "collected_at": NOW.isoformat(),
        "packages": [{"name": name, "versions": versions or [version(i) for i in range(5, 0, -1)]}],
    }


class GhcrCleanupPlanTests(unittest.TestCase):
    def test_missing_protection_snapshot_never_authorizes_deletion(self):
        result = build_plan(inventory(), now=NOW)
        self.assertFalse(result["deletion_enabled"])
        self.assertEqual(result["status"], "BLOCKED_PENDING_USAGE_CONFIRMATION")
        self.assertEqual(result["counts"]["retained_versions"], 3)
        self.assertEqual(result["counts"]["review_candidates"], 2)
        self.assertTrue(all(not item["deletion_authorized"] for item in result["versions"]))

    def test_recent_updated_version_is_retained_even_if_created_long_ago(self):
        data = inventory()
        data["packages"][0]["versions"][-1]["updated_at"] = "2026-10-04T00:00:00Z"
        result = build_plan(data, now=NOW)
        entry = next(x for x in result["versions"] if x["version_id"] == 1)
        self.assertIn("RECENT_ACTIVITY", entry["reasons"])

    def test_untagged_manifest_is_retained(self):
        data = inventory()
        data["packages"][0]["versions"][-1]["metadata"]["container"]["tags"] = []
        result = build_plan(data, now=NOW)
        self.assertIn("UNTAGGED_MANIFEST", result["versions"][-1]["reasons"])

    def test_koth_versions_are_retained_until_dedicated_usage_contract_exists(self):
        result = build_plan(inventory("challenges/koth-old/service"), now=NOW)
        self.assertEqual(result["counts"]["review_candidates"], 0)
        self.assertTrue(all("KOTH_USAGE_UNCONFIRMED" in x["reasons"] for x in result["versions"]))

    def test_template_package_is_explicitly_test_only_not_real_koth(self):
        result = build_plan(inventory("challenges/koth-template/service"), now=NOW)
        self.assertEqual(result["counts"]["review_candidates"], 2)
        self.assertEqual(result["versions"][0]["package_class"], "SELF_TEST")

    def test_old_platform_packages_are_not_in_challenge_cleanup_scope(self):
        result = build_plan(inventory("msgctf-backend"), now=NOW)
        self.assertEqual(result["counts"]["review_candidates"], 0)
        self.assertTrue(all("OUTSIDE_CHALLENGE_SCOPE" in x["reasons"] for x in result["versions"]))

    def test_protection_list_adds_retention_but_never_asserts_complete_usage(self):
        data = inventory()
        image = "ghcr.io/msg-ctf/challenges/web-demo/web@" + version(1)["name"]
        result = build_plan(data, protected_images=[image], now=NOW)
        self.assertIn("EXPLICIT_PROTECTED_DIGEST", result["versions"][-1]["reasons"])
        self.assertFalse(result["deletion_enabled"])

    def test_cross_package_same_digest_protection_does_not_match_wrong_repository(self):
        image = "ghcr.io/msg-ctf/challenges/other/web@" + version(1)["name"]
        result = build_plan(inventory(), protected_images=[image], now=NOW)
        self.assertNotIn("EXPLICIT_PROTECTED_DIGEST", result["versions"][-1]["reasons"])

    def test_invalid_digest_and_duplicate_versions_fail_closed(self):
        for mutate in (
            lambda x: x["packages"][0]["versions"][0].update(name="latest"),
            lambda x: x["packages"][0]["versions"].append(copy.deepcopy(x["packages"][0]["versions"][0])),
        ):
            with self.subTest(mutate=mutate):
                data = inventory()
                mutate(data)
                with self.assertRaises(ValueError):
                    build_plan(data, now=NOW)

    def test_unknown_or_future_dates_fail_closed(self):
        for date in ("not-a-date", "2026-10-06T00:00:00Z", "2026-08-01T00:00:00"):
            with self.subTest(date=date):
                with self.assertRaises(ValueError):
                    build_plan(inventory(versions=[version(1, date)]), now=NOW)

    def test_missing_tags_or_non_string_tags_fail_closed(self):
        for tags in (None, "tag", [False]):
            data = inventory()
            data["packages"][0]["versions"][0]["metadata"]["container"]["tags"] = tags
            with self.assertRaises(ValueError):
                build_plan(data, now=NOW)

    def test_inventory_from_other_org_and_stale_snapshot_are_rejected(self):
        data = inventory()
        data["organization"] = "another-org"
        with self.assertRaises(ValueError):
            build_plan(data, now=NOW)
        data = inventory()
        data["collected_at"] = "2026-10-03T00:00:00Z"
        with self.assertRaises(ValueError):
            build_plan(data, now=NOW)

    def test_negative_or_boolean_retention_parameters_are_rejected(self):
        for options in ({"keep_latest": 0}, {"keep_latest": True}, {"retain_days": -1}):
            with self.assertRaises(ValueError):
                build_plan(inventory(), now=NOW, **options)

    def test_collector_uses_only_get_and_percent_encodes_package_name(self):
        calls = []
        def api(endpoint):
            calls.append(endpoint)
            return [[{"name": "challenges/web-demo/web"}]] if "package_type" in endpoint else [[version(1)]]
        result = collect_inventory(api=api, now=NOW)
        self.assertEqual(len(result["packages"]), 1)
        self.assertIn("challenges%2Fweb-demo%2Fweb/versions", calls[1])

    def test_empty_packages_and_version_pages_are_handled(self):
        self.assertEqual(collect_inventory(api=lambda _: [[]], now=NOW)["packages"], [])
        result = build_plan(inventory(versions=[version(1)]), now=NOW)
        self.assertEqual(result["counts"]["review_candidates"], 0)

    def test_collector_auth_failure_creates_explicit_failed_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("scripts.ghcr_cleanup_plan.collect_inventory", side_effect=RuntimeError("GHCR_INVENTORY_REQUEST_FAILED")):
                self.assertEqual(main(["--output-dir", tmp]), 1)
            data = Path(tmp, "cleanup-plan.json").read_text()
            self.assertIn("INVENTORY_FAILED", data)
            self.assertNotIn("Bearer", data)

    def test_workflow_has_read_only_permissions_and_no_schedule_or_delete(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.load((root / ".github/workflows/ghcr-cleanup-dry-run.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read", "packages": "read"})
        script = (root / "scripts/ghcr_cleanup_plan.py").read_text()
        self.assertNotIn('"DELETE"', script)
        self.assertNotIn("delete:packages", script)


if __name__ == "__main__":
    unittest.main()
