import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  FileAudio,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  UploadCloud,
} from 'lucide-react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import ProgressBar from '@/components/ProgressBar'
import useAudioPlayer from '@/hooks/useAudioPlayer'
import useAudioUpload from '@/hooks/useAudioUpload'
import { cn } from '@/utils/cn'
import { formatFileSize, formatTime } from '@/utils/formatters'

/**
 * The upload interaction for one audio slot on Learn.
 *
 *   idle        drop zone (click to browse, or drag a file in)
 *   validating  "Checking your file..."
 *   uploading   file card + progress bar (simulated, nothing is sent)
 *   uploaded    file card + preview play button + Use this audio
 *   error       a specific message + Try again
 *
 * Props:
 *   open, onClose
 *   title        slot name, e.g. "Original" or "Your Voice"
 *   onConfirm    called with the audio object when the user taps "Use this audio".
 *                Learn passes (audio) => setAudio('original', audio).
 *
 * The modal only collects and previews a file. It does no analysis.
 */

const ERROR_COPY = {
  no_file: {
    title: 'No file selected',
    body: 'Choose an audio file to continue.',
  },
  unsupported_format: {
    title: 'This format is not supported',
    body: 'Please choose an audio file such as MP3, WAV, M4A, AAC, OGG or FLAC.',
  },
  empty_file: {
    title: 'This file is empty',
    body: 'The file has no audio in it. Please choose a different one.',
  },
  file_too_large: {
    title: 'This file is too large',
    body: (max) => `Please choose a file smaller than ${max} MB.`,
  },
  unreadable_file: {
    title: 'We could not read this audio',
    body: 'The file may be damaged or in an unusual encoding. Try another copy or export it as MP3.',
  },
}

function errorText(code, maxSizeMB) {
  const entry = ERROR_COPY[code] || ERROR_COPY.unreadable_file
  return {
    title: entry.title,
    body: typeof entry.body === 'function' ? entry.body(maxSizeMB) : entry.body,
  }
}

/** Small round play/pause for previewing the chosen file. */
function PreviewButton({ audio }) {
  const player = useAudioPlayer({ src: audio.url, duration: audio.duration || 0 })

  return (
    <div className="mt-3 flex items-center gap-3 rounded-xl border border-gold-100 bg-ivory-50 px-3 py-2.5">
      <button
        type="button"
        onClick={player.toggle}
        disabled={Boolean(player.error)}
        aria-label={player.isPlaying ? 'Pause preview' : 'Play preview'}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blush-100 text-brown-500 transition-colors hover:bg-blush-200 disabled:opacity-50"
      >
        {player.isPlaying ? (
          <Pause className="h-4 w-4 fill-current" strokeWidth={2} aria-hidden="true" />
        ) : (
          <Play className="ml-0.5 h-4 w-4 fill-current" strokeWidth={2} aria-hidden="true" />
        )}
      </button>

      <div className="min-w-0 flex-1">
        <ProgressBar value={player.progress} tone="brand" size="sm" animate={false} label="Preview position" />
        <p className="mt-1.5 text-[0.74rem] leading-none text-brown-500">
          {player.error
            ? 'This browser cannot play this file, but it can still be analysed.'
            : `${formatTime(player.currentTime)}${player.duration > 0 ? ` / ${formatTime(player.duration)}` : ''}`}
        </p>
      </div>
    </div>
  )
}

export default function UploadModal({ open, onClose, title = 'Audio', onConfirm }) {
  const upload = useAudioUpload()
  const { status, progress, error, audio, isBusy, accept, maxSizeMB, select, remove } = upload

  const inputRef = useRef(null)
  const [picked, setPicked] = useState(null) // name and size, shown while the file is still being checked
  const [dragging, setDragging] = useState(false)

  // Start clean every time the modal closes, so the next open is empty.
  useEffect(() => {
    if (!open) {
      remove()
      setPicked(null)
      setDragging(false)
    }
  }, [open, remove])

  const openPicker = () => inputRef.current?.click()

  const handleFiles = (files) => {
    const file = files && files[0]
    if (!file) return
    setPicked({ name: file.name, size: file.size })
    select(file)
  }

  const handleInputChange = (e) => {
    handleFiles(e.target.files)
    // Lets the same file be chosen again after Remove.
    e.target.value = ''
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    if (isBusy) return
    handleFiles(e.dataTransfer?.files)
  }

  const handleRemove = () => {
    remove()
    setPicked(null)
  }

  const handleConfirm = () => {
    if (!audio) return
    onConfirm?.(audio) // the app copies what it needs before this modal resets
    onClose?.()
  }

  const shown = audio || picked
  const errInfo = status === 'error' ? errorText(error, maxSizeMB) : null

  /* ---------- footer ---------- */
  let footer
  if (status === 'uploaded') {
    footer = (
      <div className="flex gap-2.5">
        <Button variant="secondary" leftIcon={RefreshCw} onClick={handleRemove} className="flex-1">
          Choose another
        </Button>
        <Button variant="primary" leftIcon={CheckCircle2} onClick={handleConfirm} className="flex-[1.4]">
          Use this audio
        </Button>
      </div>
    )
  } else {
    footer = (
      <div className="flex gap-2.5">
        <Button variant="ghost" onClick={onClose} className="flex-1">
          Cancel
        </Button>
        {status === 'error' && (
          <Button variant="primary" leftIcon={RefreshCw} onClick={openPicker} className="flex-[1.4]">
            Try again
          </Button>
        )}
      </div>
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      icon={UploadCloud}
      title={`Upload ${title}`}
      subtitle="Choose an audio file from your device."
      footer={footer}
    >
      {/* One hidden input serves every state */}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleInputChange}
        className="hidden"
        tabIndex={-1}
        aria-hidden="true"
      />

      {/* IDLE and ERROR: drop zone */}
      {(status === 'idle' || status === 'error') && (
        <>
          <button
            type="button"
            onClick={openPicker}
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={cn(
              'flex w-full flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed px-4 py-9 text-center',
              'transition-colors duration-200',
              dragging
                ? 'border-brown-400 bg-blush-50'
                : 'border-gold-200 bg-ivory-50 hover:border-brown-300 hover:bg-blush-50/60'
            )}
          >
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-mist-100 text-mist-500">
              <UploadCloud className="h-7 w-7" strokeWidth={1.8} aria-hidden="true" />
            </span>
            <span className="font-serif text-[1.2rem] font-semibold text-brown-900">
              {dragging ? 'Drop to upload' : 'Tap to choose a file'}
            </span>
            <span className="text-[0.82rem] leading-snug text-brown-500">
              or drag an audio file here
              <br />
              MP3, WAV, M4A, AAC, OGG or FLAC, up to {maxSizeMB} MB
            </span>
          </button>

          {errInfo && (
            <div
              role="alert"
              className="mt-3 flex animate-fade-in items-start gap-2.5 rounded-xl border border-blush-300 bg-blush-50 px-3.5 py-3"
            >
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-status-bad" strokeWidth={2} aria-hidden="true" />
              <div>
                <p className="text-[0.92rem] font-semibold leading-tight text-brown-800">{errInfo.title}</p>
                <p className="mt-1 text-[0.82rem] leading-snug text-brown-600">{errInfo.body}</p>
              </div>
            </div>
          )}
        </>
      )}

      {/* VALIDATING */}
      {status === 'validating' && (
        <div className="flex flex-col items-center gap-3 py-10 text-center" role="status">
          <Loader2 className="h-8 w-8 animate-spin text-brown-400" strokeWidth={1.8} aria-hidden="true" />
          <p className="font-serif text-[1.15rem] text-brown-700">Checking your file...</p>
          {picked && <p className="max-w-full truncate px-4 text-[0.82rem] text-brown-500">{picked.name}</p>}
        </div>
      )}

      {/* UPLOADING and UPLOADED: file card */}
      {(status === 'uploading' || status === 'uploaded') && shown && (
        <div className="animate-fade-in">
          <div className="flex items-center gap-3 rounded-card border border-gold-100 bg-card-warm p-3.5 shadow-soft">
            <span
              className={cn(
                'flex h-12 w-12 shrink-0 items-center justify-center rounded-full',
                status === 'uploaded' ? 'bg-sage-100 text-sage-500' : 'bg-mist-100 text-mist-500'
              )}
            >
              {status === 'uploaded' ? (
                <CheckCircle2 className="h-6 w-6" strokeWidth={2} aria-hidden="true" />
              ) : (
                <FileAudio className="h-6 w-6" strokeWidth={1.8} aria-hidden="true" />
              )}
            </span>

            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.95rem] font-medium leading-tight text-brown-900" title={shown.name}>
                {shown.name}
              </p>
              <p className="mt-1 text-[0.78rem] leading-none text-brown-500">
                {[
                  status === 'uploaded' && Number(audio?.duration) > 0 ? formatTime(audio.duration) : null,
                  Number(shown.size) > 0 ? formatFileSize(shown.size) : null,
                ]
                  .filter(Boolean)
                  .join(' \u00B7 ')}
              </p>
            </div>

            {status === 'uploading' ? (
              <span className="shrink-0 text-[0.85rem] font-medium tabular-nums text-brown-600">{progress}%</span>
            ) : (
              <button
                type="button"
                onClick={handleRemove}
                aria-label="Remove file"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-brown-400 transition-colors hover:bg-blush-100 hover:text-status-bad"
              >
                <Trash2 className="h-[1.1rem] w-[1.1rem]" strokeWidth={1.8} aria-hidden="true" />
              </button>
            )}
          </div>

          {status === 'uploading' && (
            <div className="mt-3" role="status">
              <ProgressBar value={progress} tone="brand" size="md" animate={false} label="Upload progress" />
              <p className="mt-2 text-[0.8rem] text-brown-500">Preparing your audio...</p>
            </div>
          )}

          {status === 'uploaded' && audio && (
            <>
              <p className="mt-3 flex items-center gap-1.5 text-[0.85rem] font-medium text-sage-600">
                <CheckCircle2 className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
                Ready to use
              </p>
              <PreviewButton audio={audio} />
            </>
          )}
        </div>
      )}
    </Modal>
  )
}
