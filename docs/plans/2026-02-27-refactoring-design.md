# Simple-Updown 전체 리팩토링 설계

**날짜:** 2026-02-27  
**방식:** 점진적 레이어 리팩토링 (방식 A)  
**범위:** 백엔드 + 프론트엔드 + 인프라 전체

---

## 배경 및 목적

전체 코드 분석 결과 발견된 주요 문제:

- **백엔드:** 스토리지 추상화 파괴 (`r2` 이중 인스턴스 + 직접 참조), JSON DB 스레드 안전성 없음, 다수의 런타임 버그, `app.py` 단일 파일에 789줄 집중
- **프론트엔드:** 디버그 UI 프로덕션 노출, Options API 사용, 공통 로직 중복 (5곳), 다운로드 방식 비효율
- **인프라:** EOL Node.js 16 이미지, PR에서 Docker Hub push, 빌드 캐시 미사용, docker-compose 설정 오류

---

## 단계별 설계

### 단계 1: 백엔드 핵심 구조 개선

#### 1-1. DB를 SQLite(aiosqlite)로 교체

**현재:** `database.py` — JSON 파일 기반, 스레드 안전성 없음, O(n) 탐색  
**변경:** SQLite + aiosqlite — 비동기, 스레드 안전, SHA256 해시 인덱싱

스키마:
```sql
CREATE TABLE files (
    id TEXT PRIMARY KEY,
    file_hash TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER,
    content_type TEXT,
    upload_time TEXT,
    expire_time TEXT,
    expire_minutes INTEGER,
    uploader_ip TEXT,
    md5_hash TEXT,
    sha1_hash TEXT
);
CREATE INDEX idx_file_hash ON files(file_hash);
```

기존 `file_metadata.json` 데이터 마이그레이션 스크립트 포함.

#### 1-2. 스토리지 추상화 완전 수정

**현재 문제:**
```python
storage = LocalStorage() if storage_type == "local" else R2Storage()
r2 = R2Storage()  # STORAGE_TYPE=local이어도 항상 생성됨
# 코드 곳곳에서 r2.upload_file(), r2.get_file_bytes() 직접 참조
```

**변경 후:**
- `r2 = R2Storage()` 전역 인스턴스 제거
- `storage` 하나만 사용
- `LocalStorage`와 `R2Storage`가 완전히 동일한 인터페이스 구현:
  - `upload_file(src_path: str, file_hash: str) -> bool`
  - `download_stream(file_hash: str) -> Generator`
  - `delete_file(file_hash: str) -> bool`
  - `file_exists(file_hash: str) -> bool`
  - `get_file_bytes(file_hash: str) -> bytes`

#### 1-3. 버그 수정 5개

| 버그 | 위치 | 수정 방법 |
|------|------|-----------|
| `load_dotenv()` 호출 순서 | `app.py` 35~41줄 | 스토리지 초기화 전으로 이동 |
| `get_thumbnail` R2 분기 `file_path` 미정의 | `app.py` ~716줄 | R2 분기에서 bytes 기반 처리로 통일 |
| `HTTPException`이 500으로 재포장 | `app.py` `download_file` | `HTTPException` 별도 catch |
| `StreamingResponse` 내부 `HTTPException` | `app.py` `file_streamer` | 스트리밍 전 사전 검증으로 이동 |
| `Content-Disposition` 헤더 인코딩 | `app.py` ~492줄 | RFC 5987 형식 적용 |

#### 1-4. 코드 정리

- `pyshorteners` 미사용 import 및 의존성 제거
- `gc.collect()` 남용 제거 (80MB마다 호출)
- `local_storage.py`의 미사용 메서드 제거 (`save_file`, `save_file_stream`, `get_file_url`, `stream_file`)
- `database.py`의 미사용 `get_by_filename` 메서드 제거
- `r2_storage.py`의 미사용 `hashlib` import 제거

---

### 단계 2: 백엔드 구조 분리

#### 2-1. `app.py` 모듈 분리

```
simple-updown-backend/
├── app.py              # FastAPI 앱 초기화 + 미들웨어 + 스케줄러
├── database.py         # SQLiteDB 클래스
├── local_storage.py    # LocalStorage 클래스
├── r2_storage.py       # R2Storage 클래스
├── utils.py            # 공통 유틸 (format_file_size, is_image_file 등)
└── routers/
    ├── __init__.py
    ├── files.py        # GET /api/files/, DELETE /files/{hash}
    ├── upload.py       # POST /upload/
    ├── download.py     # GET /download/{hash}
    └── thumbnail.py    # GET /thumbnail/{hash}
```

#### 2-2. `list_files` GET에서 DB 수정 제거

- `GET /api/files/` → 목록 조회만 (REST 원칙 준수)
- 고아 파일 정리, 파일 크기 검증 → APScheduler 스케줄러로 이전

#### 2-3. 타입 힌팅 추가

모든 함수 시그니처에 Python 타입 힌팅 추가.

---

### 단계 3: 프론트엔드 리팩토링

#### 3-1. Vue 3 Composition API 전환

두 컴포넌트를 `<script setup>` 방식으로 전환:

```javascript
// 현재 (Options API)
export default {
  data() { return { files: [] } },
  methods: { async fetchFiles() { ... } },
  computed: { filteredFiles() { ... } }
}

// 변경 후 (Composition API)
<script setup>
const files = ref([])
const filteredFiles = computed(() => ...)
async function fetchFiles() { ... }
</script>
```

#### 3-2. 공통 유틸 및 API 레이어 분리

```
simple-updown-frontend/src/
├── composables/
│   ├── useFiles.js       # 파일 목록 관련 로직
│   └── useUpload.js      # 업로드 관련 로직
├── utils/
│   ├── fileUtils.js      # formatFileSize, isImageFile, getFileIcon
│   └── dateUtils.js      # parseUTCDate, isExpiringSoon, getTimeLeft (중복 5곳 통합)
└── api/
    └── filesApi.js       # axios 인스턴스 + API 호출 함수들
```

#### 3-3. 즉시 수정 사항

- 디버그 UI 제거 (`debug-info`, `debug-note` 클래스)
- 주석 처리된 `console.log` 20개+ 제거
- 업로드 실패 시 UI에 오류 표시 (`uploadErrors` 배열 렌더링)
- `uploadedCount` 실패 시에도 증가하는 버그 수정
- 삭제 확인 다이얼로그 추가
- 연도 하드코딩 수정 (`2025` → `new Date().getFullYear()`)
- `copy-alert`/`multi-upload-message` CSS 중복 통합 → `.toast-message`

#### 3-4. 다운로드 직접 링크 방식 변경

```javascript
// 현재: 전체 파일을 Blob으로 메모리에 올림 (대용량 파일 비효율)
const response = await axios.get(`/download/${hash}`, { responseType: 'blob' });

// 변경: 직접 링크로 브라우저 스트리밍 처리
const link = document.createElement('a');
link.href = `/download/${hash}`;
link.download = filename;
link.click();
```

---

### 단계 4: 인프라 개선

#### 4-1. Dockerfile 개선

- `node:16` → `node:20` (EOL 이미지 교체)
- `npm install` → `npm ci` (재현 가능한 빌드)
- BuildKit 캐시 마운트 추가 (pip, npm 빌드 속도 향상)
- uvicorn 멀티워커 설정 (`--workers` 환경변수화, 기본값 `$(nproc)`)
- `Containerfile`의 `--reload` 플래그 제거

#### 4-2. GitHub Actions 개선

- PR에서 Docker Hub push 차단: `push: ${{ github.event_name != 'pull_request' }}`
- 액션 버전 업그레이드: `checkout@v3→v4`, `setup-buildx@v2→v3`, `login@v2→v3`, `build-push@v4→v5`
- GHA 빌드 캐시 추가: `cache-from/to: type=gha`

#### 4-3. docker-compose 개선

- `docker-compose.local.yml`에 `file_metadata` 볼륨 마운트 추가 (재시작 시 데이터 손실 방지)
- 헬스체크 추가 (`GET /api/files/` 활용)
- `docker-compose.yml`의 `STORAGE_TYPE =` 문법 오류 수정

#### 4-4. `.dockerignore` 보강

추가 항목: `node_modules`, `.git`, `__pycache__`, `*.pyc`, `docs/`, `Containerfile`, `*.md`

#### 4-5. `.env_sample` 수정

- `r2_REGION` → `R2_REGION` (대소문자 통일)
- 각 변수에 설명 주석 추가

---

## 성공 기준

- 모든 기존 기능이 동일하게 동작
- 스토리지 타입 전환 시 코드 변경 없이 환경변수만으로 동작
- 프론트엔드에 디버그 정보 노출 없음
- 다운로드가 브라우저 스트리밍 방식으로 동작
- PR에서 Docker Hub에 이미지가 push되지 않음
- 기존 `file_metadata.json` 데이터가 SQLite로 마이그레이션됨

---

## 변경하지 않는 것

- API 엔드포인트 경로 및 응답 형식 (하위 호환성 유지)
- SHA256 해시 기반 파일 저장 방식
- APScheduler 만료 파일 자동 삭제 로직 (위치만 이동)
- 전체 UI/UX 디자인 (기능 버그 수정 제외)
- 인증/권한 시스템 (현재 없음, 추가하지 않음)
