import aiosqlite
import uuid
import os
from typing import Optional, Dict, Any, Tuple

DB_PATH = os.getenv("DB_PATH", "/app/data/file_metadata.db")


class FileMetadataDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    file_hash TEXT UNIQUE NOT NULL,
                    file_name TEXT NOT NULL,
                    file_size INTEGER,
                    content_type TEXT,
                    upload_time TEXT,
                    expire_time TEXT,
                    expire_minutes INTEGER,
                    uploader_ip TEXT,
                    md5_hash TEXT,
                    sha1_hash TEXT
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_hash ON files(file_hash)"
            )
            await db.commit()

    async def insert(self, metadata: Dict[str, Any]) -> str:
        doc_id = str(uuid.uuid4())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO files
                    (id, file_hash, file_name, file_size, content_type,
                     upload_time, expire_time, expire_minutes, uploader_ip,
                     md5_hash, sha1_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    metadata.get("hash", {}).get("sha256"),
                    metadata.get("file_name"),
                    metadata.get("file_size"),
                    metadata.get("content_type"),
                    metadata.get("date") or metadata.get("upload_time"),
                    metadata.get("expire_time"),
                    metadata.get("expire_minutes"),
                    metadata.get("uploader_ip"),
                    metadata.get("hash", {}).get("md5"),
                    metadata.get("hash", {}).get("sha1"),
                ),
            )
            await db.commit()
        return doc_id

    async def get_by_hash(
        self, file_hash: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM files WHERE file_hash = ?", (file_hash,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return row["id"], self._row_to_metadata(row)

    async def list_all(self) -> Dict[str, Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM files") as cursor:
                rows = await cursor.fetchall()
                return {row["id"]: self._row_to_metadata(row) for row in rows}

    async def delete(self, doc_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM files WHERE id = ?", (doc_id,))
            await db.commit()

    async def update_filename(self, doc_id: str, file_name: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE files SET file_name = ? WHERE id = ?", (file_name, doc_id)
            )
            await db.commit()

    def _row_to_metadata(self, row) -> Dict[str, Any]:
        return {
            "file_name": row["file_name"],
            "file_size": row["file_size"],
            "content_type": row["content_type"],
            "upload_time": row["upload_time"],
            "expire_time": row["expire_time"],
            "expire_minutes": row["expire_minutes"],
            "uploader_ip": row["uploader_ip"],
            "hash": {
                "sha256": row["file_hash"],
                "md5": row["md5_hash"],
                "sha1": row["sha1_hash"],
            },
        }
