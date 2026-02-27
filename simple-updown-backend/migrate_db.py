"""기존 file_metadata.json을 SQLite DB로 마이그레이션"""
import json
import asyncio
import os
import sys


async def migrate(json_path: str, db_path: str) -> None:
    if not os.path.exists(json_path):
        print(f"마이그레이션할 JSON 파일 없음: {json_path}")
        return

    from database import FileMetadataDB

    db = FileMetadataDB(db_path)
    await db.init()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    for doc_id, metadata in data.items():
        try:
            await db.insert(metadata)
            count += 1
        except Exception as e:
            print(f"  건너뜀 (doc_id={doc_id}): {e}")

    print(f"마이그레이션 완료: {count}개 파일")


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "file_metadata.json"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "/app/data/file_metadata.db"
    asyncio.run(migrate(json_path, db_path))
