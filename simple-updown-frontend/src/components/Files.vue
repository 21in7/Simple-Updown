<template>
  <div class="files-container">
    <h2>파일 목록</h2>
    <div v-if="loading" class="loading">로딩 중...</div>
    <div v-else-if="files.length === 0" class="no-files">
      업로드된 파일이 없습니다.
    </div>
    <ul v-else class="file-list">
      <li v-for="file in files" :key="file.id" class="file-item">
        <div class="file-info">
          <span class="file-name">{{ file.name }}</span>
          <span class="file-size">{{ formatFileSize(file.size) }}</span>
          <span class="file-date">{{ formatDate(file.uploadDate) }}</span>
        </div>
        <div class="file-actions">
          <button @click="downloadFile(file)" class="action-button download">
            다운로드
          </button>
          <button @click="deleteFile(file.id)" class="action-button delete">
            삭제
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<script>
export default {
  data() {
    return {
      files: [],
      loading: true
    }
  },
  mounted() {
    // 컴포넌트가 마운트되면 파일 목록 가져오기
    this.fetchFiles();
  },
  methods: {
    fetchFiles() {
      // API에서 파일 목록 가져오기
      // 실제 구현시 axios 등을 사용하여 구현
      
      // 목업 데이터
      setTimeout(() => {
        this.files = [
          {
            id: 1,
            name: '문서.pdf',
            size: 1240000,
            uploadDate: new Date(2025, 3, 10)
          },
          {
            id: 2,
            name: '이미지.jpg',
            size: 543000,
            uploadDate: new Date(2025, 3, 11)
          }
        ];
        this.loading = false;
      }, 1000);
    },
    formatFileSize(bytes) {
      if (bytes < 1024) return bytes + ' B';
      else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
      else return (bytes / 1048576).toFixed(1) + ' MB';
    },
    formatDate(date) {
      return `${date.getFullYear()}.${date.getMonth() + 1}.${date.getDate()}`;
    },
    downloadFile(file) {
      // 파일 다운로드 로직
      console.log('다운로드:', file.name);
    },
    deleteFile(id) {
      // 파일 삭제 로직
      console.log('파일 삭제:', id);
      this.files = this.files.filter(file => file.id !== id);
    }
  }
}
</script>

<style scoped>
.files-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

.loading, .no-files {
  text-align: center;
  padding: 20px;
  color: #666;
}

.file-list {
  list-style: none;
  padding: 0;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  border-bottom: 1px solid #eee;
}

.file-name {
  font-weight: bold;
  margin-right: 15px;
}

.file-size, .file-date {
  color: #666;
  margin-right: 15px;
  font-size: 0.9em;
}

.action-button {
  padding: 8px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  margin-left: 10px;
}

.download {
  background-color: #4CAF50;
  color: white;
}

.delete {
  background-color: #f44336;
  color: white;
}
</style>
