import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Frontend state for the Upload modal.
 *
 * Status flow:
 *   idle -> validating -> uploading -> uploaded
 *                    \-> error
 *
 * What it does:
 *  - checks the format and size of the chosen file
 *  - reads the real duration from the file
 *  - shows a SIMULATED upload progress bar (nothing is sent anywhere)
 *  - returns a playable object URL, so useAudioPlayer can preview it
 *
 * What it does NOT do: any analysis. It only prepares a file for
 * analyzeSong() to receive later.
 */

export const ACCEPTED_EXTENSIONS = ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac', 'webm', 'mp4']
export const ACCEPT_ATTR = ['audio/*', ...ACCEPTED_EXTENSIONS.map((e) => `.${e}`)].join(',')
export const MAX_FILE_SIZE_MB = 50

const MAX_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
const METADATA_TIMEOUT_MS = 8000

function getExtension(name = '') {
  const match = /\.([^.]+)$/.exec(name)
  return match ? match[1].toLowerCase() : ''
}

function isSupportedFormat(file) {
  const ext = getExtension(file.name)
  const typeOk = typeof file.type === 'string' && file.type.startsWith('audio/')
  // Some phones report an empty type, so the extension is accepted too.
  // A .mp4 is only accepted when the browser calls it audio.
  if (ext === 'mp4') return typeOk
  return typeOk || ACCEPTED_EXTENSIONS.includes(ext)
}

/**
 * Reads the duration in seconds.
 * Resolves with a number, null (playable but length unknown), or rejects
 * when the browser cannot decode the file at all.
 */
function readDuration(url) {
  return new Promise((resolve, reject) => {
    const probe = new Audio()
    probe.preload = 'metadata'

    let settled = false
    const done = (fn, value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      probe.removeAttribute('src')
      probe.load()
      fn(value)
    }

    const timer = setTimeout(() => done(reject, new Error('timeout')), METADATA_TIMEOUT_MS)

    probe.onloadedmetadata = () => {
      const d = probe.duration
      // Some formats (streamed webm) report Infinity. Treat the length as unknown.
      done(resolve, Number.isFinite(d) && d > 0 ? d : null)
    }
    probe.onerror = () => done(reject, new Error('decode'))
    probe.src = url
  })
}

export default function useAudioUpload() {
  const [status, setStatus] = useState('idle')
  const [progress, setProgress] = useState(0) // 0 to 100
  const [error, setError] = useState(null)
  const [audio, setAudio] = useState(null)

  const tokenRef = useRef(0) // invalidates an in-flight selection
  const timerRef = useRef(null)
  const urlRef = useRef(null)

  const stopProgress = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const revokeUrl = useCallback(() => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
  }, [])

  const fail = useCallback(
    (code) => {
      stopProgress()
      revokeUrl()
      setAudio(null)
      setProgress(0)
      setError(code)
      setStatus('error')
    },
    [stopProgress, revokeUrl]
  )

  /** Runs the simulated progress bar, then marks the upload complete. */
  const simulateUpload = useCallback(
    (token, nextAudio) => {
      stopProgress()
      setStatus('uploading')
      setProgress(0)

      // Larger files take a little longer, capped so the demo never drags.
      const totalMs = Math.min(3000, 1100 + (nextAudio.size / (1024 * 1024)) * 90)
      const startedAt = performance.now()

      timerRef.current = setInterval(() => {
        if (token !== tokenRef.current) {
          stopProgress()
          return
        }
        const t = Math.min(1, (performance.now() - startedAt) / totalMs)
        // Ease-out so it feels like a real transfer that slows near the end.
        const eased = 1 - Math.pow(1 - t, 2.2)
        setProgress(Math.round(eased * 100))

        if (t >= 1) {
          stopProgress()
          setAudio(nextAudio)
          setStatus('uploaded')
        }
      }, 80)
    },
    [stopProgress]
  )

  /** Called with a File from an <input type="file"> or a drag-and-drop. */
  const select = useCallback(
    async (file) => {
      const token = ++tokenRef.current
      stopProgress()
      revokeUrl()
      setAudio(null)
      setError(null)
      setProgress(0)

      if (!file) {
        fail('no_file')
        return
      }
      if (!isSupportedFormat(file)) {
        fail('unsupported_format')
        return
      }
      if (file.size === 0) {
        fail('empty_file')
        return
      }
      if (file.size > MAX_BYTES) {
        fail('file_too_large')
        return
      }

      setStatus('validating')
      const url = URL.createObjectURL(file)
      urlRef.current = url

      let duration
      try {
        duration = await readDuration(url)
      } catch {
        if (token !== tokenRef.current) return
        fail('unreadable_file')
        return
      }

      // The user removed the file or chose another one while we were reading.
      if (token !== tokenRef.current) {
        URL.revokeObjectURL(url)
        return
      }

      simulateUpload(token, {
        file,
        url,
        name: file.name,
        size: file.size,
        mimeType: file.type || `audio/${getExtension(file.name)}`,
        duration, // seconds, or null when the browser could not tell
        simulated: false,
      })
    },
    [fail, revokeUrl, simulateUpload, stopProgress]
  )

  /** Attaches a recording made in the Record modal, so both routes give the same shape. */
  const attach = useCallback(
    (recorded) => {
      tokenRef.current += 1
      stopProgress()
      revokeUrl()
      setError(null)
      setProgress(100)
      setAudio(recorded)
      setStatus('uploaded')
    },
    [revokeUrl, stopProgress]
  )

  /** Removes the file and returns to the empty state ("Remove / reselect"). */
  const remove = useCallback(() => {
    tokenRef.current += 1
    stopProgress()
    revokeUrl()
    setAudio(null)
    setError(null)
    setProgress(0)
    setStatus('idle')
  }, [revokeUrl, stopProgress])

  // Clean up on unmount so no timer or object URL is left behind.
  useEffect(() => {
    return () => {
      tokenRef.current += 1
      stopProgress()
      revokeUrl()
    }
  }, [stopProgress, revokeUrl])

  return {
    status, // 'idle' | 'validating' | 'uploading' | 'uploaded' | 'error'
    progress, // 0 to 100 (simulated)
    error, // null | 'no_file' | 'unsupported_format' | 'empty_file'
    //        | 'file_too_large' | 'unreadable_file'
    audio, // { file, url, name, size, mimeType, duration, simulated } once uploaded
    isBusy: status === 'validating' || status === 'uploading',
    accept: ACCEPT_ATTR,
    maxSizeMB: MAX_FILE_SIZE_MB,
    select,
    attach,
    remove,
    reset: remove,
  }
}
