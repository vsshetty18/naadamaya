/**
 * NAADAMAYA library API: profile, songs, recordings.
 *
 *   const profile = await getProfile()
 *   await updateProfile({ display_name: 'V S Vighnesh' })
 *   const song = await uploadReferenceSong(file, { title: 'Mungaru Maleye' })
 *   const rec = await uploadRecording(fileOrBlob, song.id, { source: 'browser_recording' })
 *
 * Uploads accept either a File (from the Upload modal) or a Blob (from the
 * Record modal). Server errors arrive as ApiError (see apiClient).
 *
 * Audio and photos live behind the access token on local storage, so
 * fetchAudioUrl() downloads them as a Blob and returns an object URL an
 * <audio> or <img> tag can use. Signed links (S3/R2) are used directly.
 * Call URL.revokeObjectURL(url) when you are done with an object URL.
 */

import api from '@/services/apiClient'

/* ---------------- profile ---------------- */
export const getProfile = () => api.get('/profile')

/** Partial update: only the fields you pass change. Pass null to clear one. */
export const updateProfile = (fields) => api.put('/profile', fields)

export function uploadProfilePhoto(file) {
  const form = new FormData()
  form.append('file', file, file.name || 'photo.jpg')
  return api.upload('/profile/photo', form)
}

/* ---------------- songs ---------------- */
const SONG_FIELDS = ['title', 'artist', 'movie', 'language', 'genre', 'lyricist', 'composer', 'lyrics']

export function uploadReferenceSong(file, details = {}) {
  const form = new FormData()
  form.append('file', file, file.name || 'original.webm')
  SONG_FIELDS.forEach((key) => {
    const value = details[key]
    if (value !== undefined && value !== null && String(value).trim() !== '') form.append(key, value)
  })
  return api.upload('/songs/reference', form)
}

export const listSongs = (params = {}) => api.get(`/songs${api.qs(params)}`)
export const getSong = (id) => api.get(`/songs/${id}`)
export const deleteSong = (id) => api.del(`/songs/${id}`)

/* ---------------- recordings ---------------- */
/** source: "upload" or "browser_recording" (feeds "Songs Recorded"). */
export function uploadRecording(file, songId, { source = 'upload' } = {}) {
  const form = new FormData()
  form.append('file', file, file.name || 'recording.webm')
  form.append('song_id', songId)
  form.append('source', source)
  return api.upload('/recordings', form)
}

export const listRecordings = (params = {}) => api.get(`/recordings${api.qs(params)}`)
export const getRecording = (id) => api.get(`/recordings/${id}`)
export const deleteRecording = (id) => api.del(`/recordings/${id}`)

/* ---------------- protected media ---------------- */
/**
 * Turns an audio_url or profile_photo_url from the API into something a media
 * tag can load. Relative paths (local storage) need the token, so they are
 * downloaded as a Blob. Absolute links (signed S3/R2 URLs) are used as is.
 * Returns null when there is no url.
 */
export async function fetchMediaUrl(url) {
  if (!url) return null
  if (/^https?:\/\//i.test(url)) return url
  const path = url.replace(/^\/api\/v1/, '')
  const blob = await api.blob(path)
  return URL.createObjectURL(blob)
}
