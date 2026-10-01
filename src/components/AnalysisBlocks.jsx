import { AlertTriangle, CheckCircle2, Clock, Mic2, Wind, XCircle } from 'lucide-react'

import { cn } from '@/utils/cn'
import { clamp, formatSigned, formatTime } from '@/utils/formatters'

/**
 * The four optional analysis cards on the Report:
 *
 *   HowYouPerformed        analysis.performance          [{ type, text }]
 *   RhythmComparison       analysis.rhythmComparison     { unit, entries }
 *   PronunciationAnalysis  analysis.pronunciationAnalysis { items }
 *   BreathAnalysis         analysis.breathAnalysis       { phrases }
 *
 * Each one draws only what its data contains. With no usable data it
 * returns null, so the Report never shows an empty card. Nothing here is
 * hardcoded: every sentence, number and time range comes from the analysis.
 */

/* ==========================================================
   SHARED PIECES
   ========================================================== */

function CardHeader({ icon: Icon, title, subtitle }) {
  return (
    <div className="flex items-start gap-2.5">
      {Icon && <Icon className="mt-0.5 h-5 w-5 shrink-0 text-gold-500" strokeWidth={1.8} aria-hidden="true" />}
      <div>
        <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
          {title}
        </h2>
        {subtitle && <p className="mt-1.5 text-[0.82rem] leading-snug text-brown-500">{subtitle}</p>}
      </div>
    </div>
  )
}

const TONES = {
  good: { bar: '#84A075', text: 'text-sage-600', dot: 'bg-sage-500' },
  warn: { bar: '#E3A55C', text: 'text-status-warn', dot: 'bg-status-warn' },
  bad: { bar: '#D98079', text: 'text-status-bad', dot: 'bg-status-bad' },
  neutral: { bar: '#CCE1E7', text: 'text-brown-500', dot: 'bg-brown-300' },
}

const isNum = (v) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v))

/** Thin strip showing WHERE in the song each range sits. */
function RangeStrip({ ranges, total }) {
  return (
    <div className="relative h-3 overflow-hidden rounded-full bg-ivory-200" aria-hidden="true">
      {ranges.map((r, i) => (
        <span
          key={i}
          className="absolute inset-y-0 rounded-full"
          style={{
            left: `${clamp((r.start / total) * 100, 0, 100)}%`,
            width: `${clamp(((r.end - r.start) / total) * 100, 1.5, 100)}%`,
            backgroundColor: TONES[r.tone].bar,
          }}
        />
      ))}
    </div>
  )
}

/**
 * Shared body for the two "ranges with a status and a note" cards.
 * `toneFor` maps the backend's status word to good / warn / bad.
 */
function RangeList({ rows, duration }) {
  const lastEnd = Math.max(...rows.map((r) => r.end))
  const total = Math.max(Number(duration) || 0, lastEnd, 1)

  return (
    <>
      <div className="mt-4">
        <RangeStrip ranges={rows} total={total} />
        <div className="mt-1.5 flex justify-between text-[0.68rem] tabular-nums leading-none text-brown-400" aria-hidden="true">
          <span>{formatTime(0)}</span>
          <span>{formatTime(total)}</span>
        </div>
      </div>

      <ul className="mt-3 flex flex-col gap-2">
        {rows.map((r, i) => (
          <li
            key={`${r.start}-${i}`}
            className="flex items-start gap-2.5 rounded-xl border border-gold-100/70 bg-ivory-50/70 px-3 py-2.5"
          >
            <span className={cn('mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full', TONES[r.tone].dot)} aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className={cn('text-[0.85rem] font-semibold capitalize leading-tight', TONES[r.tone].text)}>
                  {r.status}
                </span>
                <span className="text-[0.72rem] tabular-nums text-brown-500">
                  {formatTime(r.start)}
                  {'\u2013'}
                  {formatTime(r.end)}
                </span>
              </span>
              {r.note && <span className="mt-1 block text-[0.8rem] leading-snug text-brown-600">{r.note}</span>}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}

/** Cleans and sorts raw ranges, then adds a tone from a status map. */
function prepareRanges(list, toneMap) {
  return (Array.isArray(list) ? list : [])
    .filter((r) => r && isNum(r.startTime) && isNum(r.endTime))
    .map((r) => ({
      start: Number(r.startTime),
      end: Math.max(Number(r.endTime), Number(r.startTime)),
      status: r.status ? String(r.status).replace(/_/g, ' ') : 'noted',
      note: r.note,
      tone: toneMap[r.status] || 'neutral',
    }))
    .sort((a, b) => a.start - b.start)
}

/* ==========================================================
   HOW YOU PERFORMED
   ========================================================== */

const PERFORMANCE_TYPES = {
  positive: { Icon: CheckCircle2, text: 'text-sage-600', bg: 'bg-sage-50', border: 'border-sage-100' },
  improvement: { Icon: AlertTriangle, text: 'text-status-warn', bg: 'bg-blush-50', border: 'border-blush-100' },
  issue: { Icon: XCircle, text: 'text-status-bad', bg: 'bg-blush-100', border: 'border-blush-200' },
}

export function HowYouPerformed({ items, className }) {
  const list = (Array.isArray(items) ? items : []).filter((i) => i && i.text)
  if (list.length === 0) return null

  return (
    <section aria-label="How you performed" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <CardHeader title="How You Performed" subtitle="What was evaluated in this song." />

      <ul className="mt-3.5 flex flex-col gap-2">
        {list.map((item, i) => {
          const style = PERFORMANCE_TYPES[item.type] || PERFORMANCE_TYPES.improvement
          const Icon = style.Icon
          return (
            <li
              key={`${item.text}-${i}`}
              className={cn('flex items-start gap-2.5 rounded-xl border px-3 py-2.5', style.bg, style.border)}
            >
              <Icon className={cn('mt-0.5 h-[1.1rem] w-[1.1rem] shrink-0', style.text)} strokeWidth={2} aria-hidden="true" />
              <span className="text-[0.85rem] leading-snug text-brown-800">{item.text}</span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/* ==========================================================
   RHYTHM COMPARISON
   ========================================================== */

// Display thresholds only. The engine's own verdict would come from the data.
const ON_TIME_MS = 50
const OFF_MS = 120

function offsetTone(ms) {
  const a = Math.abs(ms)
  if (a <= ON_TIME_MS) return 'good'
  if (a <= OFF_MS) return 'warn'
  return 'bad'
}

export function RhythmComparison({ data, className }) {
  const unit = data?.unit || 'ms'
  const entries = (Array.isArray(data?.entries) ? data.entries : [])
    .filter((e) => e && e.label && isNum(e.offsetMs))
    .map((e) => ({ ...e, offset: Number(e.offsetMs), tone: offsetTone(Number(e.offsetMs)) }))

  if (entries.length === 0) return null

  const scale = Math.max(100, ...entries.map((e) => Math.abs(e.offset)))
  const average = Math.round(entries.reduce((s, e) => s + e.offset, 0) / entries.length)
  const lateCount = entries.filter((e) => e.offset > ON_TIME_MS).length

  return (
    <section aria-label="Rhythm comparison" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <CardHeader
        icon={Clock}
        title="Rhythm Comparison"
        subtitle={
          lateCount === 0
            ? 'Your entries stayed close to the original.'
            : `${lateCount} of ${entries.length} ${entries.length === 1 ? 'part' : 'parts'} entered noticeably late.`
        }
      />

      <div className="mt-4 flex justify-between text-[0.68rem] font-medium uppercase tracking-wide text-brown-400" aria-hidden="true">
        <span>Early</span>
        <span>On time</span>
        <span>Late</span>
      </div>

      <ul className="mt-1.5 flex flex-col gap-2.5">
        {entries.map((e, i) => {
          const widthPct = clamp((Math.abs(e.offset) / scale) * 50, 1, 50)
          const late = e.offset > 0
          return (
            <li key={`${e.label}-${i}`}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 truncate text-[0.82rem] text-brown-800">{e.label}</span>
                <span className={cn('shrink-0 text-[0.78rem] font-medium tabular-nums', TONES[e.tone].text)}>
                  {formatSigned(e.offset)} {unit}
                </span>
              </div>
              <div
                className="relative mt-1 h-2 rounded-full bg-ivory-200"
                role="img"
                aria-label={`${e.label}: ${Math.abs(e.offset)} ${unit} ${e.offset === 0 ? 'on time' : late ? 'late' : 'early'}`}
              >
                <span className="absolute inset-y-[-2px] left-1/2 w-px bg-brown-300" aria-hidden="true" />
                <span
                  className="absolute inset-y-0 rounded-full"
                  style={{
                    width: `${widthPct}%`,
                    [late ? 'left' : 'right']: '50%',
                    backgroundColor: TONES[e.tone].bar,
                  }}
                />
              </div>
            </li>
          )
        })}
      </ul>

      <p className="mt-4 border-t border-gold-100 pt-3 text-[0.78rem] text-brown-500">
        Average timing offset: <span className="font-medium tabular-nums text-brown-800">{formatSigned(average)} {unit}</span>
      </p>
    </section>
  )
}

/* ==========================================================
   PRONUNCIATION ANALYSIS
   ========================================================== */

const PRONUNCIATION_TONES = { clear: 'good', unclear: 'warn', slurred: 'bad', rushed: 'warn' }

export function PronunciationAnalysis({ data, duration, className }) {
  const rows = prepareRanges(data?.items, PRONUNCIATION_TONES)
  if (rows.length === 0) return null

  const unclear = rows.filter((r) => r.tone !== 'good').length

  return (
    <section aria-label="Pronunciation analysis" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <CardHeader
        icon={Mic2}
        title="Pronunciation Analysis"
        subtitle={unclear === 0 ? 'Your words were clear throughout.' : 'Where your words were clear and where they blurred.'}
      />
      <RangeList rows={rows} duration={duration} />
    </section>
  )
}

/* ==========================================================
   BREATH CONTROL
   ========================================================== */

const BREATH_TONES = { steady: 'good', short: 'warn', strained: 'bad' }

export function BreathAnalysis({ data, duration, className }) {
  const rows = prepareRanges(data?.phrases, BREATH_TONES)
  if (rows.length === 0) return null

  const strained = rows.filter((r) => r.tone !== 'good').length

  return (
    <section aria-label="Breath control" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      <CardHeader
        icon={Wind}
        title="Breath Control"
        subtitle={strained === 0 ? 'Your breath support held up well.' : 'How your breath carried through the longer phrases.'}
      />
      <RangeList rows={rows} duration={duration} />
    </section>
  )
}
