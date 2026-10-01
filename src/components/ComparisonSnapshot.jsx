import { cn } from '@/utils/cn'
import { formatCents, formatSigned, formatTime } from '@/utils/formatters'
import { getSnapshotIcon } from '@/utils/metricConfig'

/**
 * The "Comparison Snapshot" card on the Report.
 *
 *   Comparison Snapshot
 *                         [ Original ] [ Your Voice ]
 *   Average Pitch              F#          F#
 *   Tempo (BPM)                82          84
 *   Duration                 04:21       04:18
 *   Pitch Deviation             -         +12c
 *
 * Props:
 *   rows   analysis.snapshot:
 *          [{ id, label, format, original, user, difference }]
 *          format: 'text' | 'number' | 'time' | 'cents' | 'score' | 'ms'
 *   showDifference   adds a Difference column (roomier layouts)
 *
 * Only the rows the analysis returned are drawn. A row with neither an
 * original nor a user value is skipped. A value that does not apply
 * (for example the original's pitch deviation) shows a dash.
 */

const DASH = '\u2014'

/** Turns a raw value into display text, using the row's `format`. */
function formatValue(value, format) {
  if (value === null || value === undefined || value === '') return DASH

  switch (format) {
    case 'time':
      return Number.isFinite(Number(value)) ? formatTime(value) : DASH
    case 'cents':
      return Number.isFinite(Number(value)) ? formatCents(value) : DASH
    case 'score':
      return Number.isFinite(Number(value)) ? `${Math.round(Number(value))}/100` : DASH
    case 'ms':
      return Number.isFinite(Number(value)) ? `${formatSigned(value)} ms` : DASH
    case 'number':
      return Number.isFinite(Number(value)) ? String(Math.round(Number(value) * 10) / 10) : DASH
    default:
      return String(value)
  }
}

/** Difference text, e.g. "+2", "-3", "+5 s". Missing differences show a dash. */
function formatDifference(row) {
  const d = row.difference
  if (d === null || d === undefined || !Number.isFinite(Number(d))) return DASH
  if (row.format === 'time') return `${formatSigned(d)} s`
  if (row.format === 'cents') return formatCents(d)
  if (row.format === 'ms') return `${formatSigned(d)} ms`
  return formatSigned(d)
}

function hasValue(v) {
  return v !== null && v !== undefined && v !== ''
}

export default function ComparisonSnapshot({ rows, showDifference = false, className }) {
  const items = (Array.isArray(rows) ? rows : []).filter(
    (r) => r && r.label && (hasValue(r.original) || hasValue(r.user))
  )

  // Nothing returned, so no empty card.
  if (items.length === 0) return null

  const cols = showDifference
    ? 'grid-cols-[minmax(0,1.5fr)_1fr_1fr_0.8fr]'
    : 'grid-cols-[minmax(0,1.5fr)_1fr_1fr]'

  return (
    <section aria-label="Comparison snapshot" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
        Comparison Snapshot
      </h2>

      <div role="table" aria-label="Original compared with your voice" className="mt-3.5">
        {/* Column heads */}
        <div role="row" className={cn('grid items-center gap-1.5', cols)}>
          <span role="columnheader" className="sr-only">
            Measure
          </span>
          <span
            role="columnheader"
            className="rounded-lg bg-brown-500 px-1 py-1.5 text-center text-[0.74rem] font-medium leading-none text-ivory-50 sm:text-[0.8rem]"
          >
            Original
          </span>
          <span
            role="columnheader"
            className="rounded-lg bg-brown-50 px-1 py-1.5 text-center text-[0.74rem] font-medium leading-none text-brown-600 sm:text-[0.8rem]"
          >
            Your Voice
          </span>
          {showDifference && (
            <span
              role="columnheader"
              className="px-1 py-1.5 text-center text-[0.74rem] font-medium leading-none text-brown-500 sm:text-[0.8rem]"
            >
              Difference
            </span>
          )}
        </div>

        {/* Rows */}
        {items.map((row, i) => {
          const Icon = getSnapshotIcon(row.id)
          return (
            <div
              key={`${row.id || row.label}-${i}`}
              role="row"
              className={cn(
                'grid items-center gap-1.5 py-2.5',
                cols,
                i < items.length - 1 && 'border-b border-gold-100/70'
              )}
            >
              <span role="rowheader" className="flex min-w-0 items-center gap-2 text-[0.78rem] text-brown-600 sm:text-[0.85rem]">
                <Icon className="h-4 w-4 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
                <span className="truncate" title={row.label}>
                  {row.label}
                </span>
              </span>

              <span role="cell" className="text-center text-[0.85rem] font-medium tabular-nums text-brown-800 sm:text-[0.92rem]">
                {formatValue(row.original, row.format)}
              </span>
              <span role="cell" className="text-center text-[0.85rem] font-medium tabular-nums text-brown-800 sm:text-[0.92rem]">
                {formatValue(row.user, row.format)}
              </span>

              {showDifference && (
                <span role="cell" className="text-center text-[0.8rem] tabular-nums text-brown-500">
                  {formatDifference(row)}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
