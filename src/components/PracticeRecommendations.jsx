import { useState } from 'react'
import { Check, Clock, Target } from 'lucide-react'

import { cn } from '@/utils/cn'
import { getMetricConfig } from '@/utils/metricConfig'

/**
 * The "What Should You Practice?" card on the Report.
 *
 *   (target) What Should You Practice?
 *   Based on the areas that need the most attention.
 *
 *   [1]  Steady the high notes                 10 min   [ ]
 *        Practice the high-note section slowly...
 *        [Stability]  [High-note section]
 *
 * Props:
 *   recommendations   analysis.recommendations:
 *                     [{ id, priority, title, description, metricId,
 *                        sectionId, duration }]
 *   sections          analysis.sections, used only to turn a `sectionId`
 *                     into a readable section name for the tag
 *   metrics           analysis.metrics, used only to turn a `metricId`
 *                     into a readable metric name for the tag
 *
 * Every line comes from the analysis. The order follows `priority` (lowest
 * number first). Ticking a step is local to this screen and is not saved.
 * No recommendations means no card.
 */

export default function PracticeRecommendations({ recommendations, sections, metrics, className }) {
  const [done, setDone] = useState({})

  const items = (Array.isArray(recommendations) ? recommendations : [])
    .filter((r) => r && (r.title || r.description))
    .map((r, i) => ({ ...r, order: Number.isFinite(Number(r.priority)) ? Number(r.priority) : i + 1 }))
    .sort((a, b) => a.order - b.order)

  // Nothing returned, so no empty card.
  if (items.length === 0) return null

  const sectionName = (id) =>
    id ? (Array.isArray(sections) ? sections.find((s) => s.id === id)?.sectionName : null) : null
  const metricName = (id) =>
    id ? (Array.isArray(metrics) ? metrics.find((m) => m.id === id)?.name : null) : null

  const toggle = (key) => setDone((d) => ({ ...d, [key]: !d[key] }))
  const doneCount = items.filter((r, i) => done[r.id ?? i]).length

  return (
    <section aria-label="Practice recommendations" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <Target className="mt-0.5 h-5 w-5 shrink-0 text-gold-500" strokeWidth={1.8} aria-hidden="true" />
          <div>
            <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
              What Should You Practice?
            </h2>
            <p className="mt-1.5 text-[0.82rem] leading-snug text-brown-500">
              Based on the areas that need the most attention.
            </p>
          </div>
        </div>

        <span className="shrink-0 pt-1 text-[0.75rem] tabular-nums text-brown-500">
          {doneCount}/{items.length} done
        </span>
      </div>

      <ol className="mt-4 flex flex-col gap-2.5">
        {items.map((r, i) => {
          const key = r.id ?? i
          const isDone = Boolean(done[key])
          const metric = metricName(r.metricId)
          const section = sectionName(r.sectionId)
          const color = getMetricConfig(r.metricId).color

          return (
            <li
              key={key}
              className={cn(
                'flex items-start gap-3 rounded-xl border px-3 py-3 transition-colors',
                isDone ? 'border-sage-200 bg-sage-50/70' : 'border-gold-100/70 bg-ivory-50/70'
              )}
            >
              <span
                className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-serif text-[0.95rem] font-semibold text-white"
                style={{ backgroundColor: isDone ? '#5F7F55' : color }}
                aria-hidden="true"
              >
                {isDone ? <Check className="h-4 w-4" strokeWidth={3} /> : i + 1}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p
                    className={cn(
                      'font-serif text-[1.05rem] font-semibold leading-tight text-brown-900',
                      isDone && 'text-brown-500 line-through decoration-brown-300'
                    )}
                  >
                    {r.title || r.description}
                  </p>
                  {r.duration && (
                    <span className="flex shrink-0 items-center gap-1 pt-0.5 text-[0.72rem] text-brown-500">
                      <Clock className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
                      {r.duration}
                    </span>
                  )}
                </div>

                {r.title && r.description && (
                  <p className="mt-1 text-[0.8rem] leading-snug text-brown-500">{r.description}</p>
                )}

                {(metric || section) && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {metric && (
                      <span className="rounded-pill border border-gold-100 bg-ivory-100 px-2 py-1 text-[0.68rem] font-medium leading-none text-brown-600">
                        {metric}
                      </span>
                    )}
                    {section && (
                      <span className="rounded-pill border border-mist-200 bg-mist-50 px-2 py-1 text-[0.68rem] font-medium leading-none text-mist-500">
                        {section}
                      </span>
                    )}
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={() => toggle(key)}
                aria-pressed={isDone}
                aria-label={`Mark "${r.title || r.description}" as ${isDone ? 'not done' : 'done'}`}
                className={cn(
                  'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 transition-colors',
                  isDone
                    ? 'border-sage-500 bg-sage-500 text-white'
                    : 'border-brown-200 bg-ivory-50 text-transparent hover:border-brown-400'
                )}
              >
                <Check className="h-3.5 w-3.5" strokeWidth={3} aria-hidden="true" />
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
