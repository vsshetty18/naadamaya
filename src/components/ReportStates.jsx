import {
  AlertCircle,
  BarChart3,
  Clock,
  Crown,
  FileWarning,
  Music,
  RefreshCw,
  SearchX,
  WifiOff,
} from 'lucide-react'

import Button from '@/components/Button'
import { cn } from '@/utils/cn'

/**
 * The non-report screens of the Report page.
 *
 *   EmptyReport      no analysis yet
 *   ErrorReport      analysis failed (audio missing, unsupported format,
 *                    no credits, timeout, network, not found, failed)
 *   ReportSkeleton   loading placeholder while a saved report is fetched
 *
 * The uploading and processing states are covered elsewhere:
 *   uploading   UploadModal (File 28)
 *   processing  ProcessingState (File 41)
 *   completed   the report itself
 *
 * These only draw screens. Where the buttons lead is decided by the caller.
 */

/* ==========================================================
   SHARED FRAME
   ========================================================== */

function StateCard({ icon: Icon, tone = 'gold', title, body, children, className }) {
  const tones = {
    gold: 'bg-gold-50 text-gold-500',
    bad: 'bg-blush-100 text-status-bad',
    warn: 'bg-blush-50 text-status-warn',
    mist: 'bg-mist-100 text-mist-500',
  }

  return (
    <section
      className={cn(
        'nm-card mx-auto flex w-full max-w-xl animate-fade-up flex-col items-center px-6 py-10 text-center sm:px-10 sm:py-12',
        className
      )}
    >
      <span className={cn('flex h-16 w-16 items-center justify-center rounded-full', tones[tone] || tones.gold)}>
        <Icon className="h-8 w-8" strokeWidth={1.6} aria-hidden="true" />
      </span>

      <h2 className="mt-5 font-serif text-[1.6rem] font-semibold leading-tight text-brown-900 sm:text-[1.9rem]">
        {title}
      </h2>
      <p className="mt-2 max-w-sm text-[0.92rem] leading-relaxed text-brown-500">{body}</p>

      {children && <div className="mt-6 flex w-full max-w-xs flex-col gap-2.5">{children}</div>}
    </section>
  )
}

/* ==========================================================
   EMPTY: no analysis yet
   ========================================================== */

export function EmptyReport({ onStart, onBrowse, hasSavedReports = false }) {
  return (
    <StateCard
      icon={BarChart3}
      title="No report yet"
      body="Add the original song and your voice on Learn, and your detailed comparison will appear here."
    >
      <Button variant="primary" leftIcon={Music} onClick={onStart} fullWidth>
        Go to Learn
      </Button>
      {hasSavedReports && onBrowse && (
        <Button variant="secondary" onClick={onBrowse} fullWidth>
          View a previous report
        </Button>
      )}
    </StateCard>
  )
}

/* ==========================================================
   ERROR: keyed by the error codes from analysisService
   ========================================================== */

const ERRORS = {
  audio_missing: {
    icon: FileWarning,
    tone: 'warn',
    title: 'Some audio is missing',
    body: (e) =>
      e.details?.slot === 'original'
        ? 'The original song has not been added. Go back to Learn and add it.'
        : e.details?.slot === 'user'
          ? 'Your singing has not been added. Go back to Learn and add it.'
          : 'Add both the original song and your voice on Learn to continue.',
    action: 'learn',
  },
  unsupported_format: {
    icon: FileWarning,
    tone: 'warn',
    title: 'This format is not supported',
    body: 'Please use an audio file such as MP3, WAV, M4A, AAC, OGG or FLAC.',
    action: 'learn',
  },
  no_credits: {
    icon: Crown,
    tone: 'gold',
    title: 'No credits left',
    body: 'You have used all your analysis credits. Upgrade your plan to keep improving.',
    action: 'credits',
  },
  timeout: {
    icon: Clock,
    tone: 'warn',
    title: 'This is taking too long',
    body: 'The analysis took longer than expected. No credit was used. Please try again.',
    action: 'retry',
  },
  network_error: {
    icon: WifiOff,
    tone: 'warn',
    title: 'Could not connect',
    body: 'We could not reach Naadamaya. Check your connection and try again. No credit was used.',
    action: 'retry',
  },
  not_found: {
    icon: SearchX,
    tone: 'mist',
    title: 'Report not found',
    body: 'We could not find that report. It may have been removed.',
    action: 'learn',
  },
  analysis_failed: {
    icon: AlertCircle,
    tone: 'bad',
    title: 'Analysis could not finish',
    body: 'Something went wrong while analysing this performance. No credit was used. Please try again.',
    action: 'retry',
  },
}

/**
 * Props:
 *   error      { code, message, details } from the context (run.error or report.error)
 *   onRetry    run the analysis again
 *   onLearn    go to Learn
 *   onCredits  go to Credits
 */
export function ErrorReport({ error, onRetry, onLearn, onCredits }) {
  const entry = ERRORS[error?.code] || ERRORS.analysis_failed
  const body = typeof entry.body === 'function' ? entry.body(error || {}) : entry.body

  return (
    <div role="alert">
      <StateCard icon={entry.icon} tone={entry.tone} title={entry.title} body={body}>
        {entry.action === 'retry' && onRetry && (
          <Button variant="primary" leftIcon={RefreshCw} onClick={onRetry} fullWidth>
            Try again
          </Button>
        )}
        {entry.action === 'credits' && onCredits && (
          <Button variant="primary" leftIcon={Crown} onClick={onCredits} fullWidth>
            See plans
          </Button>
        )}
        {onLearn && (
          <Button variant={entry.action === 'learn' ? 'primary' : 'secondary'} onClick={onLearn} fullWidth>
            Back to Learn
          </Button>
        )}
      </StateCard>
    </div>
  )
}

/* ==========================================================
   SKELETON: while a saved report loads
   ========================================================== */

function Bone({ className }) {
  return <div className={cn('nm-skeleton rounded-lg', className)} />
}

export function ReportSkeleton() {
  return (
    <div className="flex flex-col gap-4" role="status" aria-label="Loading report">
      <div className="nm-card space-y-4 p-4">
        {[0, 1].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <Bone className="h-12 w-12 shrink-0 rounded-xl" />
            <Bone className="h-4 w-24" />
            <Bone className="h-11 w-11 shrink-0 rounded-full" />
            <Bone className="h-8 flex-1" />
          </div>
        ))}
      </div>

      <div className="nm-card grid grid-cols-[auto_1fr] gap-4 p-4">
        <div className="space-y-3">
          <Bone className="h-5 w-28" />
          <Bone className="h-32 w-32 rounded-full" />
        </div>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Bone key={i} className="h-20" />
          ))}
        </div>
      </div>

      <div className="nm-card space-y-3 p-4">
        <Bone className="h-5 w-40" />
        <Bone className="h-44 w-full" />
      </div>

      <span className="sr-only">Loading your report...</span>
    </div>
  )
}
