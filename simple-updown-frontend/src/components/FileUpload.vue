<template>
  <div class="upload-container" @dragover.prevent @drop.prevent="onDrop">
    <h2>파일 업로드</h2>
    <div class="upload-area">
      <input 
        type="file" 
        ref="fileInput" 
        @change="onFileSelected" 
        style="display: none"
        multiple
      />
      <button @click="$refs.fileInput.click()" class="upload-button">
        파일 선택
      </button>
      <p>또는 파일을 여기에 드래그 앤 드롭하세요 (여러 파일 가능)</p>
    </div>
    
    <div v-if="selectedFiles.length > 0" class="files-list">
      <h3>선택된 파일 ({{ selectedFiles.length }}개)</h3>
      
      <div class="expiration-selector">
        <label for="expiration-time">유지 기간:</label>
        <select id="expiration-time" v-model.number="expirationMinutes">
          <option :value="5">5분</option>
          <option :value="60">1시간</option>
          <option :value="1440">1일</option>
          <option :value="4320">3일</option>
          <option :value="10080">7일</option>
          <option :value="21600">15일</option>
          <option :value="-1">무제한</option>
        </select>
      </div>
      
      <div class="selected-files-container">
        <div v-for="(file, index) in selectedFiles" :key="index" class="file-item">
          <div class="file-item-info">
            <span class="file-name">{{ file.name }}</span>
            <span class="file-size">({{ formatFileSize(file.size) }})</span>
          </div>
          <div v-if="fileProgress[index] > 0" class="progress-container">
            <div class="progress" :style="{ width: fileProgress[index] + '%' }"></div>
            <span class="progress-text">{{ fileProgress[index] }}%</span>
          </div>
          <button 
            @click="removeFile(index)" 
            class="remove-button"
            :disabled="uploadInProgress"
          >×</button>
        </div>
      </div>
      
      <div class="upload-actions">
        <button 
          @click="uploadFiles" 
          class="upload-button"
          :disabled="uploadInProgress"
        >
          {{ uploadInProgress ? '업로드 중...' : '업로드' }}
        </button>
        <button 
          @click="clearFiles" 
          class="clear-button"
          :disabled="uploadInProgress"
        >
          모두 지우기
        </button>
      </div>
      
      <div v-if="uploadedCount > 0" class="upload-summary">
        {{ uploadedCount }}/{{ totalFilesToUpload }} 파일 업로드 완료
      </div>
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
      selectedFiles: [],
      fileProgress: {},
      expirationMinutes: 5,
      isDragging: false,
      uploadInProgress: false,
      uploadedCount: 0,
      totalFilesToUpload: 0,
      uploadErrors: []
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
      const newFiles = Array.from(event.target.files || []);
      this.addFiles(newFiles);
    },
    onDrop(event) {
      this.isDragging = false;
      if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
        const newFiles = Array.from(event.dataTransfer.files);
        this.addFiles(newFiles);
      }
    },
    addFiles(newFiles) {
      // 이미 있는 파일 이름 목록 (중복 체크용)
      const existingFileNames = this.selectedFiles.map(f => f.name);
      
      // 중복이 아닌 파일만 추가
      newFiles.forEach(file => {
        if (!existingFileNames.includes(file.name)) {
          this.selectedFiles.push(file);
          this.fileProgress[this.selectedFiles.length - 1] = 0;
        }
      });
    },
    removeFile(index) {
      this.selectedFiles.splice(index, 1);
      // 진행 상태 배열도 업데이트
      const newProgress = {};
      this.selectedFiles.forEach((_, idx) => {
        newProgress[idx] = this.fileProgress[idx] || 0;
      });
      this.fileProgress = newProgress;
    },
    clearFiles() {
      this.selectedFiles = [];
      this.fileProgress = {};
      this.uploadedCount = 0;
      this.uploadErrors = [];
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
    formatFileSize(bytes) {
      if (typeof bytes !== 'number' || isNaN(bytes)) return '0 B';
      if (bytes < 1024) return bytes + ' B';
      else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
      else return (bytes / 1048576).toFixed(1) + ' MB';
    },
    async uploadFiles() {
      if (this.selectedFiles.length === 0 || this.uploadInProgress) return;
      
      this.uploadInProgress = true;
      this.uploadedCount = 0;
      this.totalFilesToUpload = this.selectedFiles.length;
      this.uploadErrors = [];
      
      // 동시 업로드 수 제한 (최대 3개 동시 업로드)
      const maxConcurrent = 3;
      const queue = [...this.selectedFiles];
      const activeUploads = new Set();
      
      const processQueue = async () => {
        // 큐가 비었고 진행중인 업로드가 없으면 완료
        if (queue.length === 0 && activeUploads.size === 0) {
          this.uploadInProgress = false;
          
          // 업로드가 완료되면 파일 목록 페이지로 이동
          if (this.uploadedCount > 0) {
            setTimeout(() => {
              this.$router.push({
                path: '/files/',
                query: { 
                  upload_complete: 'true',
                  count: this.uploadedCount
                }
              });
              this.$emit('upload-complete');
            }, 500);
          }
          return;
        }
        
        // 큐에 파일이 있고, 동시 업로드 수에 여유가 있으면 업로드 시작
        while (queue.length > 0 && activeUploads.size < maxConcurrent) {
          const fileIndex = this.selectedFiles.indexOf(queue[0]);
          const file = queue.shift();
          
          if (fileIndex === -1) continue; // 파일이 이미 제거됨
          
          activeUploads.add(fileIndex);
          this.uploadFile(file, fileIndex).finally(() => {
            activeUploads.delete(fileIndex);
            // 큐 계속 처리
            processQueue();
          });
        }
      };
      
      // 큐 처리 시작
      processQueue();
    },
    async uploadFile(file, index) {
      try {
        console.log(`파일 "${file.name}" 업로드 시작`);
        
        const formData = new FormData();
        formData.append('file', file);
        // 명시적으로 숫자 변환 후 추가
        const minutes = parseInt(this.expirationMinutes, 10);
        formData.append('expire_in_minutes', minutes);
        
        // 업로드 요청 전송 시 URL 파라미터로도 추가
        const url = `/upload/?expire_in_minutes=${minutes}`;
        const response = await axios.post(url, formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          },
          onUploadProgress: progressEvent => {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            this.fileProgress[index] = percentCompleted;
          }
        });
        
        if (response.data && response.data.success) {
          console.log(`파일 "${file.name}" 업로드 성공`);
          this.uploadedCount++;
        } else {
          throw new Error(`업로드 실패: ${response.data?.message || '알 수 없는 오류'}`);
        }
      } catch (error) {
        console.error(`파일 "${file.name}" 업로드 실패:`, error);
        this.uploadErrors.push({
          file: file.name,
          error: error.message || '알 수 없는 오류'
        });
        // 실패해도 업로드 시도 횟수는 증가
        this.uploadedCount++;
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

h2, h3 {
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

.upload-button:hover:not(:disabled) {
  background-color: #388e3c;
}

.upload-button:disabled {
  background-color: #a5d6a7;
  cursor: not-allowed;
}

.clear-button {
  background-color: #f44336;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
  margin: 10px 0 10px 10px;
  transition: background-color 0.3s;
}

.clear-button:hover:not(:disabled) {
  background-color: #d32f2f;
}

.clear-button:disabled {
  background-color: #ef9a9a;
  cursor: not-allowed;
}

.files-list {
  background-color: #f5f5f5;
  padding: 15px;
  border-radius: 5px;
  margin-bottom: 20px;
}

.selected-files-container {
  max-height: 300px;
  overflow-y: auto;
  margin: 15px 0;
  border: 1px solid #ddd;
  border-radius: 4px;
  background-color: white;
}

.file-item {
  padding: 10px 15px;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
}

.file-item:last-child {
  border-bottom: none;
}

.file-item-info {
  flex: 1;
  overflow: hidden;
  margin-right: 10px;
}

.file-name {
  font-weight: bold;
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
  display: block;
}

.file-size {
  color: #666;
  font-size: 0.9em;
}

.progress-container {
  height: 10px;
  background-color: #e0e0e0;
  border-radius: 5px;
  overflow: hidden;
  margin-top: 5px;
  flex: 1;
  position: relative;
  margin-right: 10px;
}

.progress {
  height: 100%;
  background-color: #4caf50;
  transition: width 0.3s;
}

.progress-text {
  position: absolute;
  right: 5px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 10px;
  color: #333;
}

.remove-button {
  background-color: #f44336;
  color: white;
  border: none;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  line-height: 24px;
  text-align: center;
  cursor: pointer;
  font-size: 16px;
  transition: background-color 0.3s;
  flex-shrink: 0;
}

.remove-button:hover:not(:disabled) {
  background-color: #d32f2f;
}

.remove-button:disabled {
  background-color: #e57373;
  cursor: not-allowed;
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

.upload-actions {
  display: flex;
  justify-content: center;
  margin-top: 15px;
}

.upload-summary {
  text-align: center;
  margin-top: 15px;
  font-weight: bold;
  color: #4caf50;
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