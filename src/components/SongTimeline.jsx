import { useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'

import Badge from '@/components/Badge'
import { cn } from '@/utils/cn'
import { clamp, formatTime } from '@/utils/formatters'
import { getScoreBand } from '@/utils/scoreHelpers'

/**
 * Section-by-section view of WHERE the singer needs to improve.
 *
 *   00:00 ------ 01:00 ------ 02:00 ------ 03:00
 *   [ Verse 1 ][ Chorus ][ Verse 2 ][ High notes ][ Final chorus ]
 *
 *   check  Verse 1            00:00-00:58   88
 *   warn   Chorus             00:58-01:44   79   [Pitch deviation]
 *   ...
 *
 * Props:
 *   sections   analysis.sections:
 *              [{ id, sectionName, startTime, endTime, score, status, issues, note }]
 *              status: 'good' | 'warning' | 'critical' (optional, derived from
 *              the score when missing). issues: [{ type, label }]
 *   duration   total length in seconds (analysis.original.duration).
 *              Falls back to the end of the last section.
 *   onSelect   optional, called with the section when one is chosen
 *
 * Everything shown comes from `sections`. No sections means nothing renders.
 */

const STATUS = {
  good: {
    label: 'Good',
    Icon: CheckCircle2,
    bar: 'bg-sage-400',
    barActive: 'bg-sage-500',
    text: 'text-sage-600',
    iconBg: 'bg-sage-50',
    badge: 'good',
  },
  warn: {
    label: 'Needs attention',
    Icon: AlertTriangle,
    bar: 'bg-[#E3A55C]',
    barActive: 'bg-status-warn',
    text: 'text-status-warn',
    iconBg: 'bg-blush-50',
    badge: 'warn',
  },
  bad: {
    label: 'Needs work',
    Icon: XCircle,
    bar: 'bg-[#D98079]',
    barActive: 'bg-status-bad',
    text: 'text-status-bad',
    iconBg: 'bg-blush-100',
    badge: 'bad',
  },
}

/** Maps the backend's status word to a tone, falling back to the score. */
function resolveTone(section) {
  switch (section.status) {
    case 'good':
    case 'excellent':
      return 'good'
    case 'warning':
    case 'needs_improvement':
    case 'needs_practice':
      return 'warn'
    case 'critical':
    case 'poor':
      return 'bad'
    default:
      return getScoreBand(section.score).tone
  }
}

/** Picks a tidy tick spacing so the ruler never gets crowded. */
function tickStep(total) {
  const steps = [15, 30, 60, 120, 180, 300, 600]
  return steps.find((s) => total / s <= 6) || 600
}

export default function SongTimeline({ sections, duration, onSelect, className }) {
  const [activeId, setActiveId] = useState(null)

  const model = useMemo(() => {
    if (!Array.isArray(sections) || sections.length === 0) return null

    const list = sections
      .filter((s) => Number.isFinite(Number(s.startTime)) && Number.isFinite(Number(s.endTime)))
      .map((s, i) => ({
        ...s,
        key: s.id ?? `${s.sectionName}-${i}`,
        start: Number(s.startTime),
        end: Number(s.endTime),
        tone: resolveTone(s),
      }))
      .sort((a, b) => a.start - b.start)

    if (list.length === 0) return null

    const lastEnd = list[list.length - 1].end
    const total = Math.max(Number(duration) || 0, lastEnd, 1)

    const step = tickStep(total)
    const ticks = []
    for (let t = 0; t < total; t += step) ticks.push(t)

    return { list, total, ticks }
  }, [sections, duration])

  if (!model) return null

  const { list, total, ticks } = model
  const attention = list.filter((s) => s.tone !== 'good').length

  const choose = (section) => {
    setActiveId((current) => (current === section.key ? null : section.key))
    onSelect?.(section)
  }

  return (
    <section aria-label="Song timeline" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
            Song Timeline
          </h2>
          <p className="mt-1.5 text-[0.82rem] leading-snug text-brown-500">
            See where you did well and where to focus.
          </p>
        </div>

        <Badge variant={attention === 0 ? 'good' : 'warn'} size="sm" className="mt-1">
          {attention === 0
            ? 'All sections on track'
            : `${attention} of ${list.length} ${list.length === 1 ? 'section' : 'sections'} to work on`}
        </Badge>
      </div>

      {/* Time ruler */}
      <div className="relative mt-5 h-4" aria-hidden="true">
        {ticks.map((t, i) => (
          <span
            key={t}
            className="absolute top-0 text-[0.68rem] tabular-nums leading-none text-brown-400"
            style={{
              left: `${clamp((t / total) * 100, 0, 100)}%`,
              transform: i === 0 ? 'none' : 'translateX(-50%)',
            }}
          >
            {formatTime(t)}
          </span>
        ))}
      </div>

      {/* Track: each segment is as wide as its section */}
      <div className="mt-1.5 flex h-9 gap-[3px] sm:h-10" role="group" aria-label="Song sections">
        {list.map((s) => {
          const style = STATUS[s.tone]
          const isActive = activeId === s.key
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => choose(s)}
              aria-pressed={isActive}
              aria-label={`${s.sectionName}, ${formatTime(s.start)} to ${formatTime(s.end)}, ${style.label}`}
              title={s.sectionName}
              className={cn(
                'min-w-[6px] rounded-md transition-all duration-200',
                isActive ? style.barActive : style.bar,
                activeId && !isActive && 'opacity-45',
                'hover:brightness-105'
              )}
              style={{ flex: `${Math.max(s.end - s.start, 1)} 1 0%` }}
            />
          )
        })}
      </div>

      {/* Section list */}
      <ul className="mt-4 flex flex-col gap-2">
        {list.map((s) => {
          const style = STATUS[s.tone]
          const Icon = style.Icon
          const isActive = activeId === s.key
          const issues = Array.isArray(s.issues) ? s.issues : []
          const hasScore = s.score !== null && s.score !== undefined && Number.isFinite(Number(s.score))

          return (
            <li key={s.key}>
              <button
                type="button"
                onClick={() => choose(s)}
                aria-pressed={isActive}
                className={cn(
                  'flex w-full items-start gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors',
                  isActive
                    ? 'border-gold-200 bg-blush-50'
                    : 'border-gold-100/70 bg-ivory-50/70 hover:bg-blush-50/60'
                )}
              >
                <span
                  className={cn('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full', style.iconBg, style.text)}
                >
                  <Icon className="h-[1.1rem] w-[1.1rem]" strokeWidth={2} aria-hidden="true" />
                </span>

                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                    <span className="font-serif text-[1.05rem] font-semibold leading-tight text-brown-900">
                      {s.sectionName}
                    </span>
                    <span className="text-[0.74rem] tabular-nums text-brown-500">
                      {formatTime(s.start)}
                      {'\u2013'}
                      {formatTime(s.end)}
                    </span>
                  </span>

                  {(issues.length > 0 || s.note) && (
                    <span className="mt-1.5 flex flex-wrap gap-1.5">
                      {issues.map((issue, i) => (
                        <Badge key={`${issue.type}-${i}`} variant={style.badge} size="sm">
                          {issue.label || issue.type}
                        </Badge>
                      ))}
                      {s.note && (
                        <Badge variant="gold" size="sm">
                          {s.note}
                        </Badge>
                      )}
                    </span>
                  )}

                  {issues.length === 0 && !s.note && (
                    <span className={cn('mt-1 block text-[0.78rem] leading-none', style.text)}>{style.label}</span>
                  )}
                </span>

                {hasScore && (
                  <span className="shrink-0 pt-0.5 text-right">
                    <span className={cn('font-serif text-[1.2rem] font-semibold leading-none tabular-nums', style.text)}>
                      {Math.round(clamp(s.score, 0, 100))}
                    </span>
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
