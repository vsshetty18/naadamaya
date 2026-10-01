import { useMemo } from 'react'
import { Minus, TrendingDown, TrendingUp } from 'lucide-react'

import { cn } from '@/utils/cn'
import { clamp, formatDate } from '@/utils/formatters'
import { getScoreBand, getTrend, TONE_STYLES } from '@/utils/scoreHelpers'

/**
 * The "Attempt History" card on the Report.
 *
 *   Attempt History                      +17 since attempt 1
 *   Is your performance improving?
 *
 *        (65)---(71)---(74)---(78)      line chart
 *        #1     #2     #3     #4
 *
 *   Attempt 4   28 Sep 2026    78   up 4
 *   Attempt 3   25 Sep 2026    74   up 3
 *
 * Props:
 *   history   attempts for the song on screen (AppStateContext.currentHistory):
 *             [{ attempt, score, date }]
 *
 * Every number comes from `history`. A new analysis appends an attempt, so
 * the chart and list grow. With no attempts the card is not drawn. With one
 * attempt it shows that score and an encouraging note instead of a trend.
 */

const W = 300
const H = 120
const PAD_X = 22
const PAD_TOP = 22
const PAD_BOTTOM = 16

export default function AttemptHistory({ history, className }) {
  const attempts = useMemo(
    () =>
      (Array.isArray(history) ? history : [])
        .filter((a) => a && Number.isFinite(Number(a.score)))
        .map((a, i) => ({
          attempt: Number.isFinite(Number(a.attempt)) ? Number(a.attempt) : i + 1,
          score: clamp(a.score, 0, 100),
          date: a.date,
        }))
        .sort((a, b) => a.attempt - b.attempt),
    [history]
  )

  const model = useMemo(() => {
    if (attempts.length === 0) return null

    const scores = attempts.map((a) => a.score)
    // Zoom the vertical range to the data so small gains are visible,
    // but keep at least a 20-point span so the line never looks wild.
    let min = Math.floor(Math.min(...scores) / 5) * 5 - 5
    let max = Math.ceil(Math.max(...scores) / 5) * 5 + 5
    if (max - min < 20) {
      const mid = (max + min) / 2
      min = mid - 10
      max = mid + 10
    }
    min = Math.max(0, min)
    max = Math.min(100, Math.max(max, min + 20))

    const n = attempts.length
    const toX = (i) => (n === 1 ? W / 2 : PAD_X + (i / (n - 1)) * (W - PAD_X * 2))
    const toY = (v) => PAD_TOP + (1 - (v - min) / (max - min)) * (H - PAD_TOP - PAD_BOTTOM)

    const points = attempts.map((a, i) => ({ ...a, x: toX(i), y: toY(a.score) }))
    const line = points.map((p, i) => `${i ? 'L' : 'M'}${p.x} ${p.y}`).join(' ')
    const area = `${line} L${points[n - 1].x} ${H - PAD_BOTTOM} L${points[0].x} ${H - PAD_BOTTOM} Z`

    return { points, line, area }
  }, [attempts])

  if (!model) return null

  const { points, line, area } = model
  const first = attempts[0]
  const last = attempts[attempts.length - 1]
  const overall = getTrend(first.score, last.score)
  const lastTone = TONE_STYLES[getScoreBand(last.score).tone]

  const OverallIcon = overall.direction === 'up' ? TrendingUp : overall.direction === 'down' ? TrendingDown : Minus

  let summary
  if (attempts.length === 1) {
    summary = 'First attempt recorded. Sing it again to see your progress.'
  } else if (overall.direction === 'up') {
    summary = `Up ${overall.delta} points since attempt ${first.attempt}. Keep going!`
  } else if (overall.direction === 'down') {
    summary = `Down ${Math.abs(overall.delta)} points since attempt ${first.attempt}. Revisit the practice steps.`
  } else {
    summary = `Holding steady since attempt ${first.attempt}.`
  }

  const rows = [...attempts].reverse()

  return (
    <section aria-label="Attempt history" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
            Attempt History
          </h2>
          <p className="mt-1.5 text-[0.82rem] leading-snug text-brown-500">{summary}</p>
        </div>

        {attempts.length > 1 && (
          <span
            className={cn(
              'flex shrink-0 items-center gap-1.5 rounded-pill border px-2.5 py-1.5 text-[0.78rem] font-medium leading-none',
              overall.direction === 'up' && 'border-sage-200 bg-sage-50 text-sage-600',
              overall.direction === 'down' && 'border-blush-300 bg-blush-100 text-status-bad',
              overall.direction === 'flat' && 'border-gold-100 bg-ivory-100 text-brown-600'
            )}
          >
            <OverallIcon className="h-3.5 w-3.5" strokeWidth={2.2} aria-hidden="true" />
            {overall.direction === 'flat' ? '0' : overall.delta > 0 ? `+${overall.delta}` : overall.delta}
          </span>
        )}
      </div>

      {/* Chart */}
      <div className="mt-4 rounded-xl border border-gold-100/70 bg-gradient-to-b from-ivory-100/60 to-blush-50/60 px-2 pb-2 pt-1">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full"
          role="img"
          aria-label={`Scores by attempt: ${attempts.map((a) => `attempt ${a.attempt}, ${Math.round(a.score)}`).join('; ')}`}
        >
          <defs>
            <linearGradient id="attempt-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#5F7F55" stopOpacity="0.22" />
              <stop offset="1" stopColor="#5F7F55" stopOpacity="0" />
            </linearGradient>
          </defs>

          <line
            x1={PAD_X}
            x2={W - PAD_X}
            y1={H - PAD_BOTTOM}
            y2={H - PAD_BOTTOM}
            stroke="#E2C0A6"
            strokeOpacity="0.6"
          />

          {points.length > 1 && <path d={area} fill="url(#attempt-area)" />}
          {points.length > 1 && (
            <path d={line} fill="none" stroke="#5F7F55" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          )}

          {points.map((p, i) => {
            const isLast = i === points.length - 1
            return (
              <g key={p.attempt}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={isLast ? 5 : 3.6}
                  fill={isLast ? lastTone.hex : '#FDFAF4'}
                  stroke={isLast ? '#FDFAF4' : '#5F7F55'}
                  strokeWidth={isLast ? 2 : 2}
                />
                <text
                  x={p.x}
                  y={p.y - 10}
                  textAnchor="middle"
                  fontSize="11"
                  fontWeight={isLast ? 700 : 500}
                  fill="#5E3720"
                >
                  {Math.round(p.score)}
                </text>
                <text x={p.x} y={H - 3} textAnchor="middle" fontSize="9" fill="#AE7549">
                  {`#${p.attempt}`}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {/* List, newest first */}
      <ul className="mt-3 flex flex-col gap-1.5">
        {rows.map((a, idx) => {
          const prev = rows[idx + 1]
          const trend = prev ? getTrend(prev.score, a.score) : null
          const tone = TONE_STYLES[getScoreBand(a.score).tone]
          const date = formatDate(a.date)

          return (
            <li
              key={a.attempt}
              className={cn(
                'flex items-center gap-3 rounded-xl border px-3 py-2',
                idx === 0 ? 'border-gold-200 bg-blush-50/70' : 'border-gold-100/70 bg-ivory-50/70'
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block text-[0.88rem] font-medium leading-tight text-brown-800">
                  Attempt {a.attempt}
                  {idx === 0 && attempts.length > 1 && (
                    <span className="ml-2 rounded-pill bg-gold-100 px-1.5 py-0.5 text-[0.62rem] font-semibold uppercase tracking-wide text-brown-600">
                      Latest
                    </span>
                  )}
                </span>
                {date && <span className="mt-0.5 block text-[0.72rem] leading-none text-brown-500">{date}</span>}
              </span>

              {trend && trend.direction !== 'flat' && (
                <span
                  className={cn(
                    'flex items-center gap-0.5 text-[0.74rem] tabular-nums',
                    trend.direction === 'up' ? 'text-sage-600' : 'text-status-bad'
                  )}
                >
                  {trend.direction === 'up' ? (
                    <TrendingUp className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                  ) : (
                    <TrendingDown className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                  )}
                  {trend.direction === 'up' ? `+${trend.delta}` : trend.delta}
                </span>
              )}

              <span className={cn('w-9 text-right font-serif text-[1.25rem] font-semibold leading-none tabular-nums', tone.text)}>
                {Math.round(a.score)}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
