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
  import axios from 'axios';
  
  export default {
    name: 'FilesList',
    data() {
      return {
        files: [],
        loading: true
      }
    },
    mounted() {
      this.fetchFiles();
    },
    methods: {
      async fetchFiles() {
        try {
          const response = await axios.get('/files/');
          this.files = response.data;
        } catch (error) {
          console.error('Error fetching files:', error);
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
      formatDate(date) {
        if (!date) return ''; // date가 undefined일 경우 빈 문자열 변환환
        return `${date.getFullYear()}.${date.getMonth() + 1}.${date.getDate()}`;
      },
      async downloadFile(file) {
        try {
          const response = await axios.get(`/download/${file.hash.sha256}`, { responseType: 'blob' });
          const url = window.URL.createObjectURL(new Blob([response.data]));
          const link = document.createElement('a');
          link.href = url;
          link.setAttribute('download', file.name);
          document.body.appendChild(link);
          link.click();
        } catch (error) {
          console.error('Error downloading file:', error);
        }
      },
      async deleteFile(id) {
        try {
          await axios.delete(`/files/${id}`);
          this.files = this.files.filter(file => file.id !== id);
        } catch (error) {
          console.error('Error deleting file:', error);
        }
      }
    }
  }
  </script>