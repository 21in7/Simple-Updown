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
export default {
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
    uploadFile() {
      if (!this.selectedFile) return;
      
      const formData = new FormData();
      formData.append('file', this.selectedFile);
      
      // API 엔드포인트로 파일 업로드
      // 실제 구현시 axios 등을 사용하여 구현
      console.log('파일 업로드 시작:', this.selectedFile.name);
      
      // 업로드 진행 상황 시뮬레이션
      let progress = 0;
      const interval = setInterval(() => {
        progress += 10;
        this.uploadProgress = progress;
        
        if (progress >= 100) {
          clearInterval(interval);
          console.log('업로드 완료!');
        }
      }, 300);
    }
  }
}
</script>

<style scoped>
.upload-container {
  max-width: 500px;
  margin: 0 auto;
  padding: 20px;
}

.upload-area {
  border: 2px dashed #ccc;
  padding: 30px;
  text-align: center;
  margin: 20px 0;
  border-radius: 5px;
}

.upload-button {
  background-color: #4CAF50;
  color: white;
  padding: 10px 15px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  margin: 10px 0;
}

.progress-bar {
  width: 100%;
  background-color: #f0f0f0;
  border-radius: 5px;
  margin: 15px 0;
  position: relative;
  height: 20px;
}

.progress {
  background-color: #4CAF50;
  height: 100%;
  border-radius: 5px;
  transition: width 0.2s;
}

.progress-bar span {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  color: #333;
  font-size: 12px;
}

.file-info {
  margin: 15px 0;
  padding: 10px;
  background-color: #f8f8f8;
  border-radius: 5px;
}
</style>
