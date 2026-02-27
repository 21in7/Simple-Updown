import os
from database import FileMetadataDB
from local_storage import LocalStorage
from r2_storage import R2Storage

storage_type = os.getenv("STORAGE_TYPE", "local")
if storage_type == "local":
    storage = LocalStorage()
else:
    storage = R2Storage()

db = FileMetadataDB()
