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
            try:
                with open(self.filename, 'r') as file:
                    self.store = json.load(file)
            except json.JSONDecodeError as e:
                print(f"파일 메타데이터 DB 파싱 오류. 빈 DB로 시작합니다: {str(e)}")
                self.store = {}
            except Exception as e:
                print(f"DB 로드 중 예외 발생. 빈 DB로 시작합니다: {str(e)}")
                self.store = {}
        else:
            self.store = {}
    
    def save(self):
        # Save current database state to file
        try:
            # 임시 파일에 먼저 저장 후 안전하게 이동
            temp_filename = f"{self.filename}.tmp"
            with open(temp_filename, 'w') as file:
                json.dump(self.store, file)
                file.flush()
                os.fsync(file.fileno())  # 디스크에 확실히 쓰기
            
            # 임시 파일을 실제 파일로 안전하게 대체
            if os.path.exists(self.filename):
                os.replace(temp_filename, self.filename)
            else:
                os.rename(temp_filename, self.filename)
                
        except Exception as e:
            print(f"DB 저장 중 오류 발생: {str(e)}")
            # 임시 파일 정리
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except:
                    pass
    
    def insert(self, metadata):
        # Generate unique ID and store metadata
        doc_id = str(uuid.uuid4())

        # 메모리 최적화: 대용량 메타데이터 처리 개선
        self.store[doc_id] = metadata
        
        try:
            self.save()
        except Exception as e:
            print(f"메타데이터 삽입 후 저장 중 오류: {str(e)}")
        
        return doc_id
    
    def update(self, doc_id, metadata):
        # Update existing document
        if doc_id not in self.store:
            raise KeyError("Document ID does not exist.")
        self.store[doc_id] = metadata
        
        try:
            self.save()
        except Exception as e:
            print(f"메타데이터 업데이트 후 저장 중 오류: {str(e)}")
    
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
            try:
                self.save()
            except Exception as e:
                print(f"메타데이터 삭제 후 저장 중 오류: {str(e)}")
        else:
            raise KeyError("Document ID does not exist.")
    
    def list_all(self):
        # Return all documents
        return self.store
