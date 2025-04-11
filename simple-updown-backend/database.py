# database.py
# Simple NoSQL database implementation using JSON for file metadata storage

import json
import os
import uuid


class FileMetadataDB:
    def __init__(self, filename='file_metadata.json'):
        # Initialize database with a filename
        self.filename = filename
        
        # Load database from file if exists, otherwise create empty database
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as file:
                self.store = json.load(file)
        else:
            self.store = {}
    
    def save(self):
        # Save current database state to file
        with open(self.filename, 'w') as file:
            json.dump(self.store, file, indent=4)
    
    def insert(self, metadata):
        # Generate unique ID and store metadata
        doc_id = str(uuid.uuid4())

        # Convert datetime objects to ISO format strings
        #for key, value in metadata.items():
        #    if isinstance(value, datetime.datetime):
        #        metadata[key] = value.isoformat()

        self.store[doc_id] = metadata
        self.save()
        return doc_id
    
    def update(self, doc_id, metadata):
        # Update existing document
        if doc_id not in self.store:
            raise KeyError("Document ID does not exist.")
        self.store[doc_id] = metadata
        self.save()
    
    def get(self, doc_id):
        # Retrieve document by ID
        return self.store.get(doc_id, None)
    
    def get_by_filename(self, filename):
        # Find document by filename
        for doc_id, metadata in self.store.items():
            if metadata.get('file_name') == filename:
                return doc_id, metadata
        return None, None
    
    def delete(self, doc_id):
        # Remove document from database
        if doc_id in self.store:
            del self.store[doc_id]
            self.save()
        else:
            raise KeyError("Document ID does not exist.")
    
    def list_all(self):
        # Return all documents
        return self.store
