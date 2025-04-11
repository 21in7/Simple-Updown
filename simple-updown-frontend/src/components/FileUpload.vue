<template>
    <div class="upload-container">
      <h2>파일 업로드</h2>
      <div class="upload-area" @dragover.prevent @drop.prevent="onDrop">
        <input 
          type="file" 
          ref="fileInput" 
          @change="onFileSelected" 
          style="display: none" 
        />
        <button @click="$refs.fileInput.click()" class="upload-button">
          파일 선택
        </button>
        <p>또는 파일을 여기에 드래그 앤 드롭하세요</p>
      </div>
      <div v-if="selectedFile" class="file-info">
        <p>선택된 파일: {{ selectedFile.name }}</p>
        <button @click="uploadFile" class="upload-button">업로드</button>
      </div>
      <div v-if="uploadProgress > 0" class="progress-bar">
        <div class="progress" :style="{ width: uploadProgress + '%' }"></div>
        <span>{{ uploadProgress }}%</span>
      </div>
    </div>
  </template>
  
  <script>
  import axios from 'axios';
  
  export default {
    name: 'FileUpload',
    data() {
      return {
        selectedFile: null,
        uploadProgress: 0
      }
    },
    methods: {
      onFileSelected(event) {
        this.selectedFile = event.target.files[0];
      },
      onDrop(event) {
        this.selectedFile = event.dataTransfer.files[0];
      },
      async uploadFile() {
        if (!this.selectedFile) return;
        
        const formData = new FormData();
        formData.append('file', this.selectedFile);
        
        try {
          const response = await axios.post('/upload/', formData, {
            headers: {
              'Content-Type': 'multipart/form-data'
            },
            onUploadProgress: progressEvent => {
              this.uploadProgress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            }
          });
          if (response.data.success) {
            this.$router.push({
              path: '/files/',
              query: { upload_complete: 'true' }
            });
            this.$emit('upload-complete');
          }
          console.log('파일 업로드 완료:', response.data);
        } catch (error) {
          console.error('Error uploading file:', error);
        }
      }
    }
  }
  </script>