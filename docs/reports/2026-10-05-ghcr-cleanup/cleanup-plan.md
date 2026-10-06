# GHCR 이미지 버전 정리 검토

기준: `2026-10-05T11:49:40.285888+00:00`

실제 삭제는 수행하지 않았습니다. 후보는 사용 중이 아니라는 뜻이 아닙니다.

- 패키지 39개 / 버전 110개
- 보존 103개 / 추가 검토 7개
- 최신 3개는 image version 기준이며 release revision 수와 같지 않습니다.

## 검토 후보

| 패키지 | version ID | digest | tag |
|---|---:|---|---|
| challenges/koth-template/service | 1173829039 | `sha256:2e36d81962888eb29d8a467b94eb83df29ce0af5b9c798dd2f6d031f0271d773` | 8cf8892588ca43fab2fd57c16d32b8791cac6b8b-32959545593-1-cec5aef86583474cb0516c72297c7b75 |
| challenges/koth-template/service | 1170973802 | `sha256:58dbaa889bbb6c77a22145d0138e98456e1bcf7d4ea766207bd66954cc0a6a04` | 4aea21147d4dafe214f4a4e69016361dfc1c667c-32876556248-1-74ddbfc6c4fa4d6ea3d76e366dc097b0 |
| challenges/koth-template/service | 1165345465 | `sha256:fad36dab3852951fade10ccfd8a804c632eaf5c978442c043ca6e458080edfd6` | 0fbfbfda9e63936392158f54fb5c1db2b3d84db4-32723330120-1-8fdaba6c0855402fa764a3ccc4501158 |
| challenges/koth-template/service | 1165326823 | `sha256:4c3df73a496cce072f065fda7d6765223894d786b68a17e31d03e14debe3db55` | ebf1cce68047a5a8819bdac3f511749dffe86413-32722884352-1-95c19b7704ad4182b476e87dcb50ca44 |
| challenges/koth-template/service | 1165282103 | `sha256:23b46a231f1933d811207b7395cba2684d7becf6a1e758b6b8de51726131864f` | 6eae0c7f4f09072a4adeb65d79341771741908d0-32721810592-1-5124dd74736240d5a90467b3e994f238 |
| challenges/koth-template/service | 1165202164 | `sha256:ea34aadc65f2145a21ba0b95bbc2b258bf0095a0ba28fd02600f5285ca961ea4` | 9c0088f1ede9ccc4a9226466da21bb38c26f9d03-32719785974-1-f813a10e3d6c47d5b78377515c80fb62 |
| challenges/koth-template/service | 1164962537 | `sha256:02d0eecadba943dfaf7d8eb83d872d922378010ed8912ef7390d9105f09e1002` | 647149e6da79ccb8cfc840a6a510ddb1a07e1939-32713627303-1-dd1990694a5f48c58a6229551e3f40da |

## 실제 삭제 전에 필요한 자료

- Backend active release·rollback digest의 최신 전체 목록
- Scheduler/Runtime 실행 중 인스턴스 digest의 최신 전체 목록
- KOTH 별도 사용·rollback digest 목록
- OCI index/manifest 참조 관계 확인과 관리자 승인
