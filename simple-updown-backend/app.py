# app.py
# Main FastAPI application for file upload/download with R2 storage

import os
from dotenv import load_dotenv

# 반드시 스토리지 초기화 전에 호출
load_dotenv()

import hashlib
import tempfile
import datetime
import io
import uuid
import traceback
from datetime import timedelta
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from database import FileMetadataDB
from r2_storage import R2Storage
from local_storage import LocalStorage

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed, thumbnails will not be available")
    Image = None

# 환경 변수로 스토리지 타입 지정
storage_type = os.getenv("STORAGE_TYPE", "local")

# 스토리지 인스턴스 생성
if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

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
    
    # 메모리 최적화를 위한 변수 추가
    file_hash = None
    md5_hash = None
    sha1_hash = None
    file_size = 0
    temp_file_path = None
    
    try:
        # 메모리 최적화: 스트리밍 방식 파일 처리
        # 임시 파일 이름 직접 생성 (임시 디렉토리에)
        temp_dir = tempfile.gettempdir()
        temp_file_name = f"upload_{uuid.uuid4().hex}.tmp"
        temp_file_path = os.path.join(temp_dir, temp_file_name)
        
        # 해시 계산을 위한 객체 초기화
        md5_hash_obj = hashlib.md5()
        sha1_hash_obj = hashlib.sha1()
        sha256_hash_obj = hashlib.sha256()
        
        # 메모리 최적화: 직접 디스크에 쓰기 작업
        print(f"임시 파일 생성: {temp_file_path}")
        
        # 최적화된 청크 처리 (메모리 사용량 최소화)
        chunk_size = 8 * 1024 * 1024  # 8MB 청크 크기
        chunk_count = 0
        processed_size = 0
        
        with open(temp_file_path, 'wb') as temp_file:
            # UploadFile에는 stream 메서드가 없으므로 read 메서드 사용
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:  # 파일의 끝에 도달하면 빈 바이트 문자열 반환
                    break
                
                # 해시 업데이트 (각 청크별로)
                md5_hash_obj.update(chunk)
                sha1_hash_obj.update(chunk)
                sha256_hash_obj.update(chunk)
                
                # 디스크에 직접 쓰기
                temp_file.write(chunk)
                temp_file.flush()
                
                # 파일 크기 업데이트 및 진행 상황 로깅
                chunk_length = len(chunk)
                file_size += chunk_length
                processed_size += chunk_length
                
                # 주기적 진행 상황 출력 (100MB마다)
                if processed_size >= 100 * 1024 * 1024:
                    print(f"업로드 진행 중: {format_file_size(file_size)} 처리됨")
                    processed_size = 0
                
                # 주기적으로 명시적 메모리 정리
                chunk_count += 1
                if chunk_count % 10 == 0:  # 10개 청크마다
                    del chunk
                    gc.collect()
        
        # 진행 상황 최종 출력
        print(f"업로드 완료: 총 {format_file_size(file_size)}")
        
        # 파일 크기가 0이면 에러 반환
        if file_size <= 0:
            raise HTTPException(status_code=400, detail="Empty file cannot be uploaded")
            
        # 최종 해시값 얻기
        md5_hash = md5_hash_obj.hexdigest()
        sha1_hash = sha1_hash_obj.hexdigest()
        file_hash = sha256_hash_obj.hexdigest()
        
        # 메모리 최적화: 해시 객체 명시적 삭제
        del md5_hash_obj, sha1_hash_obj, sha256_hash_obj
        
        # 메모리 정리
        gc.collect()
        
        # 파일 업로드 - 임시 파일 경로를 전달하여 스트림으로 처리
        if storage_type == "local":
            upload_success = storage.upload_file(temp_file_path, file_hash)
            # 업로드 실패 시 예외 발생
            if not upload_success:
                raise HTTPException(status_code=500, detail="Failed to store file")
        else:
            upload_success = r2.upload_file(temp_file_path, file_hash)
            if not upload_success:
                raise HTTPException(status_code=500, detail="Failed to store file in R2")
        
        # 현재 시간 계산 (UTC로 명시)
        now = datetime.datetime.utcnow()
        
        # 만료 시간 계산 (무제한이면 100년)
        if is_unlimited:
            expire_time = now + timedelta(days=36500)  # 약 100년
        else:
            expire_time = now + timedelta(minutes=expire_in_minutes)
        
        # 최소 메타데이터만 생성
        metadata = {
            "file_name": file.filename,
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
        
        # 메타데이터 저장 (DB에 삽입)
        doc_id = db.insert(metadata)
        
        # 공유 URL 생성
        base_url = str(request.base_url).rstrip("/")
        share_url = f"{base_url}/download/{file_hash}"
        
        # 명시적 메모리 정리
        gc.collect()
        
        # 최소한의 응답 데이터만 반환
        return {
            "success": True,
            "message": "File uploaded successfully.",
            "redirect_to": "/files/",
            "file_info": {
                "file_name": file.filename,
                "file_size": file_size,
                "formatted_size": format_file_size(file_size),
                "hash": file_hash,
                "share_url": share_url
            }
        }
    except Exception as e:
        # 에러 로깅
        print(f"파일 업로드 중 오류 발생: {str(e)}")
        # 스택 트레이스 출력 (디버깅용)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")
    finally:
        # 메모리 최적화: 임시 파일 정리 보장
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print("임시 파일 정리 완료")
            except Exception as e:
                print(f"임시 파일 삭제 실패: {str(e)}")
        
        # FastAPI UploadFile 파일 정리
        await file.close()
        
        # 메모리 관리: 명시적 가비지 컬렉션 호출
        gc.collect()

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
    
    # 파일 다운로드 제공
    try:
        # 컨텐츠 타입 결정
        content_type = file_metadata.get("content_type", "application/octet-stream")
        filename = file_metadata.get("file_name", "unknown")
        
        # 스트리밍 처리를 위한 함수
        def file_streamer():
            try:
                if storage_type == "local":
                    file_path = os.path.join(storage.upload_dir, file_hash)
                    if os.path.exists(file_path):
                        # 청크 단위로 스트리밍
                        with open(file_path, 'rb') as f:
                            while chunk := f.read(1024 * 1024):  # 1MB 청크
                                yield chunk
                    else:
                        # 메타데이터는 있지만 파일이 없는 경우
                        print(f"로컬 스토리지에 파일 없음: {file_path}")
                        db.delete(doc_id)
                        raise HTTPException(status_code=404, detail="File not found")
                else:
                    # R2 스토리지는 StreamingResponse를 활용
                    stream = r2.get_file_stream(file_hash)
                    if stream:
                        for chunk in stream:
                            yield chunk
                    else:
                        # 메타데이터는 있지만 파일이 없는 경우
                        print(f"R2 스토리지에 파일 없음: {file_hash}")
                        db.delete(doc_id)
                        raise HTTPException(status_code=404, detail="File not found")
            except Exception as e:
                print(f"파일 스트리밍 중 오류 발생: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error streaming file: {str(e)}")
        
        # 스트리밍 응답 반환
        return StreamingResponse(
            file_streamer(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )
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
    
    # 요청된 크기 제한 (너무 큰 썸네일 방지)
    width = min(width, 500)
    height = min(height, 500)
    
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
    
    # 썸네일 캐시 디렉토리 (메모리 사용 줄이기 위한 썸네일 캐싱)
    thumbnail_dir = os.path.join(os.path.dirname(storage.upload_dir), "thumbnails")
    os.makedirs(thumbnail_dir, exist_ok=True)
    
    # 썸네일 캐시 키 생성 (파일 해시 + 크기)
    cache_key = f"{file_hash}_{width}x{height}"
    thumbnail_path = os.path.join(thumbnail_dir, cache_key)
    
    # 캐시된 썸네일이 있으면 바로 반환
    if os.path.exists(thumbnail_path):
        try:
            # 이미지 포맷 결정
            img_format = "JPEG"
            mime_type = "image/jpeg"
            
            if file_name.lower().endswith('.png'):
                img_format = "PNG"
                mime_type = "image/png"
            elif file_name.lower().endswith('.gif'):
                img_format = "GIF"
                mime_type = "image/gif"
                
            # 캐시된 썸네일 반환
            return FileResponse(
                thumbnail_path, 
                media_type=mime_type,
                headers={"Cache-Control": "max-age=3600, public"}  # 1시간 캐싱
            )
        except Exception:
            # 캐시 파일 엑세스 오류 시 무시하고 다시 생성
            pass
    
    # 이미지 데이터 스트림으로 읽기
    img_data = None
    
    try:
        if storage_type == "local":
            file_path = os.path.join(storage.upload_dir, file_hash)
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Image file not found")
                
            # 이미지 포맷 결정
            img_format = "JPEG"
            mime_type = "image/jpeg"
            
            if file_name.lower().endswith('.png'):
                img_format = "PNG"
                mime_type = "image/png"
            elif file_name.lower().endswith('.gif'):
                img_format = "GIF"
                mime_type = "image/gif"
            
            try:
                # 로우 레벨로 이미지 처리 - 메모리 사용량 최적화
                with Image.open(file_path) as img:
                    # 큰 이미지는 리사이즈 전에 크기 줄이기
                    if max(img.width, img.height) > 2000:
                        # 대략적으로 크기 조정 (메모리 효율을 위해)
                        factor = 2000 / max(img.width, img.height)
                        intermediate_size = (int(img.width * factor), int(img.height * factor))
                        img = img.resize(intermediate_size, Image.LANCZOS)
                    
                    # 최종 썸네일 생성
                    img.thumbnail((width, height), Image.LANCZOS)
                    
                    # 알파 채널 처리 (메모리 최적화)
                    if img.mode == 'RGBA' and img_format == 'JPEG':
                        img = img.convert('RGB')
                    
                    # 썸네일을 캐시 파일로 저장
                    img.save(thumbnail_path, format=img_format, quality=85, optimize=True)
                    
                    # 캐시된 파일 반환
                    return FileResponse(
                        thumbnail_path, 
                        media_type=mime_type,
                        headers={"Cache-Control": "max-age=3600, public"}  # 1시간 캐싱
                    )
            except Exception as e:
                print(f"썸네일 생성 중 오류: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error generating thumbnail: {str(e)}")
        else:
            # R2 스토리지는 바이트 데이터로 처리
            img_data = r2.get_file_bytes(file_hash)
            if not img_data:
                raise HTTPException(status_code=404, detail="Image data not found")
            
            # 이미지 포맷 결정
            img_format = "JPEG"
            mime_type = "image/jpeg"
            
            if file_name.lower().endswith('.png'):
                img_format = "PNG"
                mime_type = "image/png"
            elif file_name.lower().endswith('.gif'):
                img_format = "GIF"
                mime_type = "image/gif"
            
        try:
            # Pillow 처리 최적화
            with Image.open(file_path) as img:
                # 메모리 최적화: 이미지 처리 전 모드 최적화
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                    
                # 큰 이미지 처리 최적화
                if max(img.width, img.height) > 2000:
                    # 단계적 리사이징으로 메모리 사용량 감소
                    resize_steps = []
                    current_size = max(img.width, img.height)
                    target_size = 2000
                    
                    # 한 번에 50% 이상 줄이지 않도록 단계 계산
                    while current_size > target_size * 1.5:
                        current_size = int(current_size * 0.7)  # 30% 감소
                        resize_steps.append(current_size)
                    
                    # 최종 목표 크기 추가
                    resize_steps.append(target_size)
                    
                    # 단계적으로 크기 줄이기
                    for step_size in resize_steps:
                        ratio = step_size / max(img.width, img.height)
                        new_size = (int(img.width * ratio), int(img.height * ratio))
                        img = img.resize(new_size, Image.LANCZOS)
                        
                        # 각 단계 후 가비지 컬렉션
                        gc.collect()
                
                # 썸네일 생성 (기존 코드 유지)
                img.thumbnail((width, height), Image.LANCZOS)
                
                # 메모리 최적화: 썸네일 저장 최적화
                save_options = {}
                if img_format == "JPEG":
                    save_options = {'quality': 85, 'optimize': True}
                elif img_format == "PNG":
                    save_options = {'optimize': True, 'compress_level': 6}
                
                # 저장 전 이미지 메모리 최적화
                if img.mode == 'RGBA' and img_format == 'JPEG':
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])  # 3이 알파 채널
                    img = background
                
                img.save(thumbnail_path, format=img_format, **save_options)
                
                # 이미지 객체 명시적 정리
                img.close()
                del img
                
                # 가비지 컬렉션
                gc.collect()
        except Exception as e:
            print(f"썸네일 생성 중 오류: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error generating thumbnail: {str(e)}")
    except Exception as e:
        print(f"이미지 처리 중 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")

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