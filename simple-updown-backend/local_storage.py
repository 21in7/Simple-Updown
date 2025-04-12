import os
import shutil
import tempfile
from pathlib import Path

class LocalStorage:
    def __init__(self, upload_dir="/app/uploads"):
        self.upload_dir = upload_dir
        # 디렉토리가 없으면 생성
        os.makedirs(upload_dir, exist_ok=True)

    def upload_file(self, file_obj, file_name):
        """로컬 파일 시스템에 파일 업로드 (메모리 최적화)"""
        destination = os.path.join(self.upload_dir, file_name)
        
        # 문자열 경로인 경우 (최적화된 처리)
        if isinstance(file_obj, str) and os.path.isfile(file_obj):
            # 메모리 최적화: 파일을 복사하는 대신 이동 (임시 파일의 경우)
            if file_obj.startswith(tempfile.gettempdir()):
                try:
                    shutil.move(file_obj, destination)
                    return True
                except (shutil.Error, OSError):
                    # 이동 실패시 복사로 대체
                    shutil.copy2(file_obj, destination)
                    return True
            else:
                # 임시 디렉토리가 아닌 경우 안전하게 복사
                shutil.copy2(file_obj, destination)
                return True
        
        # 파일 객체인 경우
        try:
            # 파일 객체 유형 식별
            if hasattr(file_obj, 'file'):
                # UploadFile 객체인 경우 내부 파일 객체 사용
                file_to_copy = file_obj.file
            elif hasattr(file_obj, 'read'):
                # 일반 파일 객체인 경우
                file_to_copy = file_obj
            else:
                # 처리할 수 없는 유형
                raise ValueError(f"지원되지 않는 파일 객체 유형: {type(file_obj)}")
            
            # 메모리 최적화: 대용량 파일 스트리밍을 위한 작은 청크 사용
            with open(destination, 'wb') as dest_file:
                # 파일 포인터를 처음으로 되돌림
                file_to_copy.seek(0)
                # 청크 단위로 복사 (버퍼 크기 조정)
                chunk_size = 1024 * 1024  # 1MB 청크
                while True:
                    chunk = file_to_copy.read(chunk_size)
                    if not chunk:
                        break
                    dest_file.write(chunk)
                    # 주기적으로 메모리 비우기
                    if hasattr(dest_file, 'flush'):
                        dest_file.flush()
            
            return True
        except Exception as e:
            print(f"파일 업로드 중 오류: {str(e)}")
            return False


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
        """
        파일을 읽어 바이트로 반환합니다.
        메모리 사용량이 중요한 경우 stream_file 메서드를 사용하는 것이 좋습니다.
        """
        try:
            file_path = os.path.join(self.upload_dir, file_name)
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                print(f"파일을 찾을 수 없음: {file_path}")
                return None
                
            with open(file_path, "rb") as f:
                return f.read()
        except Exception as e:
            print(f"파일 읽기 오류: {str(e)}")
            return None
    
    def stream_file(self, file_name, chunk_size=1024 * 1024):
        """
        파일을 청크 단위로 스트리밍합니다.
        메모리 사용량을 최소화하기 위해 제네레이터를 사용합니다.
        """
        try:
            file_path = os.path.join(self.upload_dir, file_name)
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                print(f"스트리밍할 파일을 찾을 수 없음: {file_path}")
                return None
                
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            print(f"파일 스트리밍 오류: {str(e)}")
            return None
    
    def save_file(self, file_name, file_content):
        """파일 저장하기"""
        try:
            file_path = os.path.join(self.upload_dir, file_name)
            with open(file_path, "wb") as f:
                f.write(file_content)
            return True
        except Exception as e:
            print(f"파일 저장 오류: {str(e)}")
            return False
    
    def save_file_stream(self, file_name, file_stream):
        """
        스트림에서 파일 저장하기 (메모리 효율적)
        """
        try:
            file_path = os.path.join(self.upload_dir, file_name)
            with open(file_path, "wb") as output_file:
                shutil.copyfileobj(file_stream, output_file)
            return True
        except Exception as e:
            print(f"스트림에서 파일 저장 오류: {str(e)}")
            return False
