import os
import shutil
import tempfile
import time
from utils import format_file_size

class LocalStorage:
    def __init__(self, upload_dir="/app/uploads"):
        self.upload_dir = upload_dir
        # 디렉토리가 없으면 생성
        os.makedirs(upload_dir, exist_ok=True)

    def upload_file(self, file_obj, file_name):
        """로컬 파일 시스템에 파일 업로드 (완전 스트리밍 방식)"""
        destination = os.path.join(self.upload_dir, file_name)
        
        try:
            # 목적지 파일이 이미 존재하는지 확인
            if os.path.exists(destination):
                print(f"중복 파일 발견: {destination}, 덮어쓰기")
                os.remove(destination)
            
            # 문자열 경로인 경우 (최적화된 처리)
            if isinstance(file_obj, str) and os.path.isfile(file_obj):
                # 임시 파일 여부 확인
                is_temp_file = file_obj.startswith(tempfile.gettempdir())
                file_size = os.path.getsize(file_obj)
                
                # 디버깅 정보 출력
                print(f"파일 업로드: 경로={file_obj}, 크기={format_file_size(file_size)}, 임시파일={is_temp_file}")
                
                # 대용량 파일 처리 최적화 (직접 이동 또는 버퍼 복사)
                if is_temp_file:
                    # 임시 파일은 이동으로 즉시 처리
                    try:
                        # 직접 이동 (OS 레벨 최적화)
                        shutil.move(file_obj, destination)
                        return True
                    except (shutil.Error, OSError) as e:
                        print(f"임시 파일 이동 실패: {str(e)}")
                        # 이동 실패 시 스트리밍 복사로 대체
                        return self._stream_copy_file(file_obj, destination)
                else:
                    # 일반 파일은 스트리밍 복사 (메모리 사용량 최소화)
                    return self._stream_copy_file(file_obj, destination)
            
            # 파일 객체인 경우
            elif hasattr(file_obj, 'read'):
                # 스트리밍 복사를 통한 최적화
                with open(destination, 'wb') as out_file:
                    # 버퍼 크기 설정 (너무 작으면 성능 저하, 너무 크면 메모리 사용량 증가)
                    buffer_size = 8 * 1024 * 1024  # 8MB 청크
                    
                    # 파일 포인터를 처음으로 되돌림 (필요한 경우)
                    if hasattr(file_obj, 'seek'):
                        file_obj.seek(0)
                    
                    # 청크 복사 최적화
                    bytes_copied = 0
                    chunk_count = 0
                    
                    while True:
                        chunk = file_obj.read(buffer_size)
                        if not chunk:
                            break
                        
                        # 직접 쓰기 및 플러시
                        out_file.write(chunk)
                        out_file.flush()
                        
                        bytes_copied += len(chunk)
                        chunk_count += 1
                    
                    print(f"파일 복사 완료: {bytes_copied} 바이트")
                return True
            else:
                # 지원되지 않는 파일 객체 유형
                print(f"지원되지 않는 파일 객체 유형: {type(file_obj)}")
                return False
                
        except Exception as e:
            print(f"파일 업로드 처리 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
            
    def _stream_copy_file(self, src, dst, buffer_size=8*1024*1024):
        """대용량 파일을 스트리밍 방식으로 복사 (메모리 사용량 최소화)"""
        try:
            # 이미 존재하는 목적지 파일 삭제
            if os.path.exists(dst):
                os.remove(dst)
                
            # 진행 상황 및 성능 통계 변수
            total_size = os.path.getsize(src)
            bytes_copied = 0
            start_time = time.time()
            
            # 스트리밍 복사
            with open(src, 'rb') as src_file:
                with open(dst, 'wb') as dst_file:
                    chunk_count = 0
                    while True:
                        buf = src_file.read(buffer_size)
                        if not buf:
                            break
                            
                        # 디스크에 쓰기
                        dst_file.write(buf)
                        dst_file.flush()
                        
                        # 진행 상황 업데이트
                        bytes_copied += len(buf)
                        chunk_count += 1
                        
                        # 진행 상황 로깅 (100MB마다 또는 10개 청크마다)
                        if chunk_count % 10 == 0 or bytes_copied % (100*1024*1024) < buffer_size:
                            elapsed = time.time() - start_time
                            speed = bytes_copied / elapsed / 1024 / 1024 if elapsed > 0 else 0
                            progress = bytes_copied / total_size * 100 if total_size > 0 else 0
                            print(f"복사 진행률: {progress:.1f}% ({format_file_size(bytes_copied)}/{format_file_size(total_size)}) - {speed:.1f} MB/s")
                        
                        chunk_count += 1
            
            # 복사 완료 통계
            elapsed = time.time() - start_time
            speed = bytes_copied / elapsed / 1024 / 1024 if elapsed > 0 else 0
            print(f"파일 복사 완료: {format_file_size(bytes_copied)}, {elapsed:.1f}초, {speed:.1f} MB/s")
            
            return True
        except Exception as e:
            print(f"스트리밍 복사 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
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
