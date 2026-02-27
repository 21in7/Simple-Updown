import os
import hashlib
import tempfile
import datetime
import uuid
import traceback
from datetime import timedelta
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from database import FileMetadataDB
from local_storage import LocalStorage
from r2_storage import R2Storage
from utils import format_file_size

router = APIRouter()

storage_type = os.getenv("STORAGE_TYPE", "local")
if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

db = FileMetadataDB()


@router.post("/upload/")
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
