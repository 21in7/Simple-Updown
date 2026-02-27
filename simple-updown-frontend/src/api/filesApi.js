import axios from 'axios'

const api = axios.create({
  timeout: 30000,
})

export async function fetchFiles() {
  const response = await api.get('/api/files/')
  return response.data
}

export async function uploadFile(file, expireMinutes, onProgress) {
  const minutes = parseInt(expireMinutes, 10)
  const formData = new FormData()
  formData.append('file', file)
  formData.append('expire_in_minutes', minutes)
  const response = await api.post(`/upload/?expire_in_minutes=${minutes}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress,
  })
  return response.data
}

export async function deleteFile(fileHash) {
  await api.delete(`/files/${fileHash}`)
}

export function getDownloadUrl(fileHash) {
  return `/download/${fileHash}`
}

export function getThumbnailUrl(fileHash) {
  return `/thumbnail/${fileHash}`
}
