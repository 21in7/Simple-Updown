<template>
    <div class="files-container">
      <h2>파일 목록</h2>
      <div v-if="loading" class="loading">로딩 중...</div>
      <div v-else-if="filteredFiles.length === 0" class="no-files">
        업로드된 파일이 없습니다.
      </div>
      <div v-else class="table-container">
        <table class="files-table">
          <thead>
            <tr>
              <th class="file-name-header">파일명</th>
              <th class="file-size-header">크기</th>
              <th class="file-date-header">업로드 날짜</th>
              <th class="file-expire-header">만료일</th>
              <th class="file-actions-header">작업</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="file in filteredFiles" :key="file.hash.sha256" class="file-row">
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
        return this.files.filter(file => 
          file && 
          file.file_size > 0 && 
          file.file_name && 
          file.hash && 
          file.hash.sha256 &&
          // 만료되지 않은 파일만 표시
          new Date(file.expire_time) > now
        );
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
            this.files = response.data.files;
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
      formatFileSize(bytes) {
        if (typeof bytes !== 'number' || isNaN(bytes)) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        else return (bytes / 1048576).toFixed(1) + ' MB';
      },
      formatDate(dateStr) {
        if (!dateStr) return '';
        try {
          const date = new Date(dateStr);
          if (isNaN(date.getTime())) return '';
          return `${date.getFullYear()}.${date.getMonth() + 1}.${date.getDate()} ${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`;
        } catch (error) {
          console.error('Error formatting date:', error);
          return '';
        }
      },
      isExpiringSoon(expireTimeStr) {
        if (!expireTimeStr) return false;
        const now = new Date();
        const expireTime = new Date(expireTimeStr);
        // 24시간 이내에 만료되는 경우 강조 표시
        return (expireTime - now) < 24 * 60 * 60 * 1000;
      },
      getTimeLeft(expireTimeStr) {
        if (!expireTimeStr) return '';
        
        const now = new Date();
        const expireTime = new Date(expireTimeStr);
        const diffMs = expireTime - now;
        
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
      },
      async downloadFile(file) {
        try {
          const response = await axios.get(`/download/${file.hash.sha256}`, { responseType: 'blob' });
          const url = window.URL.createObjectURL(new Blob([response.data]));
          const link = document.createElement('a');
          link.href = url;
          link.setAttribute('download', file.file_name);
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        } catch (error) {
          console.error('Error downloading file:', error);
          
          // 파일이 이미 만료된 경우 (404)
          if (error.response && error.response.status === 404) {
            alert('파일이 만료되어 더 이상 다운로드할 수 없습니다.');
            // 목록에서 제거
            this.files = this.files.filter(f => f.hash.sha256 !== file.hash.sha256);
          } else {
            alert('파일 다운로드 중 오류가 발생했습니다.');
          }
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
</style>