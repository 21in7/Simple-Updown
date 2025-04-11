# app.py
# Main FastAPI application for file upload/download with R2 storage

import os
import hashlib
import tempfile
import datetime
import pyshorteners
import io
from datetime import timedelta
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from database import FileMetadataDB
from r2_storage import R2Storage
from local_storage import LocalStorage

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed, thumbnails will not be available")
    Image = None

# 환경 변수로 스토리지 타입 지정
storage_type = os.environ.get("STORAGE_TYPE", "local")

# 스토리지 인스턴스 생성
if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

# Load environment variables
load_dotenv()

# 파일 크기 포맷팅 함수
def format_file_size(size_in_bytes):
    # 유효하지 않은 값 처리
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

app = FastAPI(title="File Storage Service")
db = FileMetadataDB()
r2 = R2Storage()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 제공

app.mount("/static", StaticFiles(directory="static"), name="static")
#app.mount("/css", StaticFiles(directory="static/css"), name="css")
#app.mount("/js", StaticFiles(directory="static/js"), name="js")

@app.get("/")
async def serve_frontend():
    return FileResponse('static/index.html')

@app.get("/files/")
async def list_files():
    return FileResponse('static/index.html')

@app.get("/api/files/")
async def list_files():
    files = []
    for doc_id, metadata in db.list_all().items():
        file_hash = metadata.get("hash", {}).get("sha256")

        # 파일 존재 여부 확인
        file_exists = False
        if storage_type == "local":
            file_path = os.path.join(storage.upload_dir, file_hash)
            file_exists = os.path.isfile(file_path)
        else:
            # R2 또는 다른 스토리지의 경우
            file_exists = storage.file_exists(file_hash)

        # 존재하는 파일만 목록에 추가하거나 존재 여부 플래그 포함
        if file_exists:
            # 파일 크기가 없거나 형식이 잘못된 경우 수정
            if "file_size" not in metadata or not isinstance(metadata["file_size"], (int, float)):
                metadata["file_size"] = 0
                metadata["formatted_size"] = "0 B"

            files.append(metadata)
        else:
            # 존재하지 않는 파일의 메타데이터 삭제
            db.delete(doc_id)
    return {"files": files}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), expire_in_minutes: int = 5):
    # Calculate file hash to use as unique identifier
    contents = await file.read()

    # 파일 크기 검증
    file_size = len(contents)
    if file_size <= 0:
        file_size = 0

    file_hash = hashlib.sha256(contents).hexdigest()

    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(contents)
        temp_file_path = temp_file.name

    # Reset file position for subsequent reads
    await file.seek(0)



    # Calculate additional hashes for metadata
    md5_hash = hashlib.md5(contents).hexdigest()
    sha1_hash = hashlib.sha1(contents).hexdigest()

    # Upload Local or R2
    if storage_type == "local":
        storage.upload_file(temp_file_path, file_hash)
    else:
        r2.upload_file(temp_file_path, file_hash)

    # Remove temporary file
    os.unlink(temp_file_path)

    # 만료 시간 계산
    expire_time = datetime.datetime.now() + timedelta(minutes=expire_in_minutes)

    # 파일 저장 시간 계산
    add_time = datetime.datetime.now()

    # Store metadata in NoSQL database
    metadata = {
        "file_name": file.filename,
        "file_size": len(contents),
        "formatted_size": format_file_size(len(contents)),
        "content_type": file.content_type,
        "hash": {
            "md5": md5_hash,
            "sha1": sha1_hash,
            "sha256": file_hash
        },
        "expire_time": expire_time.isoformat(), # ISO 포맷으로 저장
        "date": add_time.isoformat()
    }

    doc_id = db.insert(metadata)
    return {
        "success": True,
        "message": "File uploaded successfully.",
        "redirect_to": "/files/",
        "file_info": metadata
    }

@app.get("/download/{file_hash}")
async def download_file(file_hash: str):
    # Search for file metadata by hash
    for doc_id, metadata in db.list_all().items():
        if metadata.get("hash", {}).get("sha256") == file_hash:
            # 만료 시간 확인
            expire_time = datetime.datetime.fromisoformat(metadata.get("expire_time"))
            if datetime.datetime.now() > expire_time:
                # 파일 삭제
                r2.delete_file(file_hash)
                db.delete(doc_id)
                raise HTTPException(status_code=404, detail="File expired and deleted")

            # Get file from R2
            file_stream = r2.get_file_stream(file_hash)
            
            if file_stream:
                # Return file as streaming response
                return StreamingResponse(
                    file_stream, 
                    media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename={metadata['file_name']}"}
                )
    
    raise HTTPException(status_code=404, detail="File not found")

@app.delete("/files/{file_hash}")
async def delete_file(file_hash: str):
    # Search for file by hash
    for doc_id, metadata in db.list_all().items():
        if metadata.get("hash", {}).get("sha256") == file_hash:
            # Delete from R2
            success = r2.delete_file(file_hash)
            
            if success:
                # Delete metadata
                db.delete(doc_id)
                return {"message": "File deleted successfully"}
            else:
                raise HTTPException(status_code=500, detail="Failed to delete file from storage")
    
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/thumbnail/{file_hash}")
async def get_thumbnail(file_hash: str):
    # PIL이 설치되어 있는지 확인
    if Image is None:
        raise HTTPException(status_code=501, detail="Thumbnail generation not available")
    
    # 파일 메타데이터 검색
    for doc_id, metadata in db.list_all().items():
        if metadata.get("hash", {}).get("sha256") == file_hash:
            # 컨텐츠 타입이 이미지인지 확인
            if not metadata.get("content_type", "").startswith("image/"):
                raise HTTPException(status_code=400, detail="Not an image file")
            
            # 만료 시간 확인
            expire_time = datetime.datetime.fromisoformat(metadata.get("expire_time"))
            if datetime.datetime.utcnow() > expire_time:
                # 파일 삭제
                r2.delete_file(file_hash)
                db.delete(doc_id)
                raise HTTPException(status_code=404, detail="File expired and deleted")
            
            # R2에서 파일 가져오기
            file_stream = r2.get_file_stream(file_hash)
            if file_stream:
                try:
                    # 이미지 로드 및 썸네일 생성
                    img = Image.open(io.BytesIO(file_stream.read()))
                    img.thumbnail((100, 100))
                    
                    # 썸네일을 바이트로 변환
                    thumb_io = io.BytesIO()
                    img_format = img.format if img.format else 'JPEG'
                    img.save(thumb_io, format=img_format)
                    thumb_io.seek(0)
                    
                    # 썸네일 반환
                    return StreamingResponse(
                        thumb_io, 
                        media_type=metadata.get("content_type")
                    )
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Error generating thumbnail: {str(e)}")
    
    raise HTTPException(status_code=404, detail="File not found")

def delete_expired_files():
    expired_docs = []
    for doc_id, metadata in db.list_all().items():
        expire_time = datetime.datetime.fromisoformat(metadata.get("expire_time"))
        if datetime.datetime.now() > expire_time:
            r2.delete_file(metadata["hash"]["sha256"])
            expired_docs.append(doc_id)

    # 반복이 끝난 후에 삭제
    for doc_id in expired_docs:
        db.delete(doc_id)

scheduler = BackgroundScheduler()
scheduler.add_job(delete_expired_files, 'interval', minutes=1)
scheduler.start()