import os
import io
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from database import FileMetadataDB
from local_storage import LocalStorage
from r2_storage import R2Storage
from utils import is_image_file, is_image_content_type

router = APIRouter()

storage_type = os.getenv("STORAGE_TYPE", "local")
if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

db = FileMetadataDB()

try:
    from PIL import Image
except ImportError:
    Image = None


@router.get("/thumbnail/{file_hash}")
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
