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
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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

# 앱 시작시 정리 작업 수행
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 실행할 코드
    cleanup_orphaned_files()
    yield
    # 앱 종료시 실행할 코드
    pass

app = FastAPI(
    title="File Storage Service",
    lifespan=lifespan
)
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
async def list_files_page():
    return FileResponse('static/index.html')

@app.get("/files/{path:path}")
async def serve_files_path(path: str):
    return FileResponse('static/index.html')

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    # API 경로는 그대로 404 반환
    if request.url.path.startswith("/api/") or request.url.path.startswith("/download/"):
        return JSONResponse(
            status_code=404,
            content={"detail": "Not Found"}
        )
    # 그 외 경로는 index.html로 리다이렉트하여 SPA 라우팅 지원
    return FileResponse('static/index.html')

def cleanup_orphaned_files():
    """
    데이터베이스에 있는 모든 파일 메타데이터를 확인하고
    실제로 존재하지 않는 파일의 메타데이터는 삭제합니다.
    """
    deleted_count = 0
    for doc_id, metadata in db.list_all().items():
        file_hash = metadata.get("hash", {}).get("sha256")
        if not file_hash:
            db.delete(doc_id)
            deleted_count += 1
            continue

        # 파일 존재 여부 확인
        file_exists = False
        if storage_type == "local":
            file_path = os.path.join(storage.upload_dir, file_hash)
            file_exists = os.path.isfile(file_path)
        else:
            # R2 또는 다른 스토리지의 경우
            file_exists = storage.file_exists(file_hash)

        if not file_exists:
            db.delete(doc_id)
            deleted_count += 1

    print(f"정리 완료: {deleted_count}개의 메타데이터 항목이 삭제되었습니다.")

@app.get("/api/files/")
async def list_files():
    files = []
    file_count = 0
    valid_count = 0
    deleted_count = 0
    
    print("파일 목록 API 호출됨")
    
    for doc_id, metadata in db.list_all().items():
        file_count += 1
        file_hash = metadata.get("hash", {}).get("sha256")
        
        # 파일 해시가 없으면 항목을 삭제하고 건너뜁니다
        if not file_hash:
            db.delete(doc_id)
            deleted_count += 1
            print(f"파일 삭제: 해시 없음 - {doc_id}")
            continue
            
        # 파일 존재 여부 확인
        file_exists = False
        if storage_type == "local":
            file_path = os.path.join(storage.upload_dir, file_hash)
            file_exists = os.path.isfile(file_path)
        else:
            # R2 또는 다른 스토리지의 경우
            file_exists = storage.file_exists(file_hash)
        
        # 존재하는 파일만 목록에 추가
        if file_exists:
            # 파일 크기가 없거나 형식이 잘못된 경우 수정
            if "file_size" not in metadata or not isinstance(metadata["file_size"], (int, float)) or metadata["file_size"] <= 0:
                # 파일 크기가 0 이하면 항목 삭제하고 건너뜁니다
                db.delete(doc_id)
                deleted_count += 1
                print(f"파일 삭제: 크기 오류 - {doc_id}")
                continue
            
            # 파일명이 없는 경우 처리
            if "file_name" not in metadata or not metadata["file_name"]:
                # 파일명이 없으면 항목 삭제하고 건너뜁니다
                db.delete(doc_id)
                deleted_count += 1
                print(f"파일 삭제: 파일명 없음 - {doc_id}")
                continue
            
            # 파일명에 확장자 표시 확인
            file_name = metadata.get("file_name", "")
            if "." not in file_name:
                print(f"경고: 확장자 없는 파일명 - {file_name}")
                
                # 컨텐츠 타입에서 확장자 추론 시도
                content_type = metadata.get("content_type", "")
                extension = ""
                
                if "image/jpeg" in content_type:
                    extension = ".jpg"
                elif "image/png" in content_type:
                    extension = ".png"
                elif "application/pdf" in content_type:
                    extension = ".pdf"
                elif "text/plain" in content_type:
                    extension = ".txt"
                
                # 확장자 추가
                if extension and not file_name.endswith(extension):
                    metadata["file_name"] = file_name + extension
                    db.update(doc_id, metadata)
                    print(f"파일명 수정: {file_name} -> {metadata['file_name']}")
            
            # 유효한 파일 항목만 목록에 추가
            files.append(metadata)
            valid_count += 1
        else:
            # 존재하지 않는 파일의 메타데이터 삭제
            db.delete(doc_id)
            deleted_count += 1
            print(f"파일 삭제: 실제 파일 없음 - {doc_id}")
    
    print(f"파일 목록 결과: 전체 {file_count}개, 유효 {valid_count}개, 삭제됨 {deleted_count}개")
    return {"files": files}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), expire_in_minutes: int = 5, request: Request = None):
    # 파일 크기 확인 (0 바이트 파일 체크)
    contents = await file.read()
    file_size = len(contents)
    
    # 클라이언트 IP 가져오기
    client_ip = request.client.host if request else "unknown"
    # IP의 앞부분 두 자리만 추출
    ip_prefix = '.'.join(client_ip.split('.')[:2]) if '.' in client_ip else client_ip
    
    # 디버깅 로그 추가
    print(f"업로드 받은 파일명: {file.filename}")
    print(f"업로드 클라이언트 IP: {client_ip}, 표시용 IP: {ip_prefix}")
    print(f"요청된 만료 시간(분): {expire_in_minutes} (타입: {type(expire_in_minutes)})")
    
    # 유효한 expire_in_minutes 값인지 확인
    if not isinstance(expire_in_minutes, int):
        print(f"유효하지 않은 만료 시간 값: {expire_in_minutes}, 기본값 5분으로 설정")
        expire_in_minutes = 5
    
    # 무제한인 경우 처리 (값이 -1)
    is_unlimited = expire_in_minutes == -1
    if is_unlimited:
        print("무제한 유지 기간 설정")
    elif expire_in_minutes <= 0:
        print(f"유효하지 않은 만료 시간 값: {expire_in_minutes}, 기본값 5분으로 설정")
        expire_in_minutes = 5
    
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="Empty file cannot be uploaded")
    
    # 파일 해시 계산
    file_hash = hashlib.sha256(contents).hexdigest()
    
    # 임시 파일 생성
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(contents)
        temp_file_path = temp_file.name
    
    # 파일 포인터를 다시 처음으로 되돌림
    await file.seek(0)
    
    # 추가 해시 계산
    md5_hash = hashlib.md5(contents).hexdigest()
    sha1_hash = hashlib.sha1(contents).hexdigest()
    
    # 파일 업로드
    try:
        if storage_type == "local":
            storage.upload_file(temp_file_path, file_hash)
        else:
            r2.upload_file(temp_file_path, file_hash)
            
        # 임시 파일 삭제
        os.unlink(temp_file_path)
        
        # 시스템 시간 정보 확인
        import time
        sys_time = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"시스템 현재 시간 (time 모듈): {sys_time}")
        
        # 현재 시간 계산 (UTC로 명시)
        now = datetime.datetime.utcnow()
        
        # 만료 시간 계산 (무제한이면 100년)
        if is_unlimited:
            expire_time = now + timedelta(days=36500)  # 약 100년
        else:
            expire_time = now + timedelta(minutes=expire_in_minutes)
        
        # 시간 디버깅 정보
        print(f"현재 UTC 시간: {now.isoformat()}")
        print(f"요청된 만료 시간: {'무제한' if is_unlimited else f'{expire_in_minutes}분'}")
        print(f"만료 UTC 시간 ({expire_in_minutes}분 후): {expire_time.isoformat()}")
        
        # 확장자 확인 및 로깅
        original_filename = file.filename
        if "." not in original_filename:
            print(f"경고: 파일명에 확장자가 없습니다 - {original_filename}")
        
        # 메타데이터 저장
        metadata = {
            "file_name": original_filename,
            "file_size": file_size,
            "formatted_size": format_file_size(file_size),
            "content_type": file.content_type,
            "hash": {
                "md5": md5_hash,
                "sha1": sha1_hash,
                "sha256": file_hash
            },
            "expire_time": expire_time.isoformat() + "Z",  # Z는 UTC 시간임을 나타냄
            "date": now.isoformat() + "Z",
            "uploader_ip": ip_prefix,  # 업로더 IP 추가
            "expire_minutes": expire_in_minutes  # 요청된 만료 시간(분) 저장
        }
        
        # 메타데이터 저장 결과 디버깅
        print(f"저장된 메타데이터: file_name={metadata['file_name']}, size={metadata['file_size']}, content_type={metadata['content_type']}")
        print(f"저장된 날짜: date={metadata['date']}, expire_time={metadata['expire_time']}")
        print(f"저장된 만료 시간(분): {metadata['expire_minutes']}")
        
        doc_id = db.insert(metadata)
        
        # 공유 URL 생성
        base_url = str(request.base_url).rstrip("/")
        share_url = f"{base_url}/download/{file_hash}"
        
        return {
            "success": True,
            "message": "File uploaded successfully.",
            "redirect_to": "/files/",
            "file_info": metadata,
            "share_url": share_url  # 공유 URL 추가
        }
    except Exception as e:
        # 에러 발생 시 임시 파일이 남아있다면 삭제
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

@app.get("/download/{file_hash}")
async def download_file(file_hash: str):
    # 파일 메타데이터 검색
    file_metadata = None
    doc_id = None
    
    for d_id, metadata in db.list_all().items():
        if metadata.get("hash", {}).get("sha256") == file_hash:
            file_metadata = metadata
            doc_id = d_id
            break
    
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")
    
    # 만료 시간 확인 (UTC 시간 사용)
    expire_time_str = file_metadata.get("expire_time")
    
    # 디버깅 정보 출력
    print(f"파일 다운로드 요청: {file_hash}, 파일명: {file_metadata.get('file_name', 'unknown')}")
    print(f"만료 시간 문자열: {expire_time_str}")
    
    try:
        # 'Z' 접미사 처리
        if expire_time_str.endswith('Z'):
            expire_time_str = expire_time_str[:-1]
        
        expire_time = datetime.datetime.fromisoformat(expire_time_str)
        current_time = datetime.datetime.utcnow()
        
        print(f"현재 UTC 시간: {current_time.isoformat()}, 파싱된 만료 시간: {expire_time.isoformat()}")
        print(f"만료 비교 결과: {current_time > expire_time}")
        
        if current_time > expire_time:
            # 파일 삭제
            print(f"파일 만료됨, 삭제 진행: {file_hash}")
            if storage_type == "local":
                storage.delete_file(file_hash)
            else:
                r2.delete_file(file_hash)
            
            db.delete(doc_id)
            raise HTTPException(status_code=404, detail="File expired and deleted")
            
    except Exception as e:
        print(f"만료 시간 처리 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing expiration time: {str(e)}")
    
    # 파일 스트림 가져오기
    try:
        if storage_type == "local":
            file_path = os.path.join(storage.upload_dir, file_hash)
            if os.path.exists(file_path):
                print(f"로컬 스토리지에서 파일 반환: {file_path}")
                return FileResponse(
                    file_path,
                    media_type="application/octet-stream",
                    filename=file_metadata['file_name']
                )
            else:
                # 메타데이터는 있지만 파일이 없는 경우
                print(f"로컬 스토리지에 파일 없음: {file_path}")
                db.delete(doc_id)
                raise HTTPException(status_code=404, detail="File not found")
        else:
            print(f"R2 스토리지에서 파일 가져오기: {file_hash}")
            file_stream = r2.get_file_stream(file_hash)
            
            if file_stream:
                # 파일을 스트리밍 응답으로 반환
                return StreamingResponse(
                    file_stream,
                    media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename={file_metadata['file_name']}"}
                )
            else:
                # 메타데이터는 있지만 파일이 없는 경우
                print(f"R2 스토리지에 파일 없음: {file_hash}")
                db.delete(doc_id)
                raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        print(f"파일 다운로드 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

@app.delete("/files/{file_hash}")
async def delete_file(file_hash: str):
    # 파일 검색
    for doc_id, metadata in db.list_all().items():
        if metadata.get("hash", {}).get("sha256") == file_hash:
            # 파일 삭제
            success = False
            if storage_type == "local":
                success = storage.delete_file(file_hash)
            else:
                success = r2.delete_file(file_hash)
                
            if success:
                # 메타데이터 삭제
                db.delete(doc_id)
                return {"message": "File deleted successfully"}
            else:
                raise HTTPException(status_code=500, detail="Failed to delete file from storage")
    
    raise HTTPException(status_code=404, detail="File not found")

# 만료된 파일 삭제 함수
def delete_expired_files():
    expired_docs = []
    current_time = datetime.datetime.utcnow()
    print(f"만료 파일 검사 시작 - 현재 UTC 시간: {current_time.isoformat()}")
    
    total_count = 0
    expired_count = 0
    error_count = 0
    
    for doc_id, metadata in db.list_all().items():
        total_count += 1
        if "expire_time" not in metadata:
            expired_docs.append(doc_id)
            error_count += 1
            print(f"만료 시간 필드 없음: {doc_id}")
            continue
            
        try:
            expire_time_str = metadata.get("expire_time")
            # 'Z' 접미사를 제거하고 파싱 (필요한 경우)
            if expire_time_str.endswith('Z'):
                expire_time_str = expire_time_str[:-1]
            expire_time = datetime.datetime.fromisoformat(expire_time_str)
            
            time_diff = (expire_time - current_time).total_seconds()
            print(f"파일 {metadata.get('file_name', 'unknown')} 만료 시간: {expire_time_str}, 시간차: {time_diff}초")
            
            if current_time > expire_time:
                expired_count += 1
                file_hash = metadata.get("hash", {}).get("sha256")
                if file_hash:
                    print(f"만료된 파일 삭제: {metadata.get('file_name', 'unknown')}, 해시: {file_hash}")
                    if storage_type == "local":
                        storage.delete_file(file_hash)
                    else:
                        r2.delete_file(file_hash)
                expired_docs.append(doc_id)
        except (ValueError, TypeError) as e:
            error_count += 1
            print(f"날짜 형식 오류: {doc_id}, 오류: {str(e)}, 값: {metadata.get('expire_time', 'none')}")
            # 날짜 형식이 잘못된 경우 해당 항목 삭제
            expired_docs.append(doc_id)
    
    # 반복이 끝난 후에 삭제
    for doc_id in expired_docs:
        db.delete(doc_id)
    
    print(f"만료 파일 검사 완료 - 전체: {total_count}, 만료됨: {expired_count}, 오류: {error_count}")
    if expired_docs:
        print(f"{len(expired_docs)}개의 만료된 파일 삭제됨")

# 스케줄러 설정
scheduler = BackgroundScheduler()
scheduler.add_job(delete_expired_files, 'interval', minutes=1)
scheduler.add_job(cleanup_orphaned_files, 'interval', hours=1)  # 정기적으로 고아 파일 정리
scheduler.start()

# 파일 확장자로 이미지 확인
def is_image_file(filename):
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    ext = os.path.splitext(filename.lower())[1]
    return ext in image_extensions

# 파일 컨텐츠 타입으로 이미지 확인
def is_image_content_type(content_type):
    return content_type and content_type.startswith('image/')

@app.get("/thumbnail/{file_hash}")
async def get_thumbnail(file_hash: str, width: int = 100, height: int = 100):
    # Pillow 라이브러리가 없으면 썸네일 생성 불가
    if Image is None:
        raise HTTPException(status_code=400, detail="Thumbnail generation not available - Pillow not installed")
    
    # 파일 메타데이터 검색
    file_metadata = None
    
    for _, metadata in db.list_all().items():
        if metadata.get("hash", {}).get("sha256") == file_hash:
            file_metadata = metadata
            break
    
    if not file_metadata:
        raise HTTPException(status_code=404, detail="File not found")
    
    # 이미지 파일이 아니면 에러 반환
    file_name = file_metadata.get("file_name", "")
    content_type = file_metadata.get("content_type", "")
    
    if not (is_image_file(file_name) or is_image_content_type(content_type)):
        raise HTTPException(status_code=400, detail="Not an image file")
    
    # 이미지 파일 읽기
    img_data = None
    img_format = "JPEG"  # 기본 포맷
    
    if storage_type == "local":
        file_path = os.path.join(storage.upload_dir, file_hash)
        if os.path.exists(file_path):
            try:
                with open(file_path, "rb") as f:
                    img_data = f.read()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    else:
        # R2에서 파일 가져오기
        try:
            img_data = r2.get_file_bytes(file_hash)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading file from R2: {str(e)}")
    
    if not img_data:
        raise HTTPException(status_code=404, detail="Image data not found")
    
    # 이미지 확장자에 따라 포맷 결정
    if file_name.lower().endswith('.png'):
        img_format = "PNG"
    elif file_name.lower().endswith('.gif'):
        img_format = "GIF"
    
    # 썸네일 생성
    try:
        img = Image.open(io.BytesIO(img_data))
        img.thumbnail((width, height))
        
        # 썸네일을 메모리에 저장
        thumbnail_io = io.BytesIO()
        img.save(thumbnail_io, format=img_format)
        thumbnail_io.seek(0)
        
        # 적절한 MIME 타입 설정
        mime_type = "image/jpeg"
        if img_format == "PNG":
            mime_type = "image/png"
        elif img_format == "GIF":
            mime_type = "image/gif"
        
        return StreamingResponse(thumbnail_io, media_type=mime_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating thumbnail: {str(e)}")

# 파라미터 테스트 엔드포인트
@app.get("/api/test-param")
async def test_param(expire_in_minutes: int = 5):
    """
    파라미터 처리를 테스트하기 위한 엔드포인트
    """
    print(f"테스트 엔드포인트 호출 - expire_in_minutes: {expire_in_minutes} (타입: {type(expire_in_minutes)})")
    return {
        "received_value": expire_in_minutes,
        "type": str(type(expire_in_minutes)),
        "is_valid": isinstance(expire_in_minutes, int) and expire_in_minutes > 0
    }