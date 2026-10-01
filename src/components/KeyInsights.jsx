import { ArrowUp, Check, Info, Lightbulb } from 'lucide-react'

import { cn } from '@/utils/cn'

/**
 * The "Key Insights" card on the Report.
 *
 *   (bulb) Key Insights
 *   [check] Good pitch accuracy in most parts!
 *   [check] Your pronunciation is clear.
 *   [up]    Try to maintain consistent pitch in higher notes.
 *   [up]    Work on breath control for longer lines.
 *
 * Props:
 *   insights   analysis.insights:
 *              [{ type, title, description }]
 *              type: 'positive' | 'improvement' | anything else (shown as a neutral note)
 *   showDescriptions   shows each insight's description under its title
 *                      (roomier layouts such as desktop)
 *
 * Every line comes from `insights`. Nothing is hardcoded, so a song with no
 * positives shows only improvements, and no insights means no card.
 */

const TYPES = {
  positive: {
    Icon: Check,
    row: 'bg-sage-50 border-sage-100',
    dot: 'bg-sage-500 text-white',
  },
  improvement: {
    Icon: ArrowUp,
    row: 'bg-blush-50 border-blush-100',
    dot: 'bg-status-warn text-white',
  },
  neutral: {
    Icon: Info,
    row: 'bg-mist-50 border-mist-100',
    dot: 'bg-mist-400 text-white',
  },
}

function resolveType(type) {
  if (type === 'positive' || type === 'improvement') return type
  return 'neutral'
}

export default function KeyInsights({ insights, showDescriptions = false, className }) {
  const items = (Array.isArray(insights) ? insights : []).filter((i) => i && (i.title || i.description))

  // No insights returned, so no empty card.
  if (items.length === 0) return null

  return (
    <section aria-label="Key insights" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <div className="flex items-center gap-2.5">
        <Lightbulb className="h-5 w-5 shrink-0 text-gold-500" strokeWidth={1.8} aria-hidden="true" />
        <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
          Key Insights
        </h2>
      </div>

      <ul className="mt-3.5 flex flex-col gap-2">
        {items.map((item, i) => {
          const style = TYPES[resolveType(item.type)]
          const Icon = style.Icon
          const text = item.title || item.description

          return (
            <li
              key={`${item.title || item.description}-${i}`}
              className={cn('flex items-start gap-2.5 rounded-xl border px-3 py-2.5', style.row)}
            >
              <span
                className={cn('mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full', style.dot)}
              >
                <Icon className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
              </span>

              <span className="min-w-0 flex-1">
                <span className="block text-[0.85rem] font-medium leading-snug text-brown-800">{text}</span>
                {showDescriptions && item.title && item.description && (
                  <span className="mt-1 block text-[0.78rem] leading-snug text-brown-500">
                    {item.description}
                  </span>
                )}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
