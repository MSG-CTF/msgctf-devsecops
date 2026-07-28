# 플랫폼 컴포넌트 CI 호출 예시

각 팀 저장소는 실제 테스트 명령과 Docker build context를 지정해 공통 workflow를 호출합니다.

## Django Backend

```yaml
name: Backend CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  ci:
    permissions:
      contents: read
      packages: write
      security-events: write
    uses: MSG-CTF/msgctf-devsecops/.github/workflows/component-cicd.yml@main
    with:
      component_name: backend
      context: .
      dockerfile: Dockerfile
      test_command: python manage.py test
      push_image: ${{ github.event_name == 'push' }}
```

## Instance Scheduler

```yaml
name: Scheduler CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  ci:
    permissions:
      contents: read
      packages: write
      security-events: write
    uses: MSG-CTF/msgctf-devsecops/.github/workflows/component-cicd.yml@main
    with:
      component_name: scheduler
      context: .
      dockerfile: Dockerfile
      test_command: ./gradlew test
      push_image: ${{ github.event_name == 'push' }}
```
