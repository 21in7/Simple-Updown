export function formatFileSize(bytes) {
  if (typeof bytes !== 'number' || isNaN(bytes)) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

export function getFileIcon(filename) {
  if (!filename) return '📁'
  const lower = filename.toLowerCase()
  if (['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'].some(ext => lower.endsWith(ext))) return '🖼️'
  if (['.mp4', '.avi', '.mov', '.mkv'].some(ext => lower.endsWith(ext))) return '🎬'
  if (['.mp3', '.wav', '.flac', '.aac'].some(ext => lower.endsWith(ext))) return '🎵'
  if (lower.endsWith('.pdf')) return '📄'
  if (['.zip', '.rar', '.7z', '.tar', '.gz'].some(ext => lower.endsWith(ext))) return '📦'
  if (['.xls', '.xlsx'].some(ext => lower.endsWith(ext))) return '📊'
  if (['.ppt', '.pptx'].some(ext => lower.endsWith(ext))) return '📋'
  if (['.doc', '.docx'].some(ext => lower.endsWith(ext))) return '📝'
  return '📁'
}

export function isImageFile(filename) {
  if (!filename) return false
  const imageExts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
  return imageExts.some(ext => filename.toLowerCase().endsWith(ext))
}
