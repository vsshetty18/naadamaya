import { Check, Loader2, Music } from 'lucide-react'

import Button from '@/components/Button'
import ProgressBar from '@/components/ProgressBar'
import { ANALYSIS_STEPS, COMPLETE_LABEL } from '@/services/analysisService'
import { cn } from '@/utils/cn'
import { clamp } from '@/utils/formatters'

/**
 * The "Processing" screen on the Report page, shown while a run is active.
 *
 *   (pulsing rings + bars)
 *   Analyzing pitch...
 *   ==========-----------   34%
 *   [x] Listening to your performance...
 *   [~] Analyzing pitch...
 *   [ ] Comparing melody...
 *   ...
 *                [ Cancel ]
 *
 * Props:
 *   progress   run.progress from AppStateContext, as sent by analysisService:
 *              { status, stepIndex, totalSteps, stepId, label, percent }
 *   onCancel   called by the Cancel button (context.cancelAnalysis)
 *
 * It only reports what the service says. The "Analysis complete." line
 * appears only when the service has sent a `complete` event, never earlier.
 * No analysis happens here.
 */

const BAR_DELAYS = [0, 0.15, 0.3, 0.45, 0.6, 0.45, 0.3, 0.15, 0]

export default function ProcessingState({ progress, onCancel, className }) {
  const total = progress?.totalSteps || ANALYSIS_STEPS.length
  const isComplete = progress?.status === 'complete'

  // Before the first event arrives, treat step 0 as the current one.
  const current = isComplete ? total : clamp(progress?.stepIndex ?? 0, 0, total - 1)
  const percent = isComplete ? 100 : clamp(progress?.percent ?? 0, 0, 100)
  const headline = isComplete ? COMPLETE_LABEL : progress?.label || ANALYSIS_STEPS[0].label

  return (
    <section
      aria-label="Analysis in progress"
      className={cn('nm-card mx-auto w-full max-w-xl animate-fade-up px-5 py-8 text-center sm:px-8 sm:py-10', className)}
    >
      {/* Pulsing rings around a note, with bars that breathe underneath */}
      <div className="relative mx-auto flex h-28 w-28 items-center justify-center" aria-hidden="true">
        <span className="absolute inset-0 animate-pulse-soft rounded-full bg-gold-50" />
        <span
          className="absolute inset-3 animate-pulse-soft rounded-full bg-gold-100/80"
          style={{ animationDelay: '0.3s' }}
        />
        <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-cta-brown text-ivory-50 shadow-cta">
          {isComplete ? (
            <Check className="h-7 w-7" strokeWidth={2.4} />
          ) : (
            <Music className="h-7 w-7" strokeWidth={1.8} />
          )}
        </span>
      </div>

      <div className="mt-3 flex h-6 items-center justify-center gap-1" aria-hidden="true">
        {BAR_DELAYS.map((delay, i) => (
          <span
            key={i}
            className={cn('w-1 rounded-full bg-brown-300', !isComplete && 'animate-pulse-soft')}
            style={{ height: `${40 + (i % 5) * 12}%`, animationDelay: `${delay}s` }}
          />
        ))}
      </div>

      {/* Current step. aria-live announces each change to screen readers. */}
      <div role="status" aria-live="polite">
        <h2 className="mt-4 font-serif text-[1.55rem] font-semibold leading-tight text-brown-900 sm:text-[1.8rem]">
          {headline}
        </h2>
        <p className="mt-1.5 text-[0.85rem] leading-snug text-brown-500">
          {isComplete
            ? 'Opening your report.'
            : 'Comparing your singing with the original. This takes a few seconds.'}
        </p>
      </div>

      <div className="mx-auto mt-5 flex max-w-sm items-center gap-3">
        <ProgressBar
          value={percent}
          tone="brand"
          size="md"
          animate={false}
          label="Analysis progress"
          className="flex-1"
        />
        <span className="w-10 text-right text-[0.82rem] font-medium tabular-nums text-brown-600">
          {Math.round(percent)}%
        </span>
      </div>

      {/* Step list */}
      <ol className="mx-auto mt-6 flex max-w-sm flex-col gap-2 text-left">
        {ANALYSIS_STEPS.map((step, i) => {
          const done = i < current || isComplete
          const active = i === current && !isComplete

          return (
            <li
              key={step.id}
              aria-current={active ? 'step' : undefined}
              className={cn(
                'flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors duration-300',
                done && 'border-sage-200 bg-sage-50/70',
                active && 'border-gold-200 bg-blush-50',
                !done && !active && 'border-gold-100/60 bg-ivory-50/50'
              )}
            >
              <span
                className={cn(
                  'flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                  done && 'bg-sage-500 text-white',
                  active && 'bg-gold-100 text-brown-500',
                  !done && !active && 'bg-ivory-200 text-brown-300'
                )}
                aria-hidden="true"
              >
                {done ? (
                  <Check className="h-3.5 w-3.5" strokeWidth={3} />
                ) : active ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.4} />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
              </span>

              <span
                className={cn(
                  'text-[0.88rem] leading-tight',
                  done && 'text-brown-600',
                  active && 'font-medium text-brown-900',
                  !done && !active && 'text-brown-400'
                )}
              >
                {step.label}
              </span>

              <span className="sr-only">{done ? 'Done' : active ? 'In progress' : 'Waiting'}</span>
            </li>
          )
        })}

        {isComplete && (
          <li className="flex items-center gap-3 rounded-xl border border-sage-300 bg-sage-100 px-3 py-2.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sage-500 text-white" aria-hidden="true">
              <Check className="h-3.5 w-3.5" strokeWidth={3} />
            </span>
            <span className="text-[0.88rem] font-semibold text-sage-600">{COMPLETE_LABEL}</span>
          </li>
        )}
      </ol>

      {!isComplete && onCancel && (
        <Button variant="ghost" onClick={onCancel} className="mt-6">
          Cancel
        </Button>
      )}
    </section>
  )
}
