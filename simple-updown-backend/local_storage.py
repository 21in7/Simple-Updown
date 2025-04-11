import os
import shutil
from pathlib import Path

class LocalStorage:
    def __init__(self, upload_dir="/app/uploads"):
        self.upload_dir = upload_dir
        # 디렉토리가 없으면 생성
        os.makedirs(upload_dir, exist_ok=True)

    def upload_file(self, file_obj, file_name):
        """로컬 파일 시스템에 파일 업로드"""
        destination = os.path.join(self.upload_dir, file_name)
        
        # 파일 객체인지 확인 (SpooledTemporaryFile, TemporaryFile, UploadFile 등)
        if hasattr(file_obj, 'file'):
            # UploadFile 객체인 경우 내부 파일 객체 사용
            file_to_copy = file_obj.file
        elif hasattr(file_obj, 'read'):
            # 일반 파일 객체인 경우
            file_to_copy = file_obj
        else:
            # 문자열 경로인 경우
            shutil.copy2(file_obj, destination)
            return f"/files/{file_name}"

        # 파일 객체일 경우 내용 복사
        with open(destination, 'wb') as dest_file:
            # 파일 포인터를 처음으로 되돌림
            file_to_copy.seek(0)
            # 내용 복사
            shutil.copyfileobj(file_to_copy, dest_file)
        
        return f"/files/{file_name}"  # 파일 접근 URL 반환

    def delete_file(self, file_name):
        """파일 삭제"""
        file_path = os.path.join(self.upload_dir, file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

    def get_file_url(self, file_name):
        """파일 URL 생성"""
        return f"/files/{file_name}"

    def file_exists(self, file_name):
        """파일 존재 여부 확인"""
        file_path = os.path.join(self.upload_dir, file_name)
        return os.path.exists(file_path) and os.path.isfile(file_path)

    def get_file_bytes(self, file_name):
        """파일을 바이트로 읽어오기"""
        file_path = os.path.join(self.upload_dir, file_name)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            print(f"파일이 존재하지 않음: {file_path}")
            return None
        
        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"파일 읽기 오류: {file_path} - {str(e)}")
            return None
