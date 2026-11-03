import base64
import json
import unittest
from unittest.mock import patch

from scripts.audit_publication_state import artifact_kind, collect, compare_problem, markdown, pages


class PublicationStateTests(unittest.TestCase):
    def artifact(self, kind="publish", revision=1, **changes):
        return {
            "id": revision, "name": f"web-example-100-1-abcdef-{kind}-bundle",
            "expired": False, "created_at": "2026-10-19T00:00:00Z",
            "run_id": 100, "registry_revision": revision, "source_sha": "old-commit",
            "run_status": "completed", "run_conclusion": "success", **changes,
        }

    def compare(self, rows, dynamic=True, trees=None):
        return compare_problem("web-example", dynamic, "same-tree", rows,
                               trees if trees is not None else {"old-commit": {"web-example": "same-tree"}})

    def test_static_requires_only_user_files(self):
        report = self.compare([self.artifact("user-files")], dynamic=False)
        self.assertEqual(report["status"], "ARTIFACTS_MATCH_PROBLEM_TREE")

    def test_dynamic_requires_both_artifacts(self):
        self.assertEqual(self.compare([self.artifact()])["status"], "MISSING_SUCCESSFUL_ARTIFACT")

    def test_older_commit_with_same_problem_tree_is_usable_evidence(self):
        self.assertEqual(self.compare([self.artifact(), self.artifact("user-files")])["status"], "ARTIFACTS_MATCH_PROBLEM_TREE")

    def test_changed_problem_tree_is_not_current(self):
        report = self.compare([self.artifact(), self.artifact("user-files")], trees={"old-commit": {"web-example": "different"}})
        self.assertEqual(report["status"], "PROBLEM_SOURCE_CHANGED")

    def test_unknown_source_tree_is_not_current(self):
        self.assertEqual(self.compare([self.artifact(), self.artifact("user-files")], trees={})["status"], "PROBLEM_SOURCE_CHANGED")

    def test_expired_artifact_is_rejected(self):
        report = self.compare([self.artifact("user-files", expired=True)], dynamic=False)
        self.assertEqual(report["status"], "MISSING_SUCCESSFUL_ARTIFACT")
        self.assertEqual(len(report["rejected_artifacts"]), 1)

    def test_failed_or_running_workflow_is_rejected(self):
        for changes in ({"run_conclusion": "failure"}, {"run_status": "in_progress", "run_conclusion": None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.compare([self.artifact("user-files", **changes)], dynamic=False)["status"], "MISSING_SUCCESSFUL_ARTIFACT")

    def test_higher_revision_wins_over_later_old_revision_rerun(self):
        older = self.artifact("user-files", revision=1, created_at="2026-10-20T00:00:00Z", source_sha="different")
        newer = self.artifact("user-files", revision=2)
        self.assertEqual(self.compare([older, newer], dynamic=False)["artifacts"]["user-files"]["registry_revision"], 2)

    def test_failed_new_revision_does_not_erase_old_success(self):
        report = self.compare([self.artifact("user-files"), self.artifact("user-files", revision=2, run_conclusion="failure")], dynamic=False)
        self.assertEqual(report["artifacts"]["user-files"]["registry_revision"], 1)
        self.assertEqual(len(report["rejected_artifacts"]), 1)

    def test_other_problem_and_unscoped_names_are_not_matched(self):
        for name in ("web-example-other-100-1-abcdef-publish-bundle", "web-example-publish-bundle", "web-example-100-1-ZZZ-publish-bundle"):
            self.assertIsNone(artifact_kind(name, "web-example"))

    def test_pagination_reads_later_pages(self):
        with patch("scripts.audit_publication_state.github", side_effect=[{"rows": list(range(100))}, {"rows": [100]}]) as api:
            self.assertEqual(len(pages("some-path", "rows")), 101)
            self.assertIn("page=2", api.call_args.args[0])

    def test_markdown_names_evidence_limit(self):
        report = {"source_sha": "a" * 40, "problems": [self.compare([self.artifact("user-files")], dynamic=False)]}
        self.assertIn("배포 성공을 뜻하지 않습니다", markdown(report))
        self.assertIn("정적", markdown(report))

    def test_collect_does_not_publish_flag_or_environment_values(self):
        body = b'name: example\nflag: msgctf2026{do-not-save}\nother: DB_PASSWORD_PRIVATE_VALUE\n'
        responses = [
            {"object": {"sha": "main-commit"}},
            {"tree": [{"path": "web-example/info.yaml", "sha": "blob"}]},
            {"tree": [{"path": "web-example", "type": "tree", "sha": "same-tree"}]},
            {"content": base64.b64encode(body).decode(), "size": len(body)},
        ]
        with patch("scripts.audit_publication_state.github", side_effect=responses), patch("scripts.audit_publication_state.pages", return_value=[]):
            report = collect()
        encoded = json.dumps(report)
        self.assertNotIn("do-not-save", encoded)
        self.assertNotIn("DB_PASSWORD_PRIVATE_VALUE", encoded)
        self.assertEqual(report["counts"]["total"], 1)

    def test_empty_catalog_fails_instead_of_reporting_zero_as_complete(self):
        with patch("scripts.audit_publication_state.github", side_effect=[{"object": {"sha": "main"}}, {"tree": []}]), self.assertRaises(ValueError):
            collect()


if __name__ == "__main__":
    unittest.main()
