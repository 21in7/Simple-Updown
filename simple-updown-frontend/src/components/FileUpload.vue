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
      <button @click="fileInput.click()" class="upload-button">
        파일 선택
      </button>
      <p>또는 파일을 여기에 드래그 앤 드롭하세요 (여러 파일 가능)</p>
    </div>
    
    <div v-if="selectedFiles.length > 0" class="files-list">
      <h3>선택된 파일 ({{ selectedFiles.length }}개)</h3>
      
      <div class="expiration-selector">
        <label for="expiration-time">유지 기간:</label>
        <select id="expiration-time" v-model="expirationMinutes">
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

      <div v-if="uploadErrors.length > 0" class="upload-errors">
        <p v-for="err in uploadErrors" :key="err.file" class="error-item">
          ⚠️ {{ err.file }}: {{ err.error }}
        </p>
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

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { uploadFile as apiUploadFile } from '@/api/filesApi'
import { formatFileSize } from '@/utils/fileUtils'

const emit = defineEmits(['upload-complete'])
const router = useRouter()

const fileInput = ref(null)
const selectedFiles = ref([])
const fileProgress = ref({})
const expirationMinutes = ref(5)
const isDragging = ref(false)
const uploadInProgress = ref(false)
const uploadedCount = ref(0)
const totalFilesToUpload = ref(0)
const uploadErrors = ref([])

function onFileSelected(event) {
  addFiles(Array.from(event.target.files || []))
}

function onDrop(event) {
  isDragging.value = false
  if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
    addFiles(Array.from(event.dataTransfer.files))
  }
}

function addFiles(newFiles) {
  const existingNames = selectedFiles.value.map(f => f.name)
  newFiles.forEach(file => {
    if (!existingNames.includes(file.name)) {
      selectedFiles.value.push(file)
      fileProgress.value[selectedFiles.value.length - 1] = 0
    }
  })
}

function removeFile(index) {
  selectedFiles.value.splice(index, 1)
  const newProgress = {}
  selectedFiles.value.forEach((_, idx) => {
    newProgress[idx] = fileProgress.value[idx] || 0
  })
  fileProgress.value = newProgress
}

function clearFiles() {
  selectedFiles.value = []
  fileProgress.value = {}
  uploadedCount.value = 0
  uploadErrors.value = []
}

function handleDragEnter(event) {
  event.preventDefault()
  isDragging.value = true
}

function handleDragLeave(event) {
  event.preventDefault()
  if (!event.relatedTarget || event.relatedTarget.nodeName === 'HTML') {
    isDragging.value = false
  }
}

async function uploadSingleFile(file, index) {
  try {
    const data = await apiUploadFile(file, expirationMinutes.value, progressEvent => {
      const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total)
      fileProgress.value[index] = percentCompleted
    })
    if (data && data.success) {
      uploadedCount.value++
    } else {
      throw new Error(`업로드 실패: ${data?.message || '알 수 없는 오류'}`)
    }
  } catch (error) {
    uploadErrors.value.push({ file: file.name, error: error.message || '알 수 없는 오류' })
  }
}

async function uploadFiles() {
  if (selectedFiles.value.length === 0 || uploadInProgress.value) return
  uploadInProgress.value = true
  uploadedCount.value = 0
  totalFilesToUpload.value = selectedFiles.value.length
  uploadErrors.value = []

  const maxConcurrent = 3
  const queue = [...selectedFiles.value]
  const activeUploads = new Set()

  const processQueue = async () => {
    if (queue.length === 0 && activeUploads.size === 0) {
      uploadInProgress.value = false
      if (uploadedCount.value > 0) {
        setTimeout(() => {
          router.push({ path: '/files/', query: { upload_complete: 'true', count: uploadedCount.value } })
          emit('upload-complete')
        }, 500)
      }
      return
    }
    while (queue.length > 0 && activeUploads.size < maxConcurrent) {
      const fileIndex = selectedFiles.value.indexOf(queue[0])
      const file = queue.shift()
      if (fileIndex === -1) continue
      activeUploads.add(fileIndex)
      uploadSingleFile(file, fileIndex).finally(() => {
        activeUploads.delete(fileIndex)
        processQueue()
      })
    }
  }

  processQueue()
}

onMounted(() => {
  window.addEventListener('dragenter', handleDragEnter)
  window.addEventListener('dragleave', handleDragLeave)
})

onBeforeUnmount(() => {
  window.removeEventListener('dragenter', handleDragEnter)
  window.removeEventListener('dragleave', handleDragLeave)
})
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

.upload-errors {
  margin-top: 10px;
  padding: 10px;
  background-color: #fff3f3;
  border: 1px solid #f44336;
  border-radius: 4px;
}

.error-item {
  color: #f44336;
  font-size: 0.9em;
  margin: 4px 0;
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