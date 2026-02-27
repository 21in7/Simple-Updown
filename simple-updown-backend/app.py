import os
from dotenv import load_dotenv

# 반드시 스토리지 초기화 전에 호출
load_dotenv()

import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import FileMetadataDB
from local_storage import LocalStorage
from r2_storage import R2Storage
from routers import files, upload, download, thumbnail

storage_type = os.getenv("STORAGE_TYPE", "local")
if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

db = FileMetadataDB()


async def cleanup_orphaned_files():
    deleted_count = 0
    for doc_id, metadata in (await db.list_all()).items():
        file_hash = metadata.get("hash", {}).get("sha256")
        if not file_hash or not storage.file_exists(file_hash):
            await db.delete(doc_id)
            deleted_count += 1
    print(f"정리 완료: {deleted_count}개의 메타데이터 항목이 삭제되었습니다.")


async def delete_expired_files():
    expired_docs = []
    current_time = datetime.datetime.utcnow()
    total_count = 0
    expired_count = 0
    error_count = 0

    for doc_id, metadata in (await db.list_all()).items():
        total_count += 1
        if "expire_time" not in metadata:
            expired_docs.append(doc_id)
            error_count += 1
            continue
        try:
            expire_time_str = metadata["expire_time"]
            if expire_time_str.endswith('Z'):
                expire_time_str = expire_time_str[:-1]
            expire_time = datetime.datetime.fromisoformat(expire_time_str)
            if current_time > expire_time:
                expired_count += 1
                file_hash = metadata.get("hash", {}).get("sha256")
                if file_hash:
                    storage.delete_file(file_hash)
                expired_docs.append(doc_id)
        except (ValueError, TypeError):
            error_count += 1
            expired_docs.append(doc_id)

    for doc_id in expired_docs:
        await db.delete(doc_id)

    print(f"만료 파일 검사 완료 - 전체: {total_count}, 만료됨: {expired_count}, 오류: {error_count}")
    if expired_docs:
        print(f"{len(expired_docs)}개의 만료된 파일 삭제됨")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    await cleanup_orphaned_files()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(delete_expired_files, 'interval', minutes=1)
    scheduler.add_job(cleanup_orphaned_files, 'interval', hours=1)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="File Storage Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(files.router)
app.include_router(upload.router)
app.include_router(download.router)
app.include_router(thumbnail.router)


@app.get("/")
async def serve_frontend():
    return FileResponse('static/index.html')


@app.get("/files/")
async def list_files_page():
    return FileResponse('static/index.html')


@app.get("/files/{path:path}")
async def serve_files_path(path: str):
    return FileResponse('static/index.html')


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/") or request.url.path.startswith("/download/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return FileResponse('static/index.html')


@app.get("/api/test-param")
async def test_param(expire_in_minutes: int = 5):
    return {
        "received_value": expire_in_minutes,
        "type": str(type(expire_in_minutes)),
        "is_valid": isinstance(expire_in_minutes, int) and expire_in_minutes > 0,
    }
