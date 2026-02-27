# Simple-Updown 전체 리팩토링 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simple-Updown 프로젝트의 백엔드(FastAPI), 프론트엔드(Vue 3), 인프라(Docker/CI) 전체를 점진적으로 리팩토링하여 버그를 제거하고 유지보수 가능한 구조로 개선한다.

**Architecture:** 4단계 점진적 리팩토링. 단계 1에서 백엔드 핵심 버그와 DB 교체, 단계 2에서 백엔드 모듈 분리, 단계 3에서 프론트엔드 Composition API 전환 및 공통 로직 분리, 단계 4에서 인프라 개선. 각 단계 완료 후 서비스가 동작 가능한 상태를 유지한다.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, APScheduler, Pillow, Vue 3 (Composition API / `<script setup>`), axios, Docker, GitHub Actions

---

## 단계 1: 백엔드 핵심 구조 개선

### Task 1-1: `load_dotenv()` 호출 순서 수정 + 미사용 코드 제거

**Files:**
- Modify: `simple-updown-backend/app.py`
- Modify: `simple-updown-backend/requirements.txt`

**Step 1: `app.py` 상단 수정**

`app.py` 1~45줄을 다음과 같이 수정한다:

```python
import os
from dotenv import load_dotenv

# 반드시 스토리지 초기화 전에 호출
load_dotenv()

storage_type = os.getenv("STORAGE_TYPE", "local")

from local_storage import LocalStorage
from r2_storage import R2Storage

if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

# r2 = R2Storage() 전역 인스턴스 제거 (이 줄 삭제)
```

**Step 2: 미사용 import 제거**

`app.py`에서 다음 줄 삭제:
```python
import pyshorteners  # 삭제
```

**Step 3: `requirements.txt`에서 `pyshorteners` 제거**

```
pyshorteners==1.0.1  # 이 줄 삭제
```

**Step 4: 서버 기동 확인**

```bash
cd simple-updown-backend
STORAGE_TYPE=local uvicorn app:app --reload --port 9000
```

Expected: 서버 정상 기동, `pyshorteners` 관련 에러 없음

**Step 5: Commit**

```bash
git add simple-updown-backend/app.py simple-updown-backend/requirements.txt
git commit -m "fix: load_dotenv 호출 순서 수정 및 미사용 pyshorteners 제거"
```

---

### Task 1-2: 스토리지 추상화 수정 — `r2` 직접 참조 제거

**Files:**
- Modify: `simple-updown-backend/app.py`
- Modify: `simple-updown-backend/local_storage.py`
- Modify: `simple-updown-backend/r2_storage.py`

**Step 1: `LocalStorage`와 `R2Storage` 인터페이스 통일**

`local_storage.py`에 다음 메서드가 없으면 추가한다:
```python
def get_file_bytes(self, file_hash: str) -> bytes:
    """썸네일 생성용 파일 전체 바이트 반환"""
    file_path = os.path.join(self.upload_dir, file_hash)
    if not os.path.exists(file_path):
        return b""
    with open(file_path, 'rb') as f:
        return f.read()

def file_exists(self, file_hash: str) -> bool:
    file_path = os.path.join(self.upload_dir, file_hash)
    return os.path.exists(file_path)
```

`r2_storage.py`에 `file_exists` 메서드 추가:
```python
def file_exists(self, object_name: str) -> bool:
    try:
        self.s3_client.head_object(Bucket=self.bucket_name, Key=object_name)
        return True
    except ClientError:
        return False
```

**Step 2: `app.py`에서 `r2` 직접 참조를 `storage`로 교체**

`app.py` 전체에서 다음 패턴을 찾아 교체한다:

```python
# 변경 전
if storage_type == "local":
    upload_success = storage.upload_file(temp_file_path, file_hash)
else:
    upload_success = r2.upload_file(temp_file_path, file_hash)

# 변경 후
upload_success = storage.upload_file(temp_file_path, file_hash)
```

`r2.get_file_bytes()`, `r2.delete_file()`, `r2.upload_file()` 등 모든 `r2.` 직접 참조를 `storage.`로 교체한다.

**Step 3: `r2 = R2Storage()` 전역 인스턴스 제거**

`app.py`에서 다음 줄 삭제:
```python
r2 = R2Storage()
```

**Step 4: 동작 확인**

```bash
cd simple-updown-backend
STORAGE_TYPE=local uvicorn app:app --reload --port 9000
# 파일 업로드, 다운로드, 삭제 테스트
curl -X POST http://localhost:9000/upload/ -F "file=@/tmp/test.txt" -F "expire_in_minutes=60"
```

Expected: 업로드/다운로드/삭제 정상 동작

**Step 5: Commit**

```bash
git add simple-updown-backend/app.py simple-updown-backend/local_storage.py simple-updown-backend/r2_storage.py
git commit -m "refactor: 스토리지 추상화 수정 — r2 직접 참조 제거, storage 단일 인터페이스 사용"
```

---

### Task 1-3: 런타임 버그 5개 수정

**Files:**
- Modify: `simple-updown-backend/app.py`

**Step 1: `HTTPException`이 500으로 재포장되는 버그 수정**

`download_file` 엔드포인트의 만료 처리 부분:
```python
# 변경 전
try:
    if current_time > expire_time:
        ...
        raise HTTPException(status_code=404, detail="File expired and deleted")
except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# 변경 후
try:
    if current_time > expire_time:
        ...
        raise HTTPException(status_code=404, detail="File expired and deleted")
except HTTPException:
    raise  # HTTPException은 그대로 전파
except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
```

**Step 2: `StreamingResponse` 내부 `HTTPException` 수정**

`file_streamer` 제너레이터 내부에서 `HTTPException`을 raise하는 코드를 스트리밍 시작 전 사전 검증으로 이동:
```python
# download_file 엔드포인트에서 스트리밍 전 파일 존재 확인
file_doc = None
for doc_id, metadata in db.list_all().items():
    if metadata.get('hash', {}).get('sha256') == file_hash:
        file_doc = (doc_id, metadata)
        break

if file_doc is None:
    raise HTTPException(status_code=404, detail="File not found")

# 이후 StreamingResponse 반환
```

**Step 3: `get_thumbnail` R2 분기 `file_path` 미정의 버그 수정**

R2 분기에서 `file_path` 대신 bytes 기반으로 처리:
```python
if storage_type == "local":
    file_path = os.path.join(storage.upload_dir, file_hash)
    with Image.open(file_path) as img:
        img_format = img.format or 'JPEG'
        # ...
else:
    img_bytes = storage.get_file_bytes(file_hash)
    if not img_bytes:
        raise HTTPException(status_code=404, detail="File not found")
    with Image.open(io.BytesIO(img_bytes)) as img:
        img_format = img.format or 'JPEG'
        # ...
```

**Step 4: `Content-Disposition` 헤더 파일명 인코딩 수정**

```python
# 변경 전
"Content-Disposition": f"attachment; filename={filename}"

# 변경 후
from urllib.parse import quote
encoded_filename = quote(filename, safe='')
"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
```

**Step 5: `gc.collect()` 남용 제거**

업로드 청크 처리 루프에서 `gc.collect()` 호출 제거:
```python
# 변경 전
if chunk_count % 10 == 0:
    del chunk
    gc.collect()

# 변경 후 (gc.collect() 제거, del chunk도 불필요)
pass
```

`import gc` 줄도 삭제한다.

**Step 6: 동작 확인**

```bash
# 만료된 파일 다운로드 시 404 반환 확인
# 한글 파일명 다운로드 시 Content-Disposition 헤더 확인
curl -I http://localhost:9000/download/{file_hash}
```

**Step 7: Commit**

```bash
git add simple-updown-backend/app.py
git commit -m "fix: HTTPException 재포장 버그, 썸네일 R2 버그, Content-Disposition 인코딩, gc.collect 제거"
```

---

### Task 1-4: JSON DB를 SQLite(aiosqlite)로 교체

**Files:**
- Create: `simple-updown-backend/database.py` (전면 재작성)
- Create: `simple-updown-backend/migrate_db.py` (마이그레이션 스크립트)
- Modify: `simple-updown-backend/requirements.txt`
- Modify: `simple-updown-backend/app.py`

**Step 1: `aiosqlite` 의존성 추가**

```
# requirements.txt에 추가
aiosqlite==0.20.0
```

**Step 2: `database.py` 전면 재작성**

```python
import aiosqlite
import asyncio
import uuid
import json
import os
from typing import Optional, Dict, Any, List, Tuple

DB_PATH = os.getenv("DB_PATH", "/app/data/file_metadata.db")

class FileMetadataDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS files (
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
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON files(file_hash)")
            await db.commit()

    async def insert(self, metadata: Dict[str, Any]) -> str:
        doc_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO files (id, file_hash, file_name, file_size, content_type,
                    upload_time, expire_time, expire_minutes, uploader_ip, md5_hash, sha1_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                metadata.get('hash', {}).get('sha256'),
                metadata.get('file_name'),
                metadata.get('file_size'),
                metadata.get('content_type'),
                metadata.get('upload_time'),
                metadata.get('expire_time'),
                metadata.get('expire_minutes'),
                metadata.get('uploader_ip'),
                metadata.get('hash', {}).get('md5'),
                metadata.get('hash', {}).get('sha1'),
            ))
            await db.commit()
        return doc_id

    async def get_by_hash(self, file_hash: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM files WHERE file_hash = ?", (file_hash,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return row['id'], self._row_to_metadata(row)

    async def list_all(self) -> Dict[str, Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM files") as cursor:
                rows = await cursor.fetchall()
                return {row['id']: self._row_to_metadata(row) for row in rows}

    async def delete(self, doc_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM files WHERE id = ?", (doc_id,))
            await db.commit()

    async def update_filename(self, doc_id: str, file_name: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE files SET file_name = ? WHERE id = ?", (file_name, doc_id)
            )
            await db.commit()

    def _row_to_metadata(self, row) -> Dict[str, Any]:
        return {
            'file_name': row['file_name'],
            'file_size': row['file_size'],
            'content_type': row['content_type'],
            'upload_time': row['upload_time'],
            'expire_time': row['expire_time'],
            'expire_minutes': row['expire_minutes'],
            'uploader_ip': row['uploader_ip'],
            'hash': {
                'sha256': row['file_hash'],
                'md5': row['md5_hash'],
                'sha1': row['sha1_hash'],
            }
        }
```

**Step 3: 마이그레이션 스크립트 작성**

`simple-updown-backend/migrate_db.py`:
```python
"""기존 file_metadata.json을 SQLite DB로 마이그레이션"""
import json
import asyncio
import os
import sys

async def migrate(json_path: str, db_path: str):
    if not os.path.exists(json_path):
        print(f"마이그레이션할 JSON 파일 없음: {json_path}")
        return

    from database import FileMetadataDB
    db = FileMetadataDB(db_path)
    await db.init()

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    count = 0
    for doc_id, metadata in data.items():
        try:
            await db.insert(metadata)
            count += 1
        except Exception as e:
            print(f"  건너뜀 (doc_id={doc_id}): {e}")

    print(f"마이그레이션 완료: {count}개 파일")

if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "file_metadata.json"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "/app/data/file_metadata.db"
    asyncio.run(migrate(json_path, db_path))
```

**Step 4: `app.py`에서 DB 호출을 비동기로 수정**

`app.py`의 모든 `db.list_all()`, `db.delete()` 등 호출을 `await db.list_all()` 형태로 수정한다. `app.py`의 엔드포인트 함수가 이미 `async def`이므로 `await`만 추가하면 된다.

앱 시작 시 DB 초기화:
```python
@app.on_event("startup")
async def startup():
    await db.init()
```

**Step 5: 동작 확인**

```bash
cd simple-updown-backend
STORAGE_TYPE=local uvicorn app:app --reload --port 9000
# 파일 업로드 후 /api/files/ 조회
curl http://localhost:9000/api/files/
```

Expected: 파일 목록 정상 반환

**Step 6: Commit**

```bash
git add simple-updown-backend/database.py simple-updown-backend/migrate_db.py \
        simple-updown-backend/app.py simple-updown-backend/requirements.txt
git commit -m "feat: JSON DB를 SQLite(aiosqlite)로 교체, 마이그레이션 스크립트 추가"
```

---

## 단계 2: 백엔드 구조 분리

### Task 2-1: `utils.py` 공통 유틸 분리

**Files:**
- Create: `simple-updown-backend/utils.py`
- Modify: `simple-updown-backend/app.py`
- Modify: `simple-updown-backend/local_storage.py`

**Step 1: `utils.py` 생성**

```python
from typing import Optional


def format_file_size(size_in_bytes: Optional[int]) -> str:
    if size_in_bytes is None or not isinstance(size_in_bytes, (int, float)) or size_in_bytes < 0:
        return "0 B"
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 ** 2:
        return f"{size_in_bytes / 1024:.1f} KB"
    elif size_in_bytes < 1024 ** 3:
        return f"{size_in_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_in_bytes / (1024 ** 3):.1f} GB"


def is_image_file(filename: str) -> bool:
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg'}
    ext = os.path.splitext(filename.lower())[1]
    return ext in image_extensions


def is_image_content_type(content_type: str) -> bool:
    return content_type.startswith('image/')
```

**Step 2: `app.py`와 `local_storage.py`에서 중복 함수 제거**

`app.py`의 `format_file_size`, `is_image_file`, `is_image_content_type` 함수 정의 삭제 후:
```python
from utils import format_file_size, is_image_file, is_image_content_type
```

`local_storage.py`의 `format_file_size` 함수 정의 삭제 후:
```python
from utils import format_file_size
```

**Step 3: Commit**

```bash
git add simple-updown-backend/utils.py simple-updown-backend/app.py simple-updown-backend/local_storage.py
git commit -m "refactor: 공통 유틸 함수를 utils.py로 분리"
```

---

### Task 2-2: `app.py`를 라우터로 분리

**Files:**
- Create: `simple-updown-backend/routers/__init__.py`
- Create: `simple-updown-backend/routers/files.py`
- Create: `simple-updown-backend/routers/upload.py`
- Create: `simple-updown-backend/routers/download.py`
- Create: `simple-updown-backend/routers/thumbnail.py`
- Modify: `simple-updown-backend/app.py`

**Step 1: `routers/` 디렉토리 생성 및 `__init__.py`**

```bash
mkdir -p simple-updown-backend/routers
touch simple-updown-backend/routers/__init__.py
```

**Step 2: `routers/files.py` 생성**

`GET /api/files/`와 `DELETE /files/{file_hash}` 엔드포인트를 이동:

```python
from fastapi import APIRouter, HTTPException
from database import FileMetadataDB
from utils import format_file_size

router = APIRouter()
db = FileMetadataDB()

@router.get("/api/files/")
async def list_files():
    """파일 목록 조회 (읽기 전용, DB 수정 없음)"""
    files = []
    all_files = await db.list_all()
    for doc_id, metadata in all_files.items():
        # 목록 구성 로직
        ...
    return files

@router.delete("/files/{file_hash}")
async def delete_file(file_hash: str):
    ...
```

**Step 3: `routers/upload.py`, `routers/download.py`, `routers/thumbnail.py` 생성**

각 엔드포인트를 해당 라우터 파일로 이동한다. 패턴은 `files.py`와 동일.

**Step 4: `app.py`에서 라우터 등록**

```python
from routers import files, upload, download, thumbnail

app.include_router(files.router)
app.include_router(upload.router)
app.include_router(download.router)
app.include_router(thumbnail.router)
```

**Step 5: `list_files`에서 DB 수정 로직 제거**

`GET /api/files/`에서 고아 파일 삭제, 파일 크기 검증, 확장자 수정 로직을 제거하고 APScheduler 스케줄러로 이전한다.

**Step 6: 동작 확인**

```bash
STORAGE_TYPE=local uvicorn app:app --reload --port 9000
curl http://localhost:9000/api/files/
curl -X POST http://localhost:9000/upload/ -F "file=@/tmp/test.txt"
curl http://localhost:9000/download/{hash}
```

**Step 7: Commit**

```bash
git add simple-updown-backend/routers/ simple-updown-backend/app.py
git commit -m "refactor: app.py를 routers/ 모듈로 분리, list_files에서 DB 수정 로직 제거"
```

---

### Task 2-3: 타입 힌팅 추가

**Files:**
- Modify: `simple-updown-backend/routers/files.py`
- Modify: `simple-updown-backend/routers/upload.py`
- Modify: `simple-updown-backend/routers/download.py`
- Modify: `simple-updown-backend/routers/thumbnail.py`
- Modify: `simple-updown-backend/local_storage.py`
- Modify: `simple-updown-backend/r2_storage.py`

**Step 1: 모든 함수 시그니처에 타입 힌팅 추가**

```python
# 변경 전
def upload_file(self, src_path, file_hash):

# 변경 후
def upload_file(self, src_path: str, file_hash: str) -> bool:
```

**Step 2: Commit**

```bash
git add simple-updown-backend/
git commit -m "refactor: 백엔드 전체 타입 힌팅 추가"
```

---

## 단계 3: 프론트엔드 리팩토링

### Task 3-1: 즉시 수정 사항 (디버그 UI 제거 + 버그 수정)

**Files:**
- Modify: `simple-updown-frontend/src/components/FilesList.vue`
- Modify: `simple-updown-frontend/src/components/FileUpload.vue`
- Modify: `simple-updown-frontend/src/App.vue`

**Step 1: 디버그 UI 제거 (`FilesList.vue`)**

다음 블록 삭제:
```html
<!-- 삭제 -->
<div class="debug-info">
  <p>총 파일 수: {{ files.length }}</p>
  <p>필터링 후 파일 수: {{ filteredFiles.length }}</p>
</div>
```

만료일 옆 `debug-note` span 삭제:
```html
<!-- 삭제 -->
<span class="debug-note">[{{ file.expire_minutes }}]</span>
```

**Step 2: 주석 처리된 `console.log` 20개+ 제거**

`FilesList.vue`와 `FileUpload.vue`에서 `//console.log`, `//console.error` 줄 모두 삭제.

**Step 3: `uploadedCount` 버그 수정 (`FileUpload.vue`)**

```javascript
// 변경 전 (실패해도 카운트 증가)
} catch (error) {
  this.uploadErrors.push({ file: file.name, error: error.message });
  this.uploadedCount++;  // 버그: 실패해도 증가
}

// 변경 후
} catch (error) {
  this.uploadErrors.push({ file: file.name, error: error.message });
  // uploadedCount는 성공 시에만 증가 (성공 분기에서만 증가)
}
```

**Step 4: 업로드 실패 UI 표시 (`FileUpload.vue`)**

`uploadErrors` 배열을 렌더링하는 UI 추가:
```html
<div v-if="uploadErrors.length > 0" class="upload-errors">
  <p v-for="err in uploadErrors" :key="err.file" class="error-item">
    ⚠️ {{ err.file }}: {{ err.error }}
  </p>
</div>
```

**Step 5: 삭제 확인 다이얼로그 추가 (`FilesList.vue`)**

```javascript
async deleteFile(fileHash) {
  if (!confirm('이 파일을 삭제하시겠습니까?')) return;
  // ... 기존 삭제 로직
}
```

**Step 6: 연도 하드코딩 수정 (`App.vue`)**

```html
<!-- 변경 전 -->
<p>© 2025 Simple Upload/Download Service</p>

<!-- 변경 후 -->
<p>© {{ new Date().getFullYear() }} Simple Upload/Download Service</p>
```

**Step 7: CSS 중복 통합 (`FilesList.vue`)**

`.copy-alert`와 `.multi-upload-message`를 `.toast-message`로 통합:
```css
.toast-message {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  /* ... 공통 스타일 */
}
```

**Step 8: 빌드 확인**

```bash
cd simple-updown-frontend
npm run build
```

Expected: 빌드 성공, 에러 없음

**Step 9: Commit**

```bash
git add simple-updown-frontend/src/
git commit -m "fix: 디버그 UI 제거, uploadedCount 버그 수정, 삭제 확인 다이얼로그 추가, 연도 동적 처리"
```

---

### Task 3-2: 공통 유틸 분리

**Files:**
- Create: `simple-updown-frontend/src/utils/fileUtils.js`
- Create: `simple-updown-frontend/src/utils/dateUtils.js`
- Modify: `simple-updown-frontend/src/components/FilesList.vue`
- Modify: `simple-updown-frontend/src/components/FileUpload.vue`

**Step 1: `fileUtils.js` 생성**

```javascript
export function formatFileSize(bytes) {
  if (typeof bytes !== 'number' || isNaN(bytes)) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

export function getFileIcon(filename) {
  const lower = filename.toLowerCase()
  if (['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'].some(ext => lower.endsWith(ext))) return '🖼️'
  if (['.mp4', '.avi', '.mov', '.mkv'].some(ext => lower.endsWith(ext))) return '🎬'
  if (['.mp3', '.wav', '.flac', '.aac'].some(ext => lower.endsWith(ext))) return '🎵'
  if (['.pdf'].some(ext => lower.endsWith(ext))) return '📄'
  if (['.zip', '.rar', '.7z', '.tar', '.gz'].some(ext => lower.endsWith(ext))) return '📦'
  if (['.xls', '.xlsx'].some(ext => lower.endsWith(ext))) return '📊'
  if (['.ppt', '.pptx'].some(ext => lower.endsWith(ext))) return '📋'
  if (['.doc', '.docx'].some(ext => lower.endsWith(ext))) return '📝'
  return '📁'
}

export function isImageFile(filename) {
  const imageExts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
  return imageExts.some(ext => filename.toLowerCase().endsWith(ext))
}
```

**Step 2: `dateUtils.js` 생성**

UTC 파싱 로직 5곳을 하나로 통합:
```javascript
const UNLIMITED_THRESHOLD_MS = 1000 * 60 * 60 * 24 * 365 * 90 // 90년

export function parseUTCDate(dateStr) {
  if (!dateStr) return null
  return new Date(dateStr.endsWith('Z') ? dateStr : dateStr + 'Z')
}

export function isUnlimited(expireTimeStr) {
  const expireTime = parseUTCDate(expireTimeStr)
  if (!expireTime) return true
  return expireTime - Date.now() > UNLIMITED_THRESHOLD_MS
}

export function isExpiringSoon(expireTimeStr, thresholdHours = 24) {
  if (isUnlimited(expireTimeStr)) return false
  const expireTime = parseUTCDate(expireTimeStr)
  if (!expireTime) return false
  const diffMs = expireTime - Date.now()
  return diffMs > 0 && diffMs < thresholdHours * 60 * 60 * 1000
}

export function getTimeLeft(expireTimeStr) {
  if (isUnlimited(expireTimeStr)) return '무제한'
  const expireTime = parseUTCDate(expireTimeStr)
  if (!expireTime) return '알 수 없음'
  const diffMs = expireTime - Date.now()
  if (diffMs <= 0) return '만료됨'
  const hours = Math.floor(diffMs / (1000 * 60 * 60))
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))
  if (hours >= 24) return `${Math.floor(hours / 24)}일 ${hours % 24}시간`
  return `${hours}시간 ${minutes}분`
}
```

**Step 3: 컴포넌트에서 중복 함수 제거 후 import**

`FilesList.vue`와 `FileUpload.vue`에서 중복 함수 정의 삭제 후:
```javascript
import { formatFileSize, getFileIcon, isImageFile } from '@/utils/fileUtils'
import { isUnlimited, isExpiringSoon, getTimeLeft, parseUTCDate } from '@/utils/dateUtils'
```

**Step 4: 빌드 확인**

```bash
npm run build
```

**Step 5: Commit**

```bash
git add simple-updown-frontend/src/utils/ simple-updown-frontend/src/components/
git commit -m "refactor: 공통 유틸 함수를 utils/로 분리 (formatFileSize, dateUtils)"
```

---

### Task 3-3: API 레이어 분리

**Files:**
- Create: `simple-updown-frontend/src/api/filesApi.js`
- Modify: `simple-updown-frontend/src/components/FilesList.vue`
- Modify: `simple-updown-frontend/src/components/FileUpload.vue`

**Step 1: `filesApi.js` 생성**

```javascript
import axios from 'axios'

const api = axios.create({
  timeout: 30000,
})

export async function fetchFiles() {
  const response = await api.get('/api/files/')
  return response.data
}

export async function uploadFile(file, expireMinutes, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('expire_in_minutes', expireMinutes)
  const response = await api.post(`/upload/?expire_in_minutes=${expireMinutes}`, formData, {
    onUploadProgress: onProgress,
  })
  return response.data
}

export async function deleteFile(fileHash) {
  await api.delete(`/files/${fileHash}`)
}

export function getDownloadUrl(fileHash) {
  return `/download/${fileHash}`
}

export function getThumbnailUrl(fileHash) {
  return `/thumbnail/${fileHash}`
}
```

**Step 2: 컴포넌트에서 axios 직접 호출을 API 레이어로 교체**

`FilesList.vue`와 `FileUpload.vue`에서 `axios.get('/api/files/')` 등을 `fetchFiles()` 등으로 교체.

**Step 3: 다운로드 직접 링크 방식으로 변경**

```javascript
// 변경 전 (Blob 메모리 로드)
const response = await axios.get(`/download/${hash}`, { responseType: 'blob' })
const url = URL.createObjectURL(new Blob([response.data]))
const link = document.createElement('a')
link.href = url
link.download = filename
link.click()
URL.revokeObjectURL(url)

// 변경 후 (직접 링크)
import { getDownloadUrl } from '@/api/filesApi'

const link = document.createElement('a')
link.href = getDownloadUrl(fileHash)
link.download = filename
document.body.appendChild(link)
link.click()
document.body.removeChild(link)
```

**Step 4: 빌드 확인**

```bash
npm run build
```

**Step 5: Commit**

```bash
git add simple-updown-frontend/src/api/ simple-updown-frontend/src/components/
git commit -m "refactor: API 레이어 분리, 다운로드 직접 링크 방식으로 변경"
```

---

### Task 3-4: Vue 3 Composition API 전환

**Files:**
- Modify: `simple-updown-frontend/src/App.vue`
- Modify: `simple-updown-frontend/src/components/FileUpload.vue`
- Modify: `simple-updown-frontend/src/components/FilesList.vue`

**Step 1: `App.vue` 전환**

```vue
<!-- 변경 전 -->
<script>
export default {
  name: 'App'
}
</script>

<!-- 변경 후 -->
<script setup>
// 로직 없음 — script 블록 자체가 불필요하지만 name 설정을 위해 유지
</script>
```

**Step 2: `FileUpload.vue` Composition API 전환**

```vue
<script setup>
import { ref, computed } from 'vue'
import { uploadFile } from '@/api/filesApi'
import { formatFileSize } from '@/utils/fileUtils'

const selectedFiles = ref([])
const fileProgress = ref({})
const uploadedCount = ref(0)
const uploadErrors = ref([])
const isUploading = ref(false)
const expireOption = ref('60')

const totalFiles = computed(() => selectedFiles.value.length)

function handleFileSelect(event) {
  selectedFiles.value = Array.from(event.target.files)
}

async function uploadFiles() {
  // ... 업로드 로직
}
</script>
```

**Step 3: `FilesList.vue` Composition API 전환**

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchFiles, deleteFile, getDownloadUrl, getThumbnailUrl } from '@/api/filesApi'
import { formatFileSize, getFileIcon, isImageFile } from '@/utils/fileUtils'
import { isUnlimited, isExpiringSoon, getTimeLeft } from '@/utils/dateUtils'

const files = ref([])
const searchQuery = ref('')
const sortBy = ref('upload_time')

const filteredFiles = computed(() => {
  // ... 필터링 로직
})

onMounted(async () => {
  files.value = await fetchFiles()
})
</script>
```

**Step 4: ESLint 규칙 업그레이드**

`package.json`의 eslint 설정:
```json
"extends": [
  "plugin:vue/vue3-recommended",
  "eslint:recommended"
]
```

**Step 5: 린트 + 빌드 확인**

```bash
npm run lint
npm run build
```

Expected: 린트 에러 없음, 빌드 성공

**Step 6: Commit**

```bash
git add simple-updown-frontend/src/
git commit -m "refactor: Vue 3 Composition API (<script setup>)로 전환, ESLint vue3-recommended 적용"
```

---

## 단계 4: 인프라 개선

### Task 4-1: Dockerfile 개선

**Files:**
- Modify: `Dockerfile`
- Modify: `Containerfile`

**Step 1: `Dockerfile` 수정**

```dockerfile
# node:16 → node:20
FROM --platform=${BUILDPLATFORM:-linux/amd64} node:20-slim AS frontend-builder

WORKDIR /app/frontend
COPY simple-updown-frontend/package*.json ./
# npm install → npm ci
RUN npm ci

COPY simple-updown-frontend/ .
RUN npm run build

FROM python:3.12-slim AS runtime

# ... (기존 내용 유지)

# uvicorn 멀티워커 설정
ENV UVICORN_WORKERS=1
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 9000 --workers ${UVICORN_WORKERS}"]
```

**Step 2: `Containerfile` 수정**

- `node:16` → `node:20`
- `--reload` 플래그 제거
- `STORAGE_TYPE` 환경변수 추가
- 비루트 사용자 추가 (Dockerfile과 동일하게)

**Step 3: 빌드 확인**

```bash
docker build --build-arg STORAGE_TYPE=local -t simple-updown:test .
docker run -p 9000:9000 simple-updown:test
```

**Step 4: Commit**

```bash
git add Dockerfile Containerfile
git commit -m "fix: Dockerfile node:16→node:20, npm ci 사용, uvicorn 멀티워커 설정"
```

---

### Task 4-2: GitHub Actions 개선

**Files:**
- Modify: `.github/workflows/docker-publish.yml`

**Step 1: PR push 차단 조건 추가**

```yaml
- name: Build and push (local)
  uses: docker/build-push-action@v5  # v4 → v5
  with:
    push: ${{ github.event_name != 'pull_request' }}  # 추가
    cache-from: type=gha  # 추가
    cache-to: type=gha,mode=max  # 추가
```

**Step 2: 액션 버전 업그레이드**

```yaml
- uses: actions/checkout@v4  # v3 → v4
- uses: docker/setup-buildx-action@v3  # v2 → v3
- uses: docker/login-action@v3  # v2 → v3
- uses: docker/build-push-action@v5  # v4 → v5
```

**Step 3: Commit**

```bash
git add .github/workflows/docker-publish.yml
git commit -m "fix: GitHub Actions — PR push 차단, 액션 버전 업그레이드, 빌드 캐시 추가"
```

---

### Task 4-3: docker-compose 및 기타 설정 파일 개선

**Files:**
- Modify: `docker-compose.local.yml`
- Modify: `docker-compose.yml`
- Modify: `.dockerignore`
- Modify: `.env_sample`

**Step 1: `docker-compose.local.yml`에 메타데이터 볼륨 추가**

```yaml
services:
  app:
    volumes:
      - ${UPLOAD_PATH:-./uploads}:/app/uploads
      - ${DATA_PATH:-./data}:/app/data  # 추가: SQLite DB 영속성
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/api/files/"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Step 2: `docker-compose.yml` 문법 오류 수정**

```yaml
# 변경 전
environment:
  - STORAGE_TYPE = # R2 or local

# 변경 후
environment:
  - STORAGE_TYPE=local  # local 또는 r2
```

**Step 3: `.dockerignore` 보강**

```
.env
.git
.gitignore
*.md
docs/
Dockerfile
Containerfile
docker-compose*
git.sh
updown/
simple-updown-frontend/node_modules
simple-updown-backend/__pycache__
simple-updown-backend/*.pyc
```

**Step 4: `.env_sample` 수정**

```
# Cloudflare R2 엔드포인트 URL (예: https://xxx.r2.cloudflarestorage.com)
R2_ENDPOINT_URL=
# R2 액세스 키 ID
R2_ACCESS_KEY_ID=
# R2 시크릿 액세스 키
R2_SECRET_ACCESS_KEY=
# R2 버킷 이름
R2_BUCKET_NAME=
# 리전 (기본값: auto)
R2_REGION=auto
```

**Step 5: Commit**

```bash
git add docker-compose.local.yml docker-compose.yml .dockerignore .env_sample
git commit -m "fix: docker-compose 볼륨/헬스체크 추가, STORAGE_TYPE 문법 수정, .dockerignore 보강"
```

---

## 완료 기준 체크리스트

- [ ] `STORAGE_TYPE=local` 실행 시 R2 클라이언트 초기화 없음
- [ ] 파일 업로드/다운로드/삭제 정상 동작
- [ ] 한글 파일명 다운로드 시 `Content-Disposition` 헤더 정상
- [ ] 만료 파일 다운로드 시 404 반환 (500 아님)
- [ ] 프론트엔드에 디버그 정보 노출 없음
- [ ] 다운로드가 직접 링크 방식으로 동작 (Blob 메모리 로드 없음)
- [ ] 파일 삭제 시 확인 다이얼로그 표시
- [ ] PR에서 Docker Hub push 없음
- [ ] `npm run build` 성공
- [ ] `npm run lint` 에러 없음
