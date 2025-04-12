<template>
  <div class="upload-container" @dragover.prevent @drop.prevent="onDrop">
    <h2>파일 업로드</h2>
    <div class="upload-area">
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
      
      <div class="expiration-selector">
        <label for="expiration-time">유지 기간:</label>
        <select id="expiration-time" v-model.number="expirationMinutes">
          <option :value="5">5분</option>
          <option :value="60">1시간</option>
          <option :value="1440">1일</option>
          <option :value="4320">3일</option>
          <option :value="10080">7일</option>
          <option :value="21600">15일</option>
        </select>
      </div>
      
      <button @click="uploadFile" class="upload-button">업로드</button>
    </div>
    <div v-if="uploadProgress > 0" class="progress-bar">
      <div class="progress" :style="{ width: uploadProgress + '%' }"></div>
      <span>{{ uploadProgress }}%</span>
    </div>
    
    <div v-if="isDragging" class="drag-overlay">
      <div class="drag-message">
        <i class="drag-icon">⬆️</i>
        <p>파일을 여기에 놓으세요</p>
      </div>
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
      uploadProgress: 0,
      expirationMinutes: 5,
      isDragging: false
    }
  },
  created() {
    window.addEventListener('dragenter', this.handleDragEnter)
    window.addEventListener('dragleave', this.handleDragLeave)
  },
  beforeUnmount() {
    window.removeEventListener('dragenter', this.handleDragEnter)
    window.removeEventListener('dragleave', this.handleDragLeave)
  },
  methods: {
    onFileSelected(event) {
      this.selectedFile = event.target.files[0];
    },
    onDrop(event) {
      this.isDragging = false;
      if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
        this.selectedFile = event.dataTransfer.files[0];
      }
    },
    handleDragEnter(event) {
      event.preventDefault();
      this.isDragging = true;
    },
    handleDragLeave(event) {
      event.preventDefault();
      // 실제 페이지 떠날 때만 드래그 오버레이 숨기기
      if (!event.relatedTarget || 
          event.relatedTarget.nodeName === 'HTML') {
        this.isDragging = false;
      }
    },
    async uploadFile() {
      if (!this.selectedFile) return;
      
      // 디버깅 로그 추가
      console.log('업로드 시작할 파일:', {
        name: this.selectedFile.name,
        type: this.selectedFile.type,
        size: this.selectedFile.size
      });
      console.log('선택된 유지 기간(분):', this.expirationMinutes, '타입:', typeof this.expirationMinutes);
      
      const formData = new FormData();
      formData.append('file', this.selectedFile);
      // 명시적으로 숫자 변환 후 추가
      const minutes = parseInt(this.expirationMinutes, 10);
      formData.append('expire_in_minutes', minutes);
      
      console.log('FormData expire_in_minutes 값:', minutes, '타입:', typeof minutes);
      
      try {
        // 업로드 요청 전송 시 URL 파라미터로도 추가
        const url = `/upload/?expire_in_minutes=${minutes}`;
        const response = await axios.post(url, formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          },
          onUploadProgress: progressEvent => {
            this.uploadProgress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          }
        });
        
        // 업로드 응답 로깅
        console.log('업로드 응답:', response.data);
        
        if (response.data.success) {
          // 파일 목록 페이지로 이동하기 전에 500ms 지연
          setTimeout(() => {
            this.$router.push({
              path: '/files/',
              query: { upload_complete: 'true' }
            });
            this.$emit('upload-complete');
          }, 500);
        }
      } catch (error) {
        console.error('Error uploading file:', error);
        if (error.response) {
          //console.error('서버 응답:', error.response.data);
        }
      }
    }
  }
}
</script>

<style scoped>
.upload-container {
  position: relative;
  max-width: 600px;
  margin: 0 auto;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  background-color: #fff;
}

h2 {
  text-align: center;
  margin-bottom: 20px;
  color: #333;
}

.upload-area {
  border: 2px dashed #ccc;
  border-radius: 5px;
  padding: 30px;
  text-align: center;
  margin-bottom: 20px;
  background-color: #f9f9f9;
  transition: background-color 0.3s, border-color 0.3s;
}

.upload-area:hover {
  background-color: #f0f0f0;
  border-color: #999;
}

.upload-button {
  background-color: #4caf50;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  margin: 10px 0;
  transition: background-color 0.3s;
}

.upload-button:hover {
  background-color: #388e3c;
}

.file-info {
  background-color: #f5f5f5;
  padding: 15px;
  border-radius: 5px;
  margin-bottom: 20px;
}

.progress-bar {
  height: 20px;
  background-color: #e0e0e0;
  border-radius: 10px;
  overflow: hidden;
  position: relative;
  margin-top: 15px;
}

.progress {
  height: 100%;
  background-color: #4caf50;
  transition: width 0.3s;
}

.progress-bar span {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  text-align: center;
  line-height: 20px;
  color: white;
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.5);
  font-size: 12px;
}

.expiration-selector {
  margin: 15px 0;
  display: flex;
  align-items: center;
}

.expiration-selector label {
  margin-right: 10px;
  font-weight: bold;
}

.expiration-selector select {
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #ccc;
  background-color: white;
}

.drag-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.7);
  z-index: 1000;
  display: flex;
  justify-content: center;
  align-items: center;
}

.drag-message {
  background-color: white;
  padding: 30px 50px;
  border-radius: 10px;
  text-align: center;
}

.drag-icon {
  font-size: 40px;
  margin-bottom: 10px;
  display: block;
}
</style>