/**
 * Pure formatting helpers shared across Naadamaya.
 * No React, no analysis logic: they only turn raw values into display strings.
 */

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

/** Keeps a number inside [min, max]. */
export function clamp(value, min = 0, max = 100) {
  const n = Number(value)
  if (Number.isNaN(n)) return min
  return Math.min(max, Math.max(min, n))
}

/** 261 -> "04:21". Accepts seconds. Bad input -> "--:--". */
export function formatTime(totalSeconds) {
  const n = Number(totalSeconds)
  if (!Number.isFinite(n) || n < 0) return '--:--'

  const rounded = Math.round(n)
  const mins = Math.floor(rounded / 60)
  const secs = rounded % 60
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

/** (0, 261) -> "00:00 / 04:21". Used by the audio players. */
export function formatTimePair(current, total) {
  return `${formatTime(current)} / ${formatTime(total)}`
}

/** Accepts an ISO string, timestamp or Date. Returns "28 Sep 2026". */
export function formatDate(input) {
  if (!input) return ''
  const d = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

/** 72 -> "72/100". Missing scores render as an em dash. */
export function formatScore(score, outOf = 100) {
  if (score === null || score === undefined || Number.isNaN(Number(score))) {
    return '\u2014'
  }
  return `${Math.round(Number(score))}/${outOf}`
}

/** 12 -> "+12", -5 -> "-5", 0 -> "0". */
export function formatSigned(value, decimals = 0) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '\u2014'
  const fixed = n.toFixed(decimals)
  return n > 0 ? `+${fixed}` : fixed
}

/** Pitch deviation in cents: 12 -> "+12\u00A2". */
export function formatCents(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '\u2014'
  return `${formatSigned(n)}\u00A2`
}

/** Bytes -> "3.2 MB". */
export function formatFileSize(bytes) {
  const n = Number(bytes)
  if (!Number.isFinite(n) || n <= 0) return '0 KB'
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

/** pluralize(1, 'credit') -> "1 credit", pluralize(10, 'credit') -> "10 credits". */
export function pluralize(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`
}

/** Rupee price: 199 -> "\u20B9199", 0 -> "\u20B90". */
export function formatPrice(amount) {
  const n = Number(amount)
  if (!Number.isFinite(n)) return ''
  return `\u20B9${n.toLocaleString('en-IN')}`
}

/** "mungaru_maleye.mp3" -> "mungaru_maleye". */
export function stripExtension(filename = '') {
  return filename.replace(/\.[^/.]+$/, '')
}

/** "V S Vighnesh" -> "VS". Used for avatar fallbacks. */
export function getInitials(name = '') {
  return name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}
