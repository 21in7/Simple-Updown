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
try:
    from PIL import Image
except ImportError:
    print("Pillow not installed, thumbnails will not be available")
    Image = None

# Load environment variables
load_dotenv()

# 파일 크기 포맷팅 함수
def format_file_size(size_in_bytes):
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

@app.get("/")
async def serve_frontend():
    return FileResponse('static/index.html')

@app.get("/files/")
async def list_files():
    return FileResponse('static/index.html')

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), expire_in_minutes: int = 5):
    # Calculate file hash to use as unique identifier
    contents = await file.read()
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

    # Upload to R2
    r2.upload_file(temp_file_path, file_hash)

    # Remove temporary file
    os.unlink(temp_file_path)

    # 만료 시간 계산
    expire_time = datetime.datetime.now() + timedelta(minutes=expire_in_minutes)

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
        "expire_time": expire_time.isoformat() # ISO 포맷으로 저장장
    }

    doc_id = db.insert(metadata)

    # 업로드 완료 후 /files/ 페이지로 리다이렉트
    response = RedirectResponse(url="/files/?upload_complete=true", status_code=303)
    return response

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