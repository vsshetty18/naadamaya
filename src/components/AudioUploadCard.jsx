import { AlertCircle, CheckCircle2, Mic, UploadCloud, X } from 'lucide-react'

import Button from '@/components/Button'
import { cn } from '@/utils/cn'
import { formatFileSize, formatTime } from '@/utils/formatters'

/**
 * One audio input card on Learn: "Original" or "Your Voice".
 *
 *   [ icon ]  Title                  [ Upload ] [ Record ]
 *             Description
 *   ---------------------------------------------------------
 *   (only when a file is chosen)  check  file name  meta   X
 *
 * The buttons stay visible after a file is chosen, so the user can replace
 * it by uploading or recording again. The card only draws the slot. The
 * modals and the state live in the Learn page and AppStateContext.
 *
 * Props:
 *   title, description
 *   icon      a lucide component (Music, User)
 *   tone      'mist' (Original) | 'sage' (Your Voice)
 *   audio     the slot object from AppStateContext, or null
 *   error     a message shown under the card (for example "audio missing")
 *   onUpload, onRecord, onRemove
 *   disabled  locks the card while an analysis is running
 */

const TONES = {
  mist: { circle: 'bg-mist-100 text-mist-500', ring: 'ring-mist-200' },
  sage: { circle: 'bg-sage-100 text-sage-500', ring: 'ring-sage-200' },
}

/** "Uploaded", "Recorded" or "Demo recording", based on how the slot was filled. */
function sourceLabel(audio) {
  if (audio.simulated) return 'Demo recording'
  return audio.file ? 'Uploaded' : 'Recorded'
}

/** Duration and size as small text parts. Unknown values are skipped, never shown as 00:00. */
function metaParts(audio) {
  const parts = []
  if (Number(audio.duration) > 0) parts.push(formatTime(audio.duration))
  if (Number(audio.size) > 0) parts.push(formatFileSize(audio.size))
  parts.push(sourceLabel(audio))
  return parts
}

export default function AudioUploadCard({
  title,
  description,
  icon: Icon,
  tone = 'mist',
  audio,
  error,
  onUpload,
  onRecord,
  onRemove,
  disabled = false,
  className,
}) {
  const styles = TONES[tone] || TONES.mist
  const hasAudio = Boolean(audio)

  return (
    <section className={cn('animate-fade-up', className)} aria-label={title}>
      <div className={cn('nm-card p-3.5 sm:p-4', error && 'border-status-bad/40')}>
        {/* Main row */}
        <div className="flex items-center gap-3 max-[359px]:flex-col max-[359px]:items-stretch">
          <div className="flex min-w-0 flex-1 items-center gap-3 border-r border-gold-100 pr-3 max-[359px]:border-r-0 max-[359px]:pr-0">
            <span
              className={cn(
                'flex h-12 w-12 shrink-0 items-center justify-center rounded-full sm:h-14 sm:w-14',
                styles.circle,
                hasAudio && 'ring-2 ring-offset-2 ring-offset-ivory-50',
                hasAudio && styles.ring
              )}
            >
              {Icon && <Icon className="h-6 w-6 sm:h-7 sm:w-7" strokeWidth={2} aria-hidden="true" />}
            </span>

            <div className="min-w-0">
              <h3 className="font-serif text-[1.3rem] font-semibold leading-none text-brown-900 sm:text-[1.45rem]">
                {title}
              </h3>
              <p className="mt-1.5 text-[0.82rem] leading-snug text-brown-500">{description}</p>
            </div>
          </div>

          <div className="flex shrink-0 gap-2 max-[359px]:[&>*]:flex-1">
            <Button
              variant="upload"
              leftIcon={UploadCloud}
              onClick={onUpload}
              disabled={disabled}
              className="h-[3rem] gap-1.5 px-3 sm:px-4"
              aria-label={`Upload ${title}`}
            >
              Upload
            </Button>
            <Button
              variant="record"
              leftIcon={Mic}
              onClick={onRecord}
              disabled={disabled}
              className="h-[3rem] gap-1.5 px-3 sm:px-4"
              aria-label={`Record ${title}`}
            >
              Record
            </Button>
          </div>
        </div>

        {/* Selected audio */}
        {hasAudio && (
          <div className="mt-3 flex animate-fade-in items-center gap-2.5 rounded-xl border border-sage-200 bg-sage-50/70 px-3 py-2.5">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-sage-500" strokeWidth={2} aria-hidden="true" />

            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.88rem] font-medium leading-tight text-brown-800" title={audio.name}>
                {audio.name}
              </p>
              <p className="mt-0.5 truncate text-[0.74rem] leading-tight text-brown-500">
                {metaParts(audio).join(' \u00B7 ')}
              </p>
            </div>

            <button
              type="button"
              onClick={onRemove}
              disabled={disabled}
              aria-label={`Remove ${title} audio`}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-brown-400 transition-colors hover:bg-white hover:text-status-bad disabled:opacity-50"
            >
              <X className="h-4 w-4" strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {/* Error (for example a missing or unsupported file) */}
      {error && (
        <p role="alert" className="mt-2 flex animate-fade-in items-center gap-1.5 px-1 text-[0.82rem] text-status-bad">
          <AlertCircle className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
          {error}
        </p>
      )}
    </section>
  )
}
