"""실제 산출물을 Backend 코드로 검사하는 로컬 전용 시험. 운영 DB/API는 사용하지 않는다."""

import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from unittest.mock import patch


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(args):
    backend = args.backend.resolve()
    evidence = args.evidence.resolve()
    snapshot = read_json(evidence / "input.json")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=backend, text=True).strip()
    require(sha == snapshot["backend_sha"], "Backend 기준 commit이 다릅니다")
    require(not (backend / ".env").exists(), "운영 환경변수 파일이 있는 checkout은 사용하지 않습니다")
    sys.path.insert(0, str(backend))
    os.environ["DJANGO_SECRET_KEY"] = secrets.token_urlsafe(48)
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    os.environ.pop("DJANGO_SETTINGS_MODULE", None)

    import django
    from django.conf import settings

    require(not settings.configured, "이미 구성된 Django 환경은 사용하지 않습니다")
    base = importlib.import_module("config.settings")
    configuration = {name: getattr(base, name) for name in dir(base) if name.isupper()}
    with tempfile.TemporaryDirectory(prefix="msgctf-consumer-probe-") as temporary:
        configuration.update(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
            MEDIA_ROOT=temporary,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
            ALLOWED_HOSTS=["testserver"],
            DEBUG=True,
            SECURE_SSL_REDIRECT=False,
            RELEASE_POLL_SOURCE_REF="refs/heads/main",
            RELEASE_POLL_GITHUB_TOKEN="",
        )
        settings.configure(**configuration)
        django.setup()

        from django.core.management import call_command
        from django.core.files.storage import default_storage
        from django.db import connections
        from rest_framework.test import APIClient
        from apps.accounts.models import Team, User
        from apps.board.models import Cell, TeamChallengeAccess
        from apps.challenge.models import Challenge
        from apps.instances.models import ChallengeRelease, ChallengeRuntimeConfig, ChallengeUserFileBundle
        from apps.instances.poller import poll_once, register_bundle, validate_bundle_source
        from apps.instances.user_files import poll_user_files_once

        call_command("migrate", verbosity=0, interactive=False)
        require(connections["default"].vendor == "sqlite", "로컬 SQLite 이외 DB는 사용하지 않습니다")
        require(settings.DATABASES["default"]["NAME"] == ":memory:", "메모리 시험 DB가 아닙니다")
        team = Team.objects.create(team_name="local-integration-probe")
        password = secrets.token_urlsafe(24)
        admin = User.objects.create_user(login_id="probe-admin", password=password, nickname="admin", role="ADMIN")
        player = User.objects.create_user(login_id="probe-player", password=password, nickname="player", team=team)

        def client_for(user):
            client = APIClient()
            response = client.post("/api/v1/auth/login", {"login_id": user.login_id, "password": password}, format="json")
            require(response.status_code == 200, "시험 사용자 로그인 실패")
            client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["data"]["access_token"])
            return client

        admin_client, player_client = client_for(admin), client_for(player)
        challenges = {}
        runs, publish_payloads, user_payloads = {}, {}, {}
        publish_artifacts, user_artifacts = [], []
        for index, case in enumerate(snapshot["cases"], 1):
            slug = case["challenge_slug"]
            category = {"pwn": "PWN", "forensic": "FORENSIC", "misc": "MISC"}[slug.split("-")[0]]
            challenge = Challenge.objects.create(challenge_slug=slug, title=slug, category=category,
                difficulty="EASY", score=500, description="로컬 산출물 시험", flag_hash="local-probe-placeholder", is_published=True)
            challenges[slug] = challenge
            cell = Cell.objects.create(cell_index=index, type="CHALLENGE", difficulty="EASY", name=slug)
            TeamChallengeAccess.objects.create(team=team, challenge=challenge, source_cell=cell)
            run_data = case["run"]
            require(run_data["status"] == "completed" and run_data["conclusion"] == "success", "출처 workflow가 성공 상태가 아닙니다")
            runs[run_data["id"]] = run_data

            def artifact_metadata(item):
                return {**item, "expired": False, "workflow_run": {
                    "id": run_data["id"], "head_branch": run_data["head_branch"], "head_sha": run_data["head_sha"]}}

            if case["publish_artifact"]:
                artifact = artifact_metadata(case["publish_artifact"])
                publish_artifacts.append(artifact)
                payload = read_json(evidence / "artifacts" / slug / "publish" / "artifact-v2.json")
                publish_payloads[artifact["id"]] = payload
                validate_bundle_source(artifact, run_data, payload)
            artifact = artifact_metadata(case["user_artifact"])
            user_artifacts.append(artifact)
            directory = evidence / "artifacts" / slug / "user"
            user_payloads[artifact["id"]] = (read_json(directory / "user-files.json"),
                (directory / "user-files.zip").read_bytes() if (directory / "user-files.zip").exists() else None)

        previous = snapshot["previous_release"]
        old_artifact = {**previous["artifact"], "workflow_run": {"id": previous["run"]["id"],
            "head_branch": previous["run"]["head_branch"], "head_sha": previous["run"]["head_sha"]}}
        old_path = evidence / "artifacts/pwn-random6/revision-330" / old_artifact["name"] / "artifact-v2.json"
        old_payload = read_json(old_path)
        validate_bundle_source(old_artifact, previous["run"], old_payload)
        status, old_release = register_bundle(old_payload)
        require(status == "registered", "이전 실제 revision 등록 실패")

        def activate(challenge, release):
            response = admin_client.post(f"/api/v1/admin/challenges/{challenge.pk}/releases/{release.pk}/activate", {}, format="json")
            require(response.status_code == 200, "관리자 릴리스 활성화 실패")

        random_challenge = challenges["pwn-random6"]
        activate(random_challenge, old_release)
        release_downloads = patch("apps.instances.poller.download_bundle", side_effect=lambda artifact, **_: copy.deepcopy(publish_payloads[artifact["id"]]))
        user_downloads = patch("apps.instances.user_files.download_user_files_bundle", side_effect=lambda artifact, **_: copy.deepcopy(user_payloads[artifact["id"]]))

        # GitHub HTTP 계층만 실제 다운로드 파일과 메타데이터로 대체한다. 소비·검증·DB 코드는 Backend 원본을 사용한다.
        with patch("apps.instances.poller.list_artifacts_by_suffix", side_effect=lambda suffix, **_: publish_artifacts if suffix == "-publish-bundle" else user_artifacts), \
             patch("apps.instances.poller.get_workflow_run", side_effect=lambda artifact, **_: runs[artifact["workflow_run"]["id"]]), \
             patch("apps.instances.user_files.get_workflow_run", side_effect=lambda artifact, **_: runs[artifact["workflow_run"]["id"]]), \
             release_downloads as release_download, user_downloads as user_download:
            first_release = poll_once()
            first_user = poll_user_files_once()
            counts_before = (release_download.call_count, user_download.call_count)
            second_release = poll_once()
            second_user = poll_user_files_once()
            require((release_download.call_count, user_download.call_count) == counts_before, "재수집 시 파일을 다시 다운로드했습니다")

        require(first_release["registered"] == 2 and first_release["invalid"] == 0, "실제 릴리스 2개 등록 실패")
        require(first_user["registered"] == 4 and first_user["invalid"] == 0, "참가자 파일 네 종류 등록 실패")
        require(all(value == 0 for value in second_release.values()), "릴리스 재수집 결과가 비어 있지 않습니다")
        require(all(value == 0 for value in second_user.values()), "참가자 파일 재수집 결과가 비어 있지 않습니다")
        random_config = ChallengeRuntimeConfig.objects.get(challenge=random_challenge)
        require(random_config.current_release_id == old_release.pk, "새 revision 등록으로 active가 바뀌었습니다")
        new_release = ChallengeRelease.objects.get(challenge=random_challenge, registry_revision=455)
        require(new_release.registry_revision > old_release.registry_revision, "신규 revision이 아닙니다")
        activate(random_challenge, new_release)

        cases = []
        for case in snapshot["cases"]:
            slug = case["challenge_slug"]
            challenge = challenges[slug]
            if case["runtime_required"]:
                release = ChallengeRelease.objects.get(challenge=challenge, registry_revision=case["registry_revision"])
                source = publish_payloads[case["publish_artifact"]["id"]]
                require(release.cpu_millicores == source["resource_profile"]["cpu_millicores"] and
                    release.memory_mib == source["resource_profile"]["memory_mib"] and
                    release.ephemeral_storage_mib == source["resource_profile"]["ephemeral_storage_mib"], "리소스 DB 보존 실패")
                persisted = {row.name: row for row in release.containers.all()}
                for container in source["workload"]["containers"]:
                    require(persisted[container["name"]].image_ref == container["image"] and
                        persisted[container["name"]].ports == container["ports"], "컨테이너 digest·포트 DB 보존 실패")
                activate(challenge, release)
            bundle = ChallengeUserFileBundle.objects.get(challenge=challenge, registry_revision=case["registry_revision"])
            manifest, archive = user_payloads[case["user_artifact"]["id"]]
            require(bundle.present == manifest["user_files"]["present"], "present DB 보존 실패")
            detail = player_client.get(f"/api/v1/challenges/{challenge.pk}")
            require(detail.status_code == 200, "참가자 문제 조회 실패")
            files = detail.data["data"]["files"]
            row = {"challenge_slug": slug, "registry_revision": case["registry_revision"], "runtime_required": case["runtime_required"],
                "present": bundle.present, "registered": True, "detail_files_count": len(files)}
            if bundle.present:
                require(len(files) == 1, "파일 응답이 누락됐습니다")
                response = player_client.get(files[0]["download_url"])
                require(response.status_code == 200, "참가자 ZIP 다운로드 실패")
                downloaded = b"".join(response.streaming_content)
                response.close()
                require(hashlib.sha256(downloaded).hexdigest() == bundle.sha256, "다운로드 checksum 불일치")
                require(downloaded == archive, "다운로드 ZIP이 발행 파일과 다릅니다")
                access = TeamChallengeAccess.objects.get(team=team, challenge=challenge)
                access.delete()
                denied = player_client.get(files[0]["download_url"])
                require(denied.status_code == 403, "문제 미개방 다운로드가 허용됐습니다")
                row.update(download_status=200, locked_download_status=403, sha256=bundle.sha256, checksum_verified=True,
                    object_key=bundle.object_key, storage_exists=default_storage.exists(bundle.object_key))
            else:
                require(files == [] and not bundle.object_key, "파일 없음 처리 실패")
            cases.append(row)

        report = {"status": "PASS", "backend_sha": sha, "django_version": django.get_version(),
            "scope": "REAL_ACTIONS_ARTIFACTS_LOCAL_BACKEND_CONSUMER", "database": "isolated_in_memory_sqlite", "storage": "temporary_local_filesystem",
            "github_transport_mocked": True, "production_db_modified": False, "gcs_verified": False,
            "runtime_verified": False, "koth_mapping_verified": False, "first_release_poll": first_release, "first_user_poll": first_user,
            "second_release_poll": second_release, "second_user_poll": second_user, "release_download_calls": counts_before[0], "user_download_calls": counts_before[1],
            "previous_active_revision": old_release.registry_revision, "new_revision": new_release.registry_revision,
            "active_preserved_until_admin_activation": True, "admin_activation_verified": True, "cases": cases,
            "participant_file_visibility_policy": "dynamic_active_release_revision; static_latest_revision"}
        connections.close_all()
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = run(args)
    except Exception as error:
        report = {"status": "FAILED", "error_type": type(error).__name__, "production_db_modified": False, "gcs_verified": False}
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        raise
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "backend_sha": report["backend_sha"]}))


if __name__ == "__main__":
    main()
