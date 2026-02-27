import os
import datetime
from urllib.parse import quote
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from database import FileMetadataDB
from local_storage import LocalStorage
from r2_storage import R2Storage

router = APIRouter()

storage_type = os.getenv("STORAGE_TYPE", "local")
if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

db = FileMetadataDB()


@router.get("/download/{file_hash}")
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
