import { useCallback, useEffect, useRef, useState } from 'react'
import { clamp } from '@/utils/formatters'

/**
 * Playback state for one audio track (Original or Your Voice).
 *
 * Two modes, same API:
 *  - REAL:      pass `src` (an object URL from an uploaded/recorded file)
 *               and a real <audio> element plays it.
 *  - SIMULATED: no `src` (mock songs have no audio file), so a timer
 *               advances the playhead across `duration`.
 *
 * The AudioPlayer component never needs to know which mode it is in.
 */

// Only one player at a time: starting one pauses the other.
let stopActivePlayer = null

export default function useAudioPlayer({ src = null, duration: durationProp = 0, onEnded } = {}) {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(Number(durationProp) || 0)
  const [error, setError] = useState(null)

  const audioRef = useRef(null)
  const timerRef = useRef(null)
  const lastTickRef = useRef(0)
  const currentRef = useRef(0)
  const durationRef = useRef(Number(durationProp) || 0)
  const onEndedRef = useRef(onEnded)
  const pauseRef = useRef(() => {})

  useEffect(() => {
    onEndedRef.current = onEnded
  }, [onEnded])

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const finish = useCallback(() => {
    stopTimer()
    currentRef.current = 0
    setCurrentTime(0)
    setIsPlaying(false)
    onEndedRef.current?.()
  }, [stopTimer])

  const startTimer = useCallback(() => {
    stopTimer()
    lastTickRef.current = performance.now()
    timerRef.current = setInterval(() => {
      const now = performance.now()
      const next = currentRef.current + (now - lastTickRef.current) / 1000
      lastTickRef.current = now

      if (next >= durationRef.current) {
        finish()
        return
      }
      currentRef.current = next
      setCurrentTime(next)
    }, 100)
  }, [stopTimer, finish])

  // Reset everything whenever the track changes (new file, or a different song).
  useEffect(() => {
    const dur = Number(durationProp) || 0
    durationRef.current = dur
    currentRef.current = 0
    setDuration(dur)
    setCurrentTime(0)
    setIsPlaying(false)
    setError(null)

    if (!src) {
      return () => stopTimer()
    }

    const audio = new Audio(src)
    audio.preload = 'metadata'
    audioRef.current = audio

    const onMeta = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        durationRef.current = audio.duration
        setDuration(audio.duration)
      }
    }
    const onTime = () => {
      currentRef.current = audio.currentTime
      setCurrentTime(audio.currentTime)
    }
    const onEnd = () => finish()
    const onErr = () => {
      setIsPlaying(false)
      setError('unsupported')
    }

    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('ended', onEnd)
    audio.addEventListener('error', onErr)

    return () => {
      audio.pause()
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('ended', onEnd)
      audio.removeEventListener('error', onErr)
      audioRef.current = null
      stopTimer()
    }
  }, [src, durationProp, stopTimer, finish])

  const pause = useCallback(() => {
    stopTimer()
    audioRef.current?.pause()
    setIsPlaying(false)
  }, [stopTimer])

  pauseRef.current = pause

  const play = useCallback(() => {
    const audio = audioRef.current
    if (!audio && durationRef.current <= 0) return

    // Pause whichever other player is running.
    if (stopActivePlayer && stopActivePlayer !== pauseRef.current) {
      stopActivePlayer()
    }
    stopActivePlayer = pauseRef.current

    if (audio) {
      audio
        .play()
        .then(() => setIsPlaying(true))
        .catch(() => {
          setError('playback_failed')
          setIsPlaying(false)
        })
    } else {
      startTimer()
      setIsPlaying(true)
    }
  }, [startTimer])

  const toggle = useCallback(() => {
    if (isPlaying) pause()
    else play()
  }, [isPlaying, play, pause])

  const seek = useCallback((seconds) => {
    const t = clamp(seconds, 0, durationRef.current)
    currentRef.current = t
    setCurrentTime(t)
    if (audioRef.current) audioRef.current.currentTime = t
    lastTickRef.current = performance.now()
  }, [])

  const reset = useCallback(() => {
    pause()
    seek(0)
  }, [pause, seek])

  // Release the "active player" slot and stop the timer on unmount.
  useEffect(() => {
    return () => {
      if (stopActivePlayer === pauseRef.current) stopActivePlayer = null
    }
  }, [])

  const progress = duration > 0 ? clamp((currentTime / duration) * 100) : 0

  return {
    isPlaying,
    currentTime,
    duration,
    progress, // 0 to 100, drives the waveform fill
    error, // null | 'unsupported' | 'playback_failed'
    isSimulated: !src,
    play,
    pause,
    toggle,
    seek,
    reset,
  }
}
