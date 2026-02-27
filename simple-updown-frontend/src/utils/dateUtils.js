const UNLIMITED_THRESHOLD_MS = 1000 * 60 * 60 * 24 * 365 * 90 // 90년

export function parseUTCDate(dateStr) {
  if (!dateStr) return null
  return new Date(dateStr.endsWith('Z') ? dateStr : dateStr + 'Z')
}

export function isUnlimited(expireTimeStr) {
  const expireTime = parseUTCDate(expireTimeStr)
  if (!expireTime) return true
  return expireTime - Date.now() > UNLIMITED_THRESHOLD_MS
}

export function isExpiringSoon(expireTimeStr, thresholdHours = 24) {
  if (isUnlimited(expireTimeStr)) return false
  const expireTime = parseUTCDate(expireTimeStr)
  if (!expireTime) return false
  const diffMs = expireTime - Date.now()
  return diffMs > 0 && diffMs < thresholdHours * 60 * 60 * 1000
}

export function getTimeLeft(expireTimeStr) {
  if (isUnlimited(expireTimeStr)) return '무제한'
  const expireTime = parseUTCDate(expireTimeStr)
  if (!expireTime) return '알 수 없음'
  const diffMs = expireTime - Date.now()
  if (diffMs <= 0) return '만료됨'
  const diffDays = Math.floor(diffMs / (24 * 60 * 60 * 1000))
  const diffHours = Math.floor((diffMs % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000))
  const diffMinutes = Math.floor((diffMs % (60 * 60 * 1000)) / (60 * 1000))
  if (diffDays > 0) return `${diffDays}일 ${diffHours}시간 남음`
  if (diffHours > 0) return `${diffHours}시간 ${diffMinutes}분 남음`
  return `${diffMinutes}분 남음`
}

export function formatDate(dateStr) {
  if (!dateStr) return ''
  try {
    const date = parseUTCDate(dateStr)
    if (!date || isNaN(date.getTime())) return '날짜 오류'
    return `${date.getFullYear()}.${(date.getMonth() + 1).toString().padStart(2, '0')}.${date.getDate().toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
  } catch {
    return '날짜 오류'
  }
}
