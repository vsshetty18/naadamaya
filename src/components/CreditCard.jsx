import { Crown, Sparkles } from 'lucide-react'

import Badge from '@/components/Badge'
import ProgressBar from '@/components/ProgressBar'
import { getPlan } from '@/data/plans'
import { cn } from '@/utils/cn'
import { clamp, pluralize } from '@/utils/formatters'

/**
 * The credit balance card at the top of the Credits page.
 *
 *   (crown)
 *      10
 *   Credits Remaining
 *   Use credits to analyze your singing and receive detailed feedback.
 *   ===========================   10 / 10 credits remaining
 *
 * Props:
 *   credits   AppStateContext credits: { plan, total, remaining }
 *
 * Every number comes from `credits`. The bar's tone follows how many are
 * left: sage when plenty, amber when running low, red when none remain.
 */

function levelFor(remaining, total) {
  if (remaining <= 0) return { tone: 'bad', note: 'You have no credits left. Upgrade to keep analysing.' }
  const pct = total > 0 ? (remaining / total) * 100 : 0
  if (remaining <= 2 || pct <= 20) return { tone: 'warn', note: 'Running low. Consider upgrading your plan.' }
  return { tone: 'good', note: null }
}

export default function CreditCard({ credits, className }) {
  if (!credits) return null

  const total = Math.max(0, Number(credits.total) || 0)
  const remaining = clamp(credits.remaining, 0, total || Infinity)
  const percent = total > 0 ? (remaining / total) * 100 : 0
  const plan = getPlan(credits.plan)
  const { tone, note } = levelFor(remaining, total)

  return (
    <section
      aria-label="Credit balance"
      className={cn('nm-card relative animate-fade-up overflow-hidden px-5 py-7 text-center sm:px-8 sm:py-9', className)}
    >
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-gold-50/80 via-transparent to-sage-50/60" />

      <div className="relative flex flex-col items-center">
        {plan && (
          <Badge variant="gold" size="sm" className="mb-3">
            {plan.name} plan
          </Badge>
        )}

        <span className="flex h-16 w-16 items-center justify-center rounded-full bg-gold-50 text-gold-500 shadow-soft">
          <Crown className="h-8 w-8" strokeWidth={1.6} aria-hidden="true" />
        </span>

        <p
          className="mt-3 font-serif text-[4rem] font-semibold leading-none tabular-nums text-brown-900 sm:text-[4.5rem]"
          aria-live="polite"
        >
          {remaining}
        </p>
        <p className="mt-1.5 font-serif text-[1.3rem] text-brown-700">
          {remaining === 1 ? 'Credit Remaining' : 'Credits Remaining'}
        </p>
        <p className="mt-2 max-w-sm text-[0.88rem] leading-snug text-brown-500">
          Use credits to analyze your singing and receive detailed feedback.
        </p>

        <div className="mt-5 flex w-full max-w-sm items-center gap-3">
          <ProgressBar
            value={percent}
            tone={tone}
            size="lg"
            label={`${remaining} of ${pluralize(total, 'credit')} remaining`}
            className="flex-1"
          />
        </div>
        <p className="mt-2 text-[0.82rem] tabular-nums text-brown-600">
          {remaining} / {pluralize(total, 'credit')} remaining
        </p>

        {note && (
          <p className="mt-3 flex items-center gap-1.5 text-[0.82rem] font-medium text-brown-600">
            <Sparkles className="h-4 w-4 text-gold-500" strokeWidth={1.8} aria-hidden="true" />
            {note}
          </p>
        )}
      </div>
    </section>
  )
}
