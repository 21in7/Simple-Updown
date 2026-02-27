import os
from dotenv import load_dotenv

# 반드시 스토리지 초기화 전에 호출
load_dotenv()

import asyncio
import hashlib
import io
import tempfile
import datetime
import uuid
import traceback
from datetime import timedelta
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import FileMetadataDB
from r2_storage import R2Storage
from local_storage import LocalStorage

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed, thumbnails will not be available")
    Image = None

storage_type = os.getenv("STORAGE_TYPE", "local")

if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

db = FileMetadataDB()


def format_file_size(size_in_bytes):
    if size_in_bytes is None or not isinstance(size_in_bytes, (int, float)) or size_in_bytes < 0:
        return "0 B"
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.2f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} GB"


def is_image_file(filename: str) -> bool:
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    ext = os.path.splitext(filename.lower())[1]
    return ext in image_extensions


def is_image_content_type(content_type: str) -> bool:
    return bool(content_type and content_type.startswith('image/'))


async def cleanup_orphaned_files():
    deleted_count = 0
    for doc_id, metadata in (await db.list_all()).items():
        file_hash = metadata.get("hash", {}).get("sha256")
        if not file_hash:
            await db.delete(doc_id)
            deleted_count += 1
            continue
        if not storage.file_exists(file_hash):
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
            expire_time_str = metadata.get("expire_time")
            if expire_time_str.endswith('Z'):
                expire_time_str = expire_time_str[:-1]
            expire_time = datetime.datetime.fromisoformat(expire_time_str)
            if current_time > expire_time:
                expired_count += 1
                file_hash = metadata.get("hash", {}).get("sha256")
                if file_hash:
                    storage.delete_file(file_hash)
                expired_docs.append(doc_id)
        except (ValueError, TypeError) as e:
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


@app.get("/api/files/")
async def list_files():
    files = []
    for doc_id, metadata in (await db.list_all()).items():
        file_hash = metadata.get("hash", {}).get("sha256")
        if not file_hash:
            continue
        if not storage.file_exists(file_hash):
            continue
        if not metadata.get("file_size") or not metadata.get("file_name"):
            continue
        files.append(metadata)
    return {"files": files}


@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...),
    expire_in_minutes: int = 5,
    request: Request = None,
):
    client_ip = request.client.host if request else "unknown"
    ip_prefix = '.'.join(client_ip.split('.')[:2]) if '.' in client_ip else client_ip

    if not isinstance(expire_in_minutes, int):
        expire_in_minutes = 5

    is_unlimited = expire_in_minutes == -1
    if not is_unlimited and expire_in_minutes <= 0:
        expire_in_minutes = 5

    file_hash = None
    file_size = 0
    temp_file_path = None

    try:
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, f"upload_{uuid.uuid4().hex}.tmp")

        md5_obj = hashlib.md5()
        sha1_obj = hashlib.sha1()
        sha256_obj = hashlib.sha256()

        chunk_size = 8 * 1024 * 1024
        processed_size = 0

        with open(temp_file_path, 'wb') as temp_file:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                md5_obj.update(chunk)
                sha1_obj.update(chunk)
                sha256_obj.update(chunk)
                temp_file.write(chunk)
                temp_file.flush()
                file_size += len(chunk)
                processed_size += len(chunk)
                if processed_size >= 100 * 1024 * 1024:
                    print(f"업로드 진행 중: {format_file_size(file_size)} 처리됨")
                    processed_size = 0

        if file_size <= 0:
            raise HTTPException(status_code=400, detail="Empty file cannot be uploaded")

        md5_hash = md5_obj.hexdigest()
        sha1_hash = sha1_obj.hexdigest()
        file_hash = sha256_obj.hexdigest()
        del md5_obj, sha1_obj, sha256_obj

        if not storage.upload_file(temp_file_path, file_hash):
            raise HTTPException(status_code=500, detail="Failed to store file")

        now = datetime.datetime.utcnow()
        expire_time = now + timedelta(days=36500) if is_unlimited else now + timedelta(minutes=expire_in_minutes)

        metadata = {
            "file_name": file.filename,
            "file_size": file_size,
            "formatted_size": format_file_size(file_size),
            "content_type": file.content_type,
            "hash": {"md5": md5_hash, "sha1": sha1_hash, "sha256": file_hash},
            "expire_time": expire_time.isoformat() + "Z",
            "date": now.isoformat() + "Z",
            "uploader_ip": ip_prefix,
            "expire_minutes": expire_in_minutes,
        }

        await db.insert(metadata)

        base_url = str(request.base_url).rstrip("/")
        share_url = f"{base_url}/download/{file_hash}"

        return {
            "success": True,
            "message": "File uploaded successfully.",
            "redirect_to": "/files/",
            "file_info": {
                "file_name": file.filename,
                "file_size": file_size,
                "formatted_size": format_file_size(file_size),
                "hash": file_hash,
                "share_url": share_url,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"파일 업로드 중 오류 발생: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                print(f"임시 파일 삭제 실패: {str(e)}")
        await file.close()


@app.get("/download/{file_hash}")
async def download_file(file_hash: str):
    result = await db.get_by_hash(file_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    doc_id, file_metadata = result

    expire_time_str = file_metadata.get("expire_time")
    try:
        if expire_time_str.endswith('Z'):
            expire_time_str = expire_time_str[:-1]
        expire_time = datetime.datetime.fromisoformat(expire_time_str)
        if datetime.datetime.utcnow() > expire_time:
            storage.delete_file(file_hash)
            await db.delete(doc_id)
            raise HTTPException(status_code=404, detail="File expired and deleted")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing expiration time: {str(e)}")

    if not storage.file_exists(file_hash):
        await db.delete(doc_id)
        raise HTTPException(status_code=404, detail="File not found")

    content_type = file_metadata.get("content_type", "application/octet-stream")
    filename = file_metadata.get("file_name", "unknown")
    encoded_filename = quote(filename, safe='')

    def file_streamer():
        if storage_type == "local":
            file_path = os.path.join(storage.upload_dir, file_hash)
            with open(file_path, 'rb') as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk
        else:
            stream = storage.get_file_stream(file_hash)
            if stream:
                for chunk in stream:
                    yield chunk

    return StreamingResponse(
        file_streamer(),
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Cache-Control": "no-cache",
        },
    )


@app.delete("/files/{file_hash}")
async def delete_file(file_hash: str):
    result = await db.get_by_hash(file_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    doc_id, _ = result

    if not storage.delete_file(file_hash):
        raise HTTPException(status_code=500, detail="Failed to delete file from storage")

    await db.delete(doc_id)
    return {"message": "File deleted successfully"}


@app.get("/thumbnail/{file_hash}")
async def get_thumbnail(file_hash: str, width: int = 100, height: int = 100):
    if Image is None:
        raise HTTPException(status_code=400, detail="Thumbnail generation not available - Pillow not installed")

    width = min(width, 500)
    height = min(height, 500)

    result = await db.get_by_hash(file_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    _, file_metadata = result

    file_name = file_metadata.get("file_name", "")
    content_type = file_metadata.get("content_type", "")

    if not (is_image_file(file_name) or is_image_content_type(content_type)):
        raise HTTPException(status_code=400, detail="Not an image file")

    thumbnail_dir = os.path.join(os.path.dirname(storage.upload_dir), "thumbnails")
    os.makedirs(thumbnail_dir, exist_ok=True)

    cache_key = f"{file_hash}_{width}x{height}"
    thumbnail_path = os.path.join(thumbnail_dir, cache_key)

    img_format = "JPEG"
    mime_type = "image/jpeg"
    if file_name.lower().endswith('.png'):
        img_format = "PNG"
        mime_type = "image/png"
    elif file_name.lower().endswith('.gif'):
        img_format = "GIF"
        mime_type = "image/gif"

    if os.path.exists(thumbnail_path):
        return FileResponse(
            thumbnail_path,
            media_type=mime_type,
            headers={"Cache-Control": "max-age=3600, public"},
        )

    try:
        if storage_type == "local":
            file_path = os.path.join(storage.upload_dir, file_hash)
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Image file not found")
            img_source = file_path
        else:
            img_bytes = storage.get_file_bytes(file_hash)
            if not img_bytes:
                raise HTTPException(status_code=404, detail="Image data not found")
            img_source = io.BytesIO(img_bytes)

        with Image.open(img_source) as img:
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
            if max(img.width, img.height) > 2000:
                factor = 2000 / max(img.width, img.height)
                img = img.resize(
                    (int(img.width * factor), int(img.height * factor)),
                    Image.LANCZOS,
                )
            img.thumbnail((width, height), Image.LANCZOS)
            if img.mode == 'RGBA' and img_format == 'JPEG':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            save_options = {'quality': 85, 'optimize': True} if img_format == 'JPEG' else {'optimize': True}
            img.save(thumbnail_path, format=img_format, **save_options)

        return FileResponse(
            thumbnail_path,
            media_type=mime_type,
            headers={"Cache-Control": "max-age=3600, public"},
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"썸네일 생성 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating thumbnail: {str(e)}")


@app.get("/api/test-param")
async def test_param(expire_in_minutes: int = 5):
    return {
        "received_value": expire_in_minutes,
        "type": str(type(expire_in_minutes)),
        "is_valid": isinstance(expire_in_minutes, int) and expire_in_minutes > 0,
    }
