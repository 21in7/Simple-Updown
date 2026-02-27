import os
from fastapi import APIRouter, HTTPException
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


@router.get("/api/files/")
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


@router.delete("/files/{file_hash}")
async def delete_file(file_hash: str):
    result = await db.get_by_hash(file_hash)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    doc_id, _ = result

    if not storage.delete_file(file_hash):
        raise HTTPException(status_code=500, detail="Failed to delete file from storage")

    await db.delete(doc_id)
    return {"message": "File deleted successfully"}
