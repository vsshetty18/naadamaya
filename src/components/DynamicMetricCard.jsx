import { Mic } from 'lucide-react'

import ProgressBar from '@/components/ProgressBar'
import { cn } from '@/utils/cn'
import { clamp } from '@/utils/formatters'
import { getMetricConfig, getMetricName } from '@/utils/metricConfig'
import { getMetricTone } from '@/utils/scoreHelpers'

/**
 * One evaluation tile in the Overall Score card.
 *
 *   Pitch Accuracy
 *   [icon]  82/100
 *   ==========----
 *
 * Props:
 *   metric        a metric object from analysis.metrics:
 *                 { id, name, score, status, description, relevance }
 *   showDescription  shows metric.description under the bar (roomier layouts)
 *
 * Or pass the fields directly: name, score, icon, status, description,
 * relevance. Direct props win over `metric`, so the card works both ways.
 *
 * The icon and colour come from metricConfig using the metric id. Which
 * metrics appear, and their scores, come only from the analysis. An unknown
 * id from a future backend still renders with a fallback icon and colour.
 * A metric with no usable score is not drawn at all (no empty cards).
 */

export default function DynamicMetricCard({
  metric = {},
  name,
  score,
  icon,
  status,
  description,
  relevance,
  showDescription = false,
  className,
}) {
  const resolved = {
    id: metric.id,
    name: name ?? metric.name,
    score: score ?? metric.score,
    status: status ?? metric.status,
    description: description ?? metric.description,
    relevance: relevance ?? metric.relevance,
  }

  const hasScore =
    resolved.score !== null &&
    resolved.score !== undefined &&
    resolved.score !== '' &&
    Number.isFinite(Number(resolved.score))

  // Never show an empty card.
  if (!hasScore) return null

  const config = getMetricConfig(resolved.id)
  const Icon = icon || config.icon || Mic
  const label = getMetricName({ id: resolved.id, name: resolved.name })
  const value = clamp(resolved.score, 0, 100)
  const tone = getMetricTone(resolved.status, value)
  const needsWork = tone === getMetricTone('needs_improvement').styles ? false : false

  return (
    <div
      className={cn(
        'flex min-w-0 flex-col rounded-xl border border-gold-100/70 bg-ivory-50/80 p-2.5 sm:p-3',
        resolved.relevance === 'high' && 'shadow-soft',
        className
      )}
    >
      <p className="truncate text-[0.74rem] font-medium leading-tight text-brown-700 sm:text-[0.82rem]" title={label}>
        {label}
      </p>

      <div className="mt-2 flex items-center gap-1.5">
        <Icon
          className="h-[1.2rem] w-[1.2rem] shrink-0 sm:h-5 sm:w-5"
          style={{ color: config.color }}
          strokeWidth={2}
          aria-hidden="true"
        />
        <span className="font-serif text-[1.1rem] font-semibold leading-none tabular-nums text-brown-900 sm:text-[1.25rem]">
          {Math.round(value)}
          <span className="font-sans text-[0.7rem] font-normal text-brown-500">/100</span>
        </span>
      </div>

      <ProgressBar
        value={value}
        color={config.color}
        track={config.track}
        size="sm"
        label={`${label}: ${Math.round(value)} out of 100`}
        className="mt-2.5"
      />

      {showDescription && resolved.description && (
        <p className="mt-2 text-[0.74rem] leading-snug text-brown-500">{resolved.description}</p>
      )}
    </div>
  )
}
