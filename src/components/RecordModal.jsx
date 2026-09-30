import { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Mic,
  MicOff,
  Pause,
  Play,
  RefreshCw,
  Square,
} from 'lucide-react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import ProgressBar from '@/components/ProgressBar'
import useAudioPlayer from '@/hooks/useAudioPlayer'
import useRecorder from '@/hooks/useRecorder'
import { cn } from '@/utils/cn'
import { formatFileSize, formatTime } from '@/utils/formatters'

/**
 * The recording interaction for one audio slot on Learn.
 *
 *   idle        big mic button, "Tap to start recording"
 *   requesting  waiting for the browser's microphone permission
 *   recording   live timer + level meter + Stop
 *   recorded    preview player + Re-record + Save recording
 *   error       a specific message + Try again / Use a demo recording
 *
 * Props:
 *   open, onClose
 *   title        slot name, e.g. "Your Voice" or "Original"
 *   onConfirm    called with the recording when the user taps "Save recording".
 *                Learn passes (audio) => setAudio('user', audio).
 *   maxDuration  seconds, default 600
 *
 * The modal only captures and previews audio. It does no analysis.
 */

const BAR_COUNT = 28

const ERROR_COPY = {
  permission_denied: {
    title: 'Microphone access was blocked',
    body: 'Allow microphone access in your browser settings, then try again. You can also continue with a demo recording.',
    canDemo: true,
  },
  no_microphone: {
    title: 'No microphone found',
    body: 'Connect a microphone and try again, or continue with a demo recording.',
    canDemo: true,
  },
  record_failed: {
    title: 'Recording could not start',
    body: 'Something went wrong while starting the recording. Please try again.',
    canDemo: true,
  },
}

/** Rolling bars that show the live input level. */
function LevelMeter({ history, active }) {
  const bars = Array.from({ length: BAR_COUNT }, (_, i) => {
    const v = history[i - (BAR_COUNT - history.length)]
    return typeof v === 'number' ? v : 0
  })

  return (
    <div className="flex h-16 items-center justify-center gap-[3px]" aria-hidden="true">
      {bars.map((v, i) => (
        <span
          key={i}
          className={cn(
            'w-[4px] rounded-full transition-[height] duration-100 ease-out',
            active ? 'bg-brown-400' : 'bg-brown-200'
          )}
          style={{ height: `${active ? 10 + v * 90 : 10}%` }}
        />
      ))}
    </div>
  )
}

/** Play/pause for the finished take. Works for real blobs and for demo takes. */
function TakePreview({ audio }) {
  const player = useAudioPlayer({ src: audio.url, duration: audio.duration || 0 })

  return (
    <div className="flex items-center gap-3 rounded-xl border border-gold-100 bg-ivory-50 px-3 py-2.5">
      <button
        type="button"
        onClick={player.toggle}
        disabled={Boolean(player.error)}
        aria-label={player.isPlaying ? 'Pause playback' : 'Play back your recording'}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blush-100 text-brown-500 transition-colors hover:bg-blush-200 disabled:opacity-50"
      >
        {player.isPlaying ? (
          <Pause className="h-4 w-4 fill-current" strokeWidth={2} aria-hidden="true" />
        ) : (
          <Play className="ml-0.5 h-4 w-4 fill-current" strokeWidth={2} aria-hidden="true" />
        )}
      </button>

      <div className="min-w-0 flex-1">
        <ProgressBar value={player.progress} tone="brand" size="sm" animate={false} label="Playback position" />
        <p className="mt-1.5 text-[0.74rem] leading-none text-brown-500">
          {player.error
            ? 'This browser cannot play this take back.'
            : `${formatTime(player.currentTime)} / ${formatTime(player.duration)}`}
        </p>
      </div>
    </div>
  )
}

export default function RecordModal({ open, onClose, title = 'Audio', onConfirm, maxDuration = 600 }) {
  const recorder = useRecorder({
    maxDuration,
    fileLabel: `${title.toLowerCase().replace(/\s+/g, '-')}-recording`,
  })
  const { status, elapsed, level, error, audio, isRecording, isSupported, start, stop, reset } = recorder

  const [history, setHistory] = useState([])

  // Feed the meter while recording, and clear it otherwise.
  useEffect(() => {
    if (status === 'recording') {
      setHistory((h) => [...h.slice(-(BAR_COUNT - 1)), level])
    } else {
      setHistory((h) => (h.length ? [] : h))
    }
  }, [level, status])

  // Start clean every time the modal closes. This also releases the microphone.
  useEffect(() => {
    if (!open) reset()
  }, [open, reset])

  const handleConfirm = () => {
    if (!audio) return
    onConfirm?.(audio) // the app copies what it needs before this modal resets
    onClose?.()
  }

  const errInfo = status === 'error' ? ERROR_COPY[error] || ERROR_COPY.record_failed : null
  const seconds = Math.floor(elapsed)

  /* ---------- footer ---------- */
  let footer
  if (status === 'idle') {
    footer = (
      <div className="flex gap-2.5">
        <Button variant="ghost" onClick={onClose} className="flex-1">
          Cancel
        </Button>
        <Button variant="primary" leftIcon={Mic} onClick={() => start()} className="flex-[1.4]">
          Start recording
        </Button>
      </div>
    )
  } else if (status === 'requesting') {
    footer = (
      <Button variant="ghost" onClick={onClose} fullWidth>
        Cancel
      </Button>
    )
  } else if (status === 'recording') {
    footer = (
      <Button variant="primary" leftIcon={Square} onClick={stop} fullWidth>
        Stop recording
      </Button>
    )
  } else if (status === 'recorded') {
    footer = (
      <div className="flex gap-2.5">
        <Button variant="secondary" leftIcon={RefreshCw} onClick={reset} className="flex-1">
          Re-record
        </Button>
        <Button variant="primary" leftIcon={CheckCircle2} onClick={handleConfirm} className="flex-[1.4]">
          Save recording
        </Button>
      </div>
    )
  } else {
    footer = (
      <div className="flex flex-col gap-2.5">
        <div className="flex gap-2.5">
          <Button variant="ghost" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button variant="primary" leftIcon={RefreshCw} onClick={() => start()} className="flex-[1.4]">
            Try again
          </Button>
        </div>
        {errInfo?.canDemo && (
          <Button variant="secondary" onClick={() => start({ simulate: true })} fullWidth>
            Continue with a demo recording
          </Button>
        )}
      </div>
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      icon={Mic}
      title={`Record ${title}`}
      subtitle="Sing or play into your microphone."
      dismissible={!isRecording} // a stray tap must not throw away a take
      footer={footer}
    >
      {/* IDLE */}
      {status === 'idle' && (
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <button
            type="button"
            onClick={() => start()}
            aria-label="Start recording"
            className="flex h-24 w-24 items-center justify-center rounded-full bg-cta-brown text-ivory-50 shadow-cta transition-transform duration-200 hover:scale-105 active:scale-95"
          >
            <Mic className="h-10 w-10" strokeWidth={1.8} aria-hidden="true" />
          </button>
          <div>
            <p className="font-serif text-[1.2rem] font-semibold text-brown-900">Tap to start recording</p>
            <p className="mt-1 text-[0.82rem] leading-snug text-brown-500">
              Find a quiet spot and keep the microphone at a steady distance.
              <br />
              Recordings can be up to {formatTime(maxDuration)} long.
            </p>
          </div>
          {!isSupported && (
            <p className="max-w-xs rounded-xl border border-gold-200 bg-gold-50 px-3 py-2 text-[0.78rem] leading-snug text-brown-600">
              Microphone recording is not available here, so a demo recording will be used. Open the app over
              HTTPS to record for real.
            </p>
          )}
        </div>
      )}

      {/* REQUESTING */}
      {status === 'requesting' && (
        <div className="flex flex-col items-center gap-3 py-10 text-center" role="status">
          <Loader2 className="h-8 w-8 animate-spin text-brown-400" strokeWidth={1.8} aria-hidden="true" />
          <p className="font-serif text-[1.15rem] text-brown-700">Waiting for microphone access...</p>
          <p className="max-w-xs text-[0.82rem] leading-snug text-brown-500">
            Choose Allow when your browser asks to use the microphone.
          </p>
        </div>
      )}

      {/* RECORDING */}
      {status === 'recording' && (
        <div className="flex flex-col items-center gap-3 py-5 text-center" role="status">
          <span className="flex items-center gap-2 text-[0.8rem] font-medium uppercase tracking-[0.16em] text-status-bad">
            <span className="h-2 w-2 animate-pulse-soft rounded-full bg-status-bad" aria-hidden="true" />
            Recording
          </span>

          <span className="font-serif text-[3.25rem] font-semibold leading-none tabular-nums text-brown-900">
            {formatTime(seconds)}
          </span>

          <div className="w-full max-w-xs">
            <LevelMeter history={history} active />
          </div>

          <span className="flex h-16 w-16 items-center justify-center rounded-full bg-blush-100 text-status-bad animate-record-pulse">
            <Mic className="h-7 w-7" strokeWidth={1.8} aria-hidden="true" />
          </span>

          <p className="text-[0.78rem] text-brown-500">Tap Stop when you have finished.</p>
        </div>
      )}

      {/* RECORDED */}
      {status === 'recorded' && audio && (
        <div className="animate-fade-in py-2">
          <div className="flex items-center gap-3 rounded-card border border-gold-100 bg-card-warm p-3.5 shadow-soft">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-sage-100 text-sage-500">
              <CheckCircle2 className="h-6 w-6" strokeWidth={2} aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.95rem] font-medium leading-tight text-brown-900" title={audio.name}>
                {audio.name}
              </p>
              <p className="mt-1 text-[0.78rem] leading-none text-brown-500">
                {[
                  formatTime(Math.round(audio.duration)),
                  audio.size > 0 ? formatFileSize(audio.size) : null,
                  audio.simulated ? 'Demo recording' : 'Recorded',
                ]
                  .filter(Boolean)
                  .join(' \u00B7 ')}
              </p>
            </div>
          </div>

          <div className="mt-3">
            <TakePreview audio={audio} />
          </div>

          {audio.simulated && (
            <p className="mt-3 text-[0.78rem] leading-snug text-brown-500">
              This is a demo take with no real audio. It lets you try the full flow without a microphone.
            </p>
          )}
        </div>
      )}

      {/* ERROR */}
      {status === 'error' && errInfo && (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-full bg-blush-100 text-status-bad">
            {error === 'record_failed' ? (
              <AlertCircle className="h-7 w-7" strokeWidth={1.8} aria-hidden="true" />
            ) : (
              <MicOff className="h-7 w-7" strokeWidth={1.8} aria-hidden="true" />
            )}
          </span>
          <div role="alert">
            <p className="font-serif text-[1.2rem] font-semibold text-brown-900">{errInfo.title}</p>
            <p className="mx-auto mt-1 max-w-xs text-[0.85rem] leading-snug text-brown-600">{errInfo.body}</p>
          </div>
        </div>
      )}
    </Modal>
  )
}
