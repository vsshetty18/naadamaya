import { useCallback, useEffect, useRef, useState } from 'react'
import { clamp } from '@/utils/formatters'

/**
 * Frontend recording state for the Record modal.
 *
 * Status flow:
 *   idle -> requesting -> recording -> recorded
 *                    \-> error
 *
 * Two modes, same API:
 *  - REAL:      uses the microphone and MediaRecorder, so the result is a
 *               playable Blob.
 *  - SIMULATED: used when the mic is unavailable (for example a non-HTTPS
 *               page) or when start({ simulate: true }) is called. The
 *               timer and level meter run, but there is no audio data.
 *
 * This hook only captures audio. It does no analysis of any kind.
 */

const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
]

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return ''
  return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported?.(t)) || ''
}

function extensionFor(mime = '') {
  if (mime.includes('mp4')) return 'm4a'
  if (mime.includes('ogg')) return 'ogg'
  return 'webm'
}

export function isRecordingSupported() {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'
  )
}

export default function useRecorder({ maxDuration = 600, fileLabel = 'recording' } = {}) {
  const [status, setStatus] = useState('idle')
  const [elapsed, setElapsed] = useState(0)
  const [level, setLevel] = useState(0) // 0 to 1, drives the live meter
  const [error, setError] = useState(null)
  const [audio, setAudio] = useState(null)

  const statusRef = useRef('idle')
  const streamRef = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])
  const ctxRef = useRef(null)
  const analyserRef = useRef(null)
  const tickRef = useRef(null)
  const startedAtRef = useRef(0)
  const elapsedRef = useRef(0)
  const simulatedRef = useRef(false)
  const tokenRef = useRef(0) // invalidates an in-flight mic permission request
  const urlRef = useRef(null)
  const stopRef = useRef(() => {})

  const updateStatus = useCallback((next) => {
    statusRef.current = next
    setStatus(next)
  }, [])

  const revokeUrl = useCallback(() => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
  }, [])

  /** Stops the timer, the mic tracks and the audio context. */
  const releaseCapture = useCallback(() => {
    if (tickRef.current) {
      clearInterval(tickRef.current)
      tickRef.current = null
    }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (ctxRef.current && ctxRef.current.state !== 'closed') {
      ctxRef.current.close().catch(() => {})
    }
    ctxRef.current = null
    analyserRef.current = null
    setLevel(0)
  }, [])

  const beginTick = useCallback(() => {
    startedAtRef.current = performance.now()
    elapsedRef.current = 0
    setElapsed(0)

    const buffer = new Uint8Array(1024)

    tickRef.current = setInterval(() => {
      const t = (performance.now() - startedAtRef.current) / 1000
      elapsedRef.current = t
      setElapsed(t)

      if (analyserRef.current) {
        analyserRef.current.getByteTimeDomainData(buffer)
        let sum = 0
        for (let i = 0; i < buffer.length; i++) {
          const v = (buffer[i] - 128) / 128
          sum += v * v
        }
        setLevel(clamp(Math.sqrt(sum / buffer.length) * 4, 0, 1))
      } else {
        // Simulated meter: a gentle, natural-looking pulse.
        setLevel(clamp(0.25 + Math.abs(Math.sin(t * 3)) * 0.5 * Math.random() + 0.1, 0, 1))
      }

      if (t >= maxDuration) stopRef.current()
    }, 100)
  }, [maxDuration])

  const finalize = useCallback(
    ({ blob = null, mimeType = '', duration, simulated }) => {
      revokeUrl()
      const url = blob ? URL.createObjectURL(blob) : null
      urlRef.current = url
      setAudio({
        blob,
        url,
        duration,
        mimeType,
        size: blob ? blob.size : 0,
        simulated,
        name: `${fileLabel}.${blob ? extensionFor(mimeType) : 'demo'}`,
      })
      updateStatus('recorded')
    },
    [fileLabel, revokeUrl, updateStatus]
  )

  const stop = useCallback(() => {
    if (statusRef.current !== 'recording') return

    const duration = elapsedRef.current

    if (simulatedRef.current) {
      releaseCapture()
      finalize({ duration, simulated: true })
      return
    }

    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') return

    // Stop the clock now; the blob is assembled in recorder.onstop.
    if (tickRef.current) {
      clearInterval(tickRef.current)
      tickRef.current = null
    }
    recorder.onstop = () => {
      const mimeType = recorder.mimeType || pickMimeType()
      const blob = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' })
      chunksRef.current = []
      recorderRef.current = null
      releaseCapture()
      finalize({ blob, mimeType, duration, simulated: false })
    }
    recorder.stop()
  }, [finalize, releaseCapture])

  stopRef.current = stop

  const start = useCallback(
    async ({ simulate = false } = {}) => {
      if (statusRef.current === 'recording' || statusRef.current === 'requesting') return

      revokeUrl()
      setAudio(null)
      setError(null)
      setElapsed(0)
      const token = ++tokenRef.current

      // Simulated path (no mic, or explicitly requested).
      if (simulate || !isRecordingSupported()) {
        simulatedRef.current = true
        updateStatus('recording')
        beginTick()
        return
      }

      simulatedRef.current = false
      updateStatus('requesting')

      try {
        // Processing is switched off because singing needs an untouched signal
        // (echo cancellation and auto-gain distort pitch and dynamics).
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
          },
        })

        // The user cancelled or left while the permission prompt was open.
        if (token !== tokenRef.current) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }

        streamRef.current = stream

        const AudioCtx = window.AudioContext || window.webkitAudioContext
        if (AudioCtx) {
          const ctx = new AudioCtx()
          const analyser = ctx.createAnalyser()
          analyser.fftSize = 1024
          ctx.createMediaStreamSource(stream).connect(analyser)
          ctxRef.current = ctx
          analyserRef.current = analyser
        }

        const mimeType = pickMimeType()
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
        chunksRef.current = []
        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) chunksRef.current.push(e.data)
        }
        recorderRef.current = recorder
        recorder.start(250)

        updateStatus('recording')
        beginTick()
      } catch (err) {
        if (token !== tokenRef.current) return
        releaseCapture()
        if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
          setError('permission_denied')
        } else if (err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError') {
          setError('no_microphone')
        } else {
          setError('record_failed')
        }
        updateStatus('error')
      }
    },
    [beginTick, releaseCapture, revokeUrl, updateStatus]
  )

  /** Throws the take away and returns to idle (used by Re-record and Close). */
  const reset = useCallback(() => {
    tokenRef.current += 1 // cancels any pending permission request
    if (recorderRef.current) {
      recorderRef.current.onstop = null
      if (recorderRef.current.state !== 'inactive') recorderRef.current.stop()
      recorderRef.current = null
    }
    chunksRef.current = []
    releaseCapture()
    revokeUrl()
    simulatedRef.current = false
    elapsedRef.current = 0
    setElapsed(0)
    setAudio(null)
    setError(null)
    updateStatus('idle')
  }, [releaseCapture, revokeUrl, updateStatus])

  // Never leave the microphone open if the modal unmounts mid-recording.
  useEffect(() => {
    return () => {
      tokenRef.current += 1
      if (recorderRef.current) {
        recorderRef.current.onstop = null
        if (recorderRef.current.state !== 'inactive') recorderRef.current.stop()
      }
      releaseCapture()
    }
  }, [releaseCapture])

  return {
    status, // 'idle' | 'requesting' | 'recording' | 'recorded' | 'error'
    elapsed, // seconds, updates every 100ms
    remaining: Math.max(0, maxDuration - elapsed),
    level, // 0 to 1
    error, // null | 'permission_denied' | 'no_microphone' | 'record_failed'
    audio, // { blob, url, duration, mimeType, size, simulated, name } once recorded
    isRecording: status === 'recording',
    isSupported: isRecordingSupported(),
    start,
    stop,
    reset,
  }
}
