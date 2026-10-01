import { useEffect, useState } from 'react'
import { Sparkles } from 'lucide-react'

import Badge from '@/components/Badge'
import { cn } from '@/utils/cn'
import { clamp } from '@/utils/formatters'
import { getScoreStatus } from '@/utils/scoreHelpers'

/**
 * The left block of the "Overall Score" card on the Report:
 *
 *   Overall Score
 *   How close your singing is to the original.
 *        ( ring with 78 /100 )
 *        [ sparkle  Good Job! ]
 *
 * Props:
 *   score          0 to 100, from analysis.overallScore
 *   statusLabel    optional wording from the backend (analysis.statusLabel).
 *                  When missing, the label is derived from the score.
 *   summary        optional sentence under the pill (analysis.summary)
 *   size           ring diameter in px (default 144)
 *
 * It draws a block, not a card. The Report page puts it in the same rounded
 * card as the metric cards, like your reference. Nothing is hardcoded:
 * the number, the ring fill, the colour and the pill all follow `score`.
 */

const STROKE = 11
const VIEWBOX = 120
const RADIUS = (VIEWBOX - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export default function OverallScore({ score, statusLabel, summary, size = 144, className }) {
  const valid = score !== null && score !== undefined && Number.isFinite(Number(score))
  const value = valid ? clamp(score, 0, 100) : 0
  const status = getScoreStatus(value, statusLabel)

  // Start empty, then fill, so the ring sweeps in. A new score re-animates it.
  const [shown, setShown] = useState(0)
  useEffect(() => {
    setShown(0)
    const raf = requestAnimationFrame(() => setShown(value))
    return () => cancelAnimationFrame(raf)
  }, [value])

  const offset = CIRCUMFERENCE * (1 - shown / 100)

  return (
    <div className={cn('flex flex-col', className)}>
      <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
        Overall Score
      </h2>
      <p className="mt-1.5 max-w-[11rem] text-[0.82rem] leading-snug text-brown-500">
        How close your singing is to the original.
      </p>

      <div className="mt-3 flex flex-col items-center sm:items-start">
        <div
          role="img"
          aria-label={valid ? `Overall score ${Math.round(value)} out of 100` : 'Overall score unavailable'}
          className="relative shrink-0"
          style={{ width: size, height: size }}
        >
          <svg viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`} className="h-full w-full -rotate-90" aria-hidden="true">
            <circle
              cx={VIEWBOX / 2}
              cy={VIEWBOX / 2}
              r={RADIUS}
              fill="none"
              stroke={status.styles.track}
              strokeWidth={STROKE}
            />
            {valid && (
              <circle
                cx={VIEWBOX / 2}
                cy={VIEWBOX / 2}
                r={RADIUS}
                fill="none"
                stroke={status.styles.stroke}
                strokeWidth={STROKE}
                strokeLinecap="round"
                strokeDasharray={CIRCUMFERENCE}
                strokeDashoffset={offset}
                style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.22, 1, 0.36, 1)' }}
              />
            )}
          </svg>

          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-serif text-score font-semibold tabular-nums text-brown-900">
              {valid ? Math.round(value) : '\u2014'}
            </span>
            {valid && <span className="-mt-0.5 text-[0.82rem] text-brown-500">/100</span>}
          </div>
        </div>

        {valid && (
          <Badge variant={status.tone} icon={Sparkles} className="mt-3">
            {status.label}
          </Badge>
        )}

        {summary && (
          <p className="mt-3 max-w-[12rem] text-[0.8rem] leading-snug text-brown-500">{summary}</p>
        )}
      </div>
    </div>
  )
}
