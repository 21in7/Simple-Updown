<template>
    <div class="files-container">
      <h2>파일 목록</h2>
      <!-- 다중 업로드 완료 메시지 -->
      <div v-if="showMultiUploadMessage" class="toast-message">
        {{ uploadCompleteMessage }}
        <button @click="dismissUploadMessage" class="dismiss-button">×</button>
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
              <th class="file-uploader-header">업로더</th>
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
              <td class="file-uploader-cell">{{ file.uploader_ip ? '업로드 유저: ' + file.uploader_ip : '알 수 없음' }}</td>
              <td class="file-date-cell">{{ formatDate(file.date) }}</td>
              <td class="file-expire-cell" :class="{ 
                'expire-soon': isExpiringSoon(file.expire_time),
                'expire-unlimited': isUnlimited(file.expire_time) || file.expire_minutes === -1
              }">
                {{ formatDate(file.expire_time) }}
                <span class="expire-time-left">({{ getTimeLeft(file.expire_time) }})</span>
                <span v-if="file.expire_minutes" class="expire-original-setting">
                  설정: <strong>{{ getExpirationText(file.expire_minutes) }}</strong>
                </span>
              </td>
              <td class="file-actions-cell">
                <button @click="downloadFile(file)" class="action-button download" title="다운로드">
                  <span class="button-icon">⬇️</span>
                </button>
                <button @click="shareFile(file)" class="action-button share" title="공유 링크 복사">
                  <span class="button-icon">🔗</span>
                </button>
                <button @click="deleteFile(file.hash.sha256)" class="action-button delete" title="삭제">
                  <span class="button-icon">🗑️</span>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <div v-if="showCopyAlert" class="toast-message">
        링크가 클립보드에 복사되었습니다!
      </div>
    </div>
  </template>
  
  <script>
  import { fetchFiles, deleteFile as apiDeleteFile, getDownloadUrl, getThumbnailUrl } from '@/api/filesApi'
  import { formatFileSize, getFileIcon, isImageFile } from '@/utils/fileUtils'
  import { isUnlimited, isExpiringSoon, getTimeLeft, formatDate } from '@/utils/dateUtils'

  export default {
    name: 'FilesList',
    data() {
      return {
        files: [],
        loading: true,
        refreshInterval: null,
        showCopyAlert: false,
        showMultiUploadMessage: false,
        uploadCompleteMessage: ''
      }
    },
    computed: {
      filteredFiles() {
        const now = new Date();
        return this.files.filter(file => {
          try {
            const expireTime = new Date(file.expire_time.endsWith('Z') ? file.expire_time : file.expire_time + 'Z');
            return expireTime > now;
          } catch (e) {
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

      // URL 쿼리에서 업로드 완료 정보 확인
      const query = this.$route.query;
      if (query.upload_complete === 'true') {
        // 쿼리 파라미터에서 업로드 된 파일 수 확인
        const count = query.count ? parseInt(query.count, 10) : 1;
        
        // 다중 업로드 메시지 표시
        if (count > 1) {
          this.uploadCompleteMessage = `${count}개의 파일이 성공적으로 업로드되었습니다.`;
          this.showMultiUploadMessage = true;
        } else {
          this.uploadCompleteMessage = "파일이 성공적으로 업로드되었습니다.";
          this.showMultiUploadMessage = true;
        }
        
        // 3초 후 메시지 숨기기
        setTimeout(() => {
          this.showMultiUploadMessage = false;
          
          // URL에서 쿼리 파라미터 제거
          this.$router.replace({ 
            path: this.$route.path,
            query: {}
          });
        }, 3000);
      }
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
          const data = await fetchFiles();
          if (data && data.files) {
            this.files = data.files.filter(file =>
              file && file.file_name && file.file_size > 0 && file.hash && file.hash.sha256
            );
          } else {
            this.files = [];
          }
        } catch (error) {
          this.files = [];
        } finally {
          this.loading = false;
        }
      },
      isImageFile,
      getFileIcon,
      formatFileSize,
      isUnlimited,
      isExpiringSoon,
      getTimeLeft,
      formatDate,
      getThumbnailUrl(fileHash) {
        return getThumbnailUrl(fileHash) + '?width=80&height=80';
      },
      // 썸네일 로드 실패 시 처리
      onThumbnailError(event) {
        event.target.style.display = 'none';
        event.target.nextElementSibling.style.display = 'block';
      },
      // 파일 공유 링크 생성 및 클립보드 복사
      async shareFile(file) {
        try {
          const shareUrl = `${window.location.origin}/download/${file.hash.sha256}`;
          await navigator.clipboard.writeText(shareUrl);
          
          // 성공 알림 표시
          this.showCopyAlert = true;
          setTimeout(() => {
            this.showCopyAlert = false;
          }, 2000);
        } catch (error) {
          alert('링크 복사에 실패했습니다. 브라우저에서 클립보드 접근을 허용해주세요.');
        }
      },
      downloadFile(file) {
        const link = document.createElement('a');
        link.href = getDownloadUrl(file.hash.sha256);
        link.download = file.file_name;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      },
      async deleteFile(fileHash) {
        if (!confirm('이 파일을 삭제하시겠습니까?')) return;
        try {
          await apiDeleteFile(fileHash);
          this.files = this.files.filter(file => file.hash.sha256 !== fileHash);
        } catch (error) {
          alert('파일 삭제 중 오류가 발생했습니다.');
        }
      },
      getExpirationText(minutes) {
        if (!minutes || isNaN(parseInt(minutes, 10))) return '';
        
        const mins = parseInt(minutes, 10);
        // console.log('expire_minutes 원본값:', minutes, '타입:', typeof minutes, '변환후:', mins);
        
        // 무제한인 경우
        if (mins === -1) {
          return '무제한';
        }
        
        if (mins < 60) {
          return `${mins}분`;
        } else if (mins < 1440) {
          return `${Math.floor(mins / 60)}시간`;
        } else if (mins < 10080) {
          return `${Math.floor(mins / 1440)}일`;
        } else {
          return `${Math.floor(mins / 10080)}주`;
        }
      },
      displayUploadMessage(message) {
        this.showMultiUploadMessage = true;
        this.uploadCompleteMessage = message;
      },
      dismissUploadMessage() {
        this.showMultiUploadMessage = false;
      }
    }
  }
  </script>

<style scoped>
.files-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  position: relative;
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
  table-layout: fixed; /* 테이블 레이아웃 고정 */
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
  word-break: break-word; /* 긴 단어도 줄바꿈 처리 */
}

.files-table tr:hover {
  background-color: #f9f9f9;
}

.file-preview-header, .file-preview-cell {
  width: 80px;
  text-align: center;
}

.file-name-header {
  width: 25%;
}

.file-name-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: normal; /* 긴 파일명 여러 줄 표시 */
}

.file-size-header, .file-size-cell {
  width: 80px;
  text-align: center;
}

.file-uploader-header, .file-uploader-cell {
  width: 120px;
  text-align: center;
  font-size: 14px;
  color: #666;
}

.file-date-header, .file-date-cell {
  width: 150px;
  text-align: center;
}

.file-expire-header, .file-expire-cell {
  width: 150px;
  text-align: center;
}

.file-actions-header, .file-actions-cell {
  width: 130px;
  text-align: center;
  white-space: nowrap;
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

.expire-time-left {
  display: block;
  font-size: 0.85em;
  color: #666;
}

.expire-soon .expire-time-left {
  color: #f44336;
  font-weight: bold;
}

/* 무제한 스타일 */
.expire-unlimited {
  color: #2196f3;
  font-weight: bold;
}

.expire-original-setting {
  display: block;
  font-size: 0.85em;
  color: #666;
}

.action-button {
  margin: 0 3px;
  padding: 8px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s;
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.button-icon {
  font-size: 18px;
}

.download {
  background-color: #4caf50;
  color: white;
}

.download:hover {
  background-color: #388e3c;
}

.share {
  background-color: #2196f3;
  color: white;
}

.share:hover {
  background-color: #1976d2;
}

.delete {
  background-color: #f44336;
  color: white;
}

.delete:hover {
  background-color: #d32f2f;
}

.toast-message {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background-color: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 10px 20px;
  border-radius: 4px;
  font-size: 14px;
  z-index: 9999;
  animation: fade-in-out 2s ease-in-out;
}

@keyframes fade-in-out {
  0% { opacity: 0; }
  20% { opacity: 1; }
  80% { opacity: 1; }
  100% { opacity: 0; }
}

.dismiss-button {
  background: none;
  border: none;
  color: white;
  font-size: 18px;
  cursor: pointer;
  margin-left: 5px;
}
</style>