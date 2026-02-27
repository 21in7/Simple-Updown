import os
from typing import Optional


def format_file_size(size_in_bytes: Optional[int]) -> str:
    if size_in_bytes is None or not isinstance(size_in_bytes, (int, float)) or size_in_bytes < 0:
        return "0 B"
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    elif size_in_bytes < 1024 ** 2:
        return f"{size_in_bytes / 1024:.1f} KB"
    elif size_in_bytes < 1024 ** 3:
        return f"{size_in_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_in_bytes / (1024 ** 3):.1f} GB"


def is_image_file(filename: str) -> bool:
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg'}
    ext = os.path.splitext(filename.lower())[1]
    return ext in image_extensions


def is_image_content_type(content_type: str) -> bool:
    return bool(content_type and content_type.startswith('image/'))
