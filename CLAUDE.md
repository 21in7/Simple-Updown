# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Simple-Updown** — 경량 파일 업로드/다운로드 웹 서비스. 사용자가 파일을 업로드하면 SHA256 해시 기반으로 저장되며, 만료 시간 설정 및 자동 삭제 기능을 제공한다. 백엔드는 Python FastAPI, 프론트엔드는 Vue.js 3으로 구성되며, 로컬 파일시스템 또는 Cloudflare R2(S3 호환) 스토리지를 지원한다.

## Commands

```bash
# 프론트엔드 개발 서버
cd simple-updown-frontend && npm run serve

# 프론트엔드 프로덕션 빌드
cd simple-updown-frontend && npm run build

# 프론트엔드 린트
cd simple-updown-frontend && npm run lint

# 백엔드 개발 서버 (로컬 스토리지)
cd simple-updown-backend && STORAGE_TYPE=local uvicorn app:app --reload --port 9000

# 백엔드 개발 서버 (R2 스토리지)
cd simple-updown-backend && STORAGE_TYPE=r2 uvicorn app:app --reload --port 9000

# Docker 빌드 (로컬 스토리지)
docker build --build-arg STORAGE_TYPE=local -t simple-updown:local .

# Docker 빌드 (R2 스토리지)
docker build --build-arg STORAGE_TYPE=r2 -t simple-updown:r2 .

# Docker Compose 실행 (로컬 스토리지)
docker-compose -f docker-compose.local.yml up -d

# Docker Compose 실행 (R2 스토리지)
docker-compose -f docker-compose.r2.yml up -d
```

테스트 프레임워크는 설정되어 있지 않다.

## Architecture

### 전체 구조

멀티스테이지 Docker 빌드로 단일 컨테이너에 프론트엔드 + 백엔드를 함께 패키징한다.

1. **빌드 스테이지** (`node:16`): Vue.js 프론트엔드를 정적 파일로 빌드
2. **런타임 스테이지** (`python:3.12-slim`): FastAPI 백엔드가 빌드된 정적 파일을 서빙

포트 9000에서 FastAPI가 API 요청과 SPA 정적 파일 서빙을 모두 담당한다.

### 백엔드 (`simple-updown-backend/`)

**`app.py`** — FastAPI 메인 애플리케이션:
- `GET /api/files/` — 파일 목록 조회 (만료/고아 파일 자동 정리 포함)
- `POST /upload/` — 파일 업로드 (8MB 청크 스트리밍, SHA256/MD5/SHA1 해시 계산, 만료 시간 설정)
- `GET /download/{file_hash}` — 파일 다운로드 (스트리밍, 만료 체크)
- `DELETE /files/{file_hash}` — 파일 삭제
- `GET /thumbnail/{file_hash}` — 이미지 썸네일 생성 (Pillow, 메모리 캐싱)
- APScheduler: 1분마다 만료 파일 자동 삭제, 1시간마다 고아 파일 정리
- Vue Router history 모드 지원: 모든 비API 경로를 `index.html`로 폴백

**`database.py`** — `FileMetadataDB` 클래스:
- JSON 파일(`file_metadata.json`) 기반 자체 구현 NoSQL
- UUID 기반 문서 ID, 원자적 저장 (임시 파일 → rename)

**`local_storage.py`** — `LocalStorage` 클래스:
- `/app/uploads` 디렉토리에 SHA256 해시명으로 파일 저장
- 스트리밍 복사 최적화

**`r2_storage.py`** — `R2Storage` 클래스:
- boto3로 Cloudflare R2 (S3 호환) 연동

### 프론트엔드 (`simple-updown-frontend/`)

Vue.js 3 + Vue Router 4 SPA.

- `src/App.vue` — 루트 컴포넌트: 헤더 네비게이션, `<router-view>`, 푸터
- `src/router/index.js` — 라우트: `/` → `FileUpload.vue`, `/files` → `FilesList.vue`
- `src/components/FileUpload.vue` — 파일 업로드 UI, 만료 시간 설정
- `src/components/FilesList.vue` — 업로드된 파일 목록, 다운로드/삭제, 썸네일 표시

### 스토리지 추상화

`STORAGE_TYPE` 환경 변수(`local` 또는 `r2`)로 스토리지 백엔드를 선택한다. 두 클래스는 동일한 인터페이스를 구현하므로 `app.py`에서 교체 가능하다.

### 파일 식별

SHA256 해시값을 파일명으로 사용한다. 동일 파일 중복 업로드 시 자동으로 처리된다.

### 만료 관리

업로드 시 만료 시간을 설정할 수 있으며, `-1`은 무제한을 의미한다. APScheduler가 주기적으로 만료된 파일을 자동 삭제한다.

## Environment Variables

R2 스토리지 사용 시 `.env_sample`을 `.env`로 복사하여 설정한다.

```
R2_ENDPOINT_URL=       # Cloudflare R2 엔드포인트
R2_ACCESS_KEY_ID=      # R2 액세스 키 ID
R2_SECRET_ACCESS_KEY=  # R2 시크릿 액세스 키
R2_BUCKET_NAME=        # R2 버킷 이름
r2_REGION=auto         # 리전 (기본값: auto)
```

로컬 스토리지 사용 시 환경 변수 불필요.

## Deployment

### Docker Hub

이미지: `gihyeon21/simple-updown`

태그 규칙:
- `latest`, `local-latest` — 로컬 스토리지 최신 버전
- `r2-latest` — R2 스토리지 최신 버전
- `v[YY.MM].[커밋수]-local` / `v[YY.MM].[커밋수]-r2` — 버전 태그

### GitHub Actions (`.github/workflows/docker-publish.yml`)

`main` 브랜치 push/PR 시 자동 실행:
1. 버전 자동 생성: `v[YY.MM].[커밋수]` 형식
2. 로컬/R2 두 버전을 Docker Hub에 멀티플랫폼(`linux/amd64`, `linux/arm64`) 빌드 및 푸시
3. 필요 시크릿: `DOCKER_HUB_USERNAME`, `DOCKER_HUB_ACCESS_TOKEN`

## Conventions

- 프로젝트 언어: 한국어 (UI 텍스트, 문서, 커밋 메시지)
- Plan 문서는 `docs/` 디렉토리에 작성
- 메모리 최적화: 대용량 파일은 8MB 청크 스트리밍, 명시적 GC 호출 패턴 유지
- 메타데이터에 업로더 IP는 앞 2옥텟만 저장 (프라이버시 보호)

## Release & Versioning

버전 형식: `v[YY.MM].[커밋수]` (GitHub Actions에서 자동 생성)

수동 빌드 시 변경 성격에 따라 커밋 메시지로 구분:
- **Breaking change**: 하위 호환성 깨지는 변경
- **Feature**: 새 기능 추가
- **Fix**: 버그 수정, 텍스트/스타일 변경

## Workflow Rules

- Plan이 있으면 내용을 `docs/plan.md`에 추가
- 기능 로직 변경 시 `README.md` 업데이트
