<template>
    <div class="files-container">
      <h2>파일 목록</h2>
      <!-- 디버깅 정보 표시 -->
      <div class="debug-info">
        <p>총 파일 수: {{ files.length }}</p>
        <p>필터링 후 파일 수: {{ filteredFiles.length }}</p>
      </div>
      
      <div v-if="loading" class="loading">로딩 중...</div>
      <div v-else-if="filteredFiles.length === 0" class="no-files">
        업로드된 파일이 없습니다.
      </div>
      <div v-else class="table-container">
        <table class="files-table">
          <thead>
            <tr>
              <th class="file-preview-header">미리보기</th>
              <th class="file-name-header">파일명</th>
              <th class="file-size-header">크기</th>
              <th class="file-date-header">업로드 날짜</th>
              <th class="file-expire-header">만료일</th>
              <th class="file-actions-header">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="file in filteredFiles" :key="file.hash.sha256" class="file-row">
              <td class="file-preview-cell">
                <img v-if="isImageFile(file.file_name)" :src="getThumbnailUrl(file.hash.sha256)" 
                  class="file-thumbnail" alt="썸네일" @error="onThumbnailError" />
                <div v-else class="file-icon">
                  {{ getFileIcon(file.file_name) }}
                </div>
              </td>
              <td class="file-name-cell">{{ file.file_name }}</td>
              <td class="file-size-cell">{{ file.formatted_size || formatFileSize(file.file_size) }}</td>
              <td class="file-date-cell">{{ formatDate(file.date) }}</td>
              <td class="file-expire-cell" :class="{ 'expire-soon': isExpiringSoon(file.expire_time) }">
                {{ formatDate(file.expire_time) }}
                <span class="expire-time-left">({{ getTimeLeft(file.expire_time) }})</span>
              </td>
              <td class="file-actions-cell">
                <button @click="downloadFile(file)" class="action-button download">
                  다운로드
                </button>
                <button @click="deleteFile(file.hash.sha256)" class="action-button delete">
                  삭제
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </template>
  
  <script>
  import axios from 'axios';
  
  export default {
    name: 'FilesList',
    data() {
      return {
        files: [],
        loading: true,
        refreshInterval: null
      }
    },
    computed: {
      filteredFiles() {
        const now = new Date();
        console.log('현재 시간:', now.toISOString());
        
        // 유효성 검사는 fetchFiles에서 이미 수행했으므로 여기서는 만료 시간만 확인
        return this.files.filter(file => {
          try {
            // UTC 시간 처리
            let expireTime;
            if (file.expire_time.endsWith('Z')) {
              expireTime = new Date(file.expire_time);
            } else {
              // Z가 없는 경우 수동으로 UTC 처리
              expireTime = new Date(file.expire_time + 'Z');
            }
            
            console.log(`파일 ${file.file_name} 만료 시간:`, file.expire_time);
            console.log(`만료여부 비교 결과:`, expireTime > now, `(${expireTime.getTime()} > ${now.getTime()})`);
            
            return expireTime > now;
          } catch (e) {
            console.error('만료 시간 파싱 오류:', e, file);
            return false;
          }
        });
      }
    },
    mounted() {
      this.fetchFiles();
      // 1분마다 파일 목록 새로고침 (만료된 파일 자동 필터링)
      this.refreshInterval = setInterval(() => {
        this.fetchFiles();
      }, 60000);
    },
    beforeUnmount() {
      // 컴포넌트 언마운트 시 인터벌 정리
      if (this.refreshInterval) {
        clearInterval(this.refreshInterval);
      }
    },
    methods: {
      async fetchFiles() {
        try {
          const response = await axios.get('/api/files/');
          if (response.data && response.data.files) {
            // 디버깅: 서버로부터 받은 원본 파일 목록
            console.log('서버에서 받은 파일 목록:', response.data.files);
            
            // 유효하지 않은 파일은 필터링하여 제외
            this.files = response.data.files.filter(file => {
              const isValid = file && 
                file.file_name && 
                file.file_size > 0 &&
                file.hash && 
                file.hash.sha256;
              
              if (!isValid) {
                console.warn('유효하지 않은 파일 제외:', file);
              }
              
              return isValid;
            });
            
            // 필터링 후 남은 파일 목록
            console.log('필터링 후 파일 목록:', this.files);
          } else {
            this.files = [];
            console.error('Invalid response format:', response.data);
          }
        } catch (error) {
          console.error('Error fetching files:', error);
          this.files = [];
        } finally {
          this.loading = false;
        }
      },
      // 이미지 파일인지 확인
      isImageFile(filename) {
        if (!filename) return false;
        const lowerFilename = filename.toLowerCase();
        return lowerFilename.endsWith('.jpg') || 
               lowerFilename.endsWith('.jpeg') || 
               lowerFilename.endsWith('.png') || 
               lowerFilename.endsWith('.gif') || 
               lowerFilename.endsWith('.webp') || 
               lowerFilename.endsWith('.bmp');
      },
      // 썸네일 URL 가져오기
      getThumbnailUrl(fileHash) {
        return `/thumbnail/${fileHash}?width=80&height=80`;
      },
      // 파일 아이콘 가져오기
      getFileIcon(filename) {
        if (!filename) return '📄';
        
        const lowerFilename = filename.toLowerCase();
        if (this.isImageFile(lowerFilename)) return '🖼️';
        if (lowerFilename.endsWith('.pdf')) return '📕';
        if (lowerFilename.endsWith('.doc') || lowerFilename.endsWith('.docx')) return '📝';
        if (lowerFilename.endsWith('.xls') || lowerFilename.endsWith('.xlsx')) return '📊';
        if (lowerFilename.endsWith('.ppt') || lowerFilename.endsWith('.pptx')) return '📊';
        if (lowerFilename.endsWith('.zip') || lowerFilename.endsWith('.rar')) return '🗜️';
        if (lowerFilename.endsWith('.txt')) return '📄';
        
        return '📁';
      },
      // 썸네일 로드 실패 시 처리
      onThumbnailError(event) {
        event.target.style.display = 'none';
        event.target.nextElementSibling.style.display = 'block';
      },
      formatFileSize(bytes) {
        if (typeof bytes !== 'number' || isNaN(bytes)) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        else return (bytes / 1048576).toFixed(1) + ' MB';
      },
      formatDate(dateStr) {
        if (!dateStr) return '';
        try {
          // UTC 시간을 로컬 시간으로 변환
          console.log(`formatDate 원본 문자열:`, dateStr);
          
          // UTC 시간대 처리 (Z가 있으면 UTC)
          let date;
          if (dateStr.endsWith('Z')) {
            date = new Date(dateStr);
          } else {
            // Z가 없는 경우 수동으로 UTC 처리
            date = new Date(dateStr + 'Z');
          }
          
          console.log(`변환된 날짜 객체:`, date);
          console.log(`로컬 시간으로:`, new Date(date).toLocaleString());
          
          if (isNaN(date.getTime())) {
            console.error('유효하지 않은 날짜:', dateStr);
            return '날짜 오류';
          }
          
          // 로컬 시간으로 포맷팅
          return `${date.getFullYear()}.${(date.getMonth() + 1).toString().padStart(2, '0')}.${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
        } catch (error) {
          console.error('Error formatting date:', error);
          return '날짜 오류';
        }
      },
      isExpiringSoon(expireTimeStr) {
        if (!expireTimeStr) return false;
        const now = new Date();
        
        // UTC 시간 처리
        let expireTime;
        if (expireTimeStr.endsWith('Z')) {
          expireTime = new Date(expireTimeStr);
        } else {
          // Z가 없는 경우 수동으로 UTC 처리
          expireTime = new Date(expireTimeStr + 'Z');
        }
        
        // 24시간 이내에 만료되는 경우 강조 표시
        return (expireTime - now) < 24 * 60 * 60 * 1000;
      },
      getTimeLeft(expireTimeStr) {
        if (!expireTimeStr) return '';
        
        try {
          const now = new Date();
          
          // UTC 시간을 처리
          let expireTime;
          if (expireTimeStr.endsWith('Z')) {
            expireTime = new Date(expireTimeStr);
          } else {
            // Z가 없는 경우 수동으로 UTC 처리
            expireTime = new Date(expireTimeStr + 'Z');
          }
          
          console.log(`getTimeLeft - 현재시간: ${now.toISOString()}, 만료시간: ${expireTimeStr}, 변환된 만료시간: ${expireTime.toISOString()}`);
          
          const diffMs = expireTime - now;
          console.log(`시간차이(ms): ${diffMs}`);
          
          if (diffMs <= 0) return '만료됨';
          
          const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000));
          const diffHours = Math.floor((diffMs % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
          const diffMinutes = Math.floor((diffMs % (60 * 60 * 1000)) / (60 * 1000));
          
          if (diffDays > 0) {
            return `${diffDays}일 ${diffHours}시간 남음`;
          } else if (diffHours > 0) {
            return `${diffHours}시간 ${diffMinutes}분 남음`;
          } else {
            return `${diffMinutes}분 남음`;
          }
        } catch (error) {
          console.error('Error calculating time left:', error);
          return '시간 계산 오류';
        }
      },
      async downloadFile(file) {
        try {
          console.log(`파일 다운로드 요청: ${file.file_name}, 해시: ${file.hash.sha256}`);
          
          const response = await axios.get(`/download/${file.hash.sha256}`, { 
            responseType: 'blob',
            timeout: 30000 // 30초 타임아웃 설정
          });
          
          console.log('다운로드 응답 성공:', response.status, response.headers);
          
          const contentType = response.headers['content-type'] || 'application/octet-stream';
          const url = window.URL.createObjectURL(new Blob([response.data], { type: contentType }));
          const link = document.createElement('a');
          link.href = url;
          link.setAttribute('download', file.file_name);
          document.body.appendChild(link);
          link.click();
          
          // 정리
          setTimeout(() => {
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
          }, 100);
          
          console.log('파일 다운로드 완료');
        } catch (error) {
          console.error('Error downloading file:', error);
          
          let errorMessage = '파일 다운로드 중 오류가 발생했습니다.';
          
          // 상태 코드에 따른 오류 메시지
          if (error.response) {
            console.error('서버 응답:', error.response.status, error.response.data);
            
            // 404 에러 (파일 없음 또는 만료됨)
            if (error.response.status === 404) {
              errorMessage = '파일이 만료되었거나 존재하지 않습니다.';
              // 목록에서 제거
              this.files = this.files.filter(f => f.hash.sha256 !== file.hash.sha256);
            } 
            // 500 에러 (서버 내부 오류)
            else if (error.response.status === 500) {
              errorMessage = '서버 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요.';
            }
          } 
          // 연결 문제 (네트워크 등)
          else if (error.request) {
            console.error('요청 실패:', error.request);
            errorMessage = '서버에 연결할 수 없습니다. 네트워크 연결을 확인해주세요.';
          }
          
          alert(errorMessage);
        }
      },
      async deleteFile(fileHash) {
        try {
          await axios.delete(`/files/${fileHash}`);
          this.files = this.files.filter(file => file.hash.sha256 !== fileHash);
        } catch (error) {
          console.error('Error deleting file:', error);
          alert('파일 삭제 중 오류가 발생했습니다.');
        }
      }
    }
  }
  </script>

<style scoped>
.files-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

h2 {
  text-align: center;
  margin-bottom: 20px;
  color: #333;
}

.loading, .no-files {
  text-align: center;
  padding: 20px;
  font-size: 16px;
  color: #666;
  background-color: #f9f9f9;
  border-radius: 5px;
}

.table-container {
  overflow-x: auto;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-radius: 5px;
}

.files-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  background-color: white;
}

.files-table th {
  background-color: #f5f5f5;
  padding: 12px 15px;
  font-weight: bold;
  color: #333;
  border-bottom: 2px solid #ddd;
}

.files-table td {
  padding: 12px 15px;
  border-bottom: 1px solid #eee;
  vertical-align: middle;
}

.files-table tr:hover {
  background-color: #f9f9f9;
}

.file-preview-cell {
  width: 80px;
  text-align: center;
}

.file-thumbnail {
  width: 80px;
  height: 80px;
  object-fit: contain;
  border-radius: 4px;
  border: 1px solid #ddd;
  background-color: #f9f9f9;
}

.file-icon {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  background-color: #f9f9f9;
  border-radius: 4px;
  border: 1px solid #ddd;
}

.file-name-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size-cell {
  width: 100px;
  text-align: center;
}

.file-date-cell {
  width: 150px;
  text-align: center;
}

.file-expire-cell {
  width: 200px;
  text-align: center;
}

.expire-time-left {
  display: block;
  font-size: 0.85em;
  color: #666;
}

.expire-soon .expire-time-left {
  color: #f44336;
  font-weight: bold;
}

.file-actions-cell {
  width: 180px;
  text-align: center;
}

.action-button {
  margin: 0 5px;
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
}

.download {
  background-color: #4caf50;
  color: white;
}

.download:hover {
  background-color: #388e3c;
}

.delete {
  background-color: #f44336;
  color: white;
}

.delete:hover {
  background-color: #d32f2f;
}

.debug-info {
  margin-bottom: 20px;
  padding: 10px;
  background-color: #f0f0f0;
  border-radius: 5px;
  font-size: 14px;
}
</style>