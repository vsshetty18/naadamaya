import { useMemo, useRef, useState } from 'react'

import { cn } from '@/utils/cn'
import { clamp, formatCents, formatTime } from '@/utils/formatters'

/**
 * Interactive pitch graph: Original vs Your Voice.
 *
 * Props:
 *   data   analysis.pitchComparison:
 *          { axis, originalPitchData, userPitchData, annotations, stats }
 *          axis        [{ label, value }]  note names for the left edge
 *          *PitchData  [{ t (seconds), v (semitones above Sa) }]
 *
 * Everything drawn comes from `data`. Nothing is a fixed line. Hover, touch
 * or arrow keys read out the time, the note, and how far you were from the
 * original. Shaded bands mark where you went sharp, flat or unstable.
 * Missing or too-short data renders nothing (no empty card).
 */

const W = 600
const H = 200
const MAX_POINTS = 160
const ON_PITCH_CENTS = 25

const COLORS = { original: '#A0623A', user: '#2F7186' }

const ISSUE = {
  sharp: { label: 'Sharp', color: '#C4574F' },
  flat: { label: 'Flat', color: '#8A6BB0' },
  unstable: { label: 'Unstable', color: '#C0892F' },
}

/** Smooth SVG path through the points (midpoint quadratic curves). */
function buildPath(points, toX, toY) {
  if (points.length === 0) return ''
  const step = Math.max(1, Math.ceil(points.length / MAX_POINTS))
  const pts = points.filter((_, i) => i % step === 0 || i === points.length - 1)
  const xy = pts.map((p) => [toX(p.t), toY(p.v)])
  if (xy.length < 3) return xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x} ${y}`).join(' ')

  let d = `M${xy[0][0]} ${xy[0][1]}`
  for (let i = 1; i < xy.length - 1; i++) {
    const mx = (xy[i][0] + xy[i + 1][0]) / 2
    const my = (xy[i][1] + xy[i + 1][1]) / 2
    d += ` Q${xy[i][0]} ${xy[i][1]} ${mx} ${my}`
  }
  const last = xy[xy.length - 1]
  return `${d} L${last[0]} ${last[1]}`
}

/** Index of the point whose time is closest to t (arrays are sorted by t). */
function nearestIndex(points, t) {
  let lo = 0
  let hi = points.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (points[mid].t < t) lo = mid
    else hi = mid
  }
  return Math.abs(points[lo].t - t) <= Math.abs(points[hi].t - t) ? lo : hi
}

function nearestNote(axis = [], value) {
  if (!axis.length) return null
  return axis.reduce((best, n) => (Math.abs(n.value - value) < Math.abs(best.value - value) ? n : best)).label
}

export default function PitchComparison({ data, className }) {
  const plotRef = useRef(null)
  const [activeT, setActiveT] = useState(null)

  const original = data?.originalPitchData
  const user = data?.userPitchData
  const ready = Array.isArray(original) && Array.isArray(user) && original.length > 1 && user.length > 1

  const model = useMemo(() => {
    if (!ready) return null
    const axis = data.axis || []
    const values = [...original, ...user].map((p) => p.v).concat(axis.map((a) => a.value))
    const min = Math.min(...values) - 0.5
    const max = Math.max(...values) + 0.5
    const tMax = Math.max(original[original.length - 1].t, user[user.length - 1].t) || 1

    const toX = (t) => (t / tMax) * W
    const toY = (v) => H - ((v - min) / (max - min)) * H
    const pct = (v) => ((v - min) / (max - min)) * 100

    return {
      axis,
      min,
      max,
      tMax,
      pct,
      originalPath: buildPath(original, toX, toY),
      userPath: buildPath(user, toX, toY),
      gridY: axis.map((a) => toY(a.value)),
    }
  }, [ready, data, original, user])

  if (!ready || !model) return null

  const { axis, tMax, pct } = model
  const annotations = Array.isArray(data.annotations) ? data.annotations : []
  const stats = data.stats

  const setFromEvent = (e) => {
    const rect = plotRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return
    setActiveT(clamp((e.clientX - rect.left) / rect.width, 0, 1) * tMax)
  }

  const onKeyDown = (e) => {
    const step = tMax / 60
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      setActiveT((t) => clamp((t ?? 0) + step, 0, tMax))
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      setActiveT((t) => clamp((t ?? tMax) - step, 0, tMax))
    } else if (e.key === 'Escape') {
      setActiveT(null)
    }
  }

  /* ---------- readout for the active moment ---------- */
  let readout = null
  if (activeT !== null) {
    const o = original[nearestIndex(original, activeT)]
    const u = user[nearestIndex(user, activeT)]
    const cents = Math.round((u.v - o.v) * 100)
    const state = cents >= ON_PITCH_CENTS ? 'sharp' : cents <= -ON_PITCH_CENTS ? 'flat' : 'on'
    const note = annotations.find((a) => activeT >= a.startTime && activeT <= a.endTime)
    readout = { o, u, cents, state, note, frac: activeT / tMax }
  }

  const tooltipShift = readout ? (readout.frac < 0.22 ? '0%' : readout.frac > 0.78 ? '-100%' : '-50%') : '0%'

  return (
    <section aria-label="Pitch comparison" className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}>
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div>
          <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
            Pitch Comparison
          </h2>
          <p className="mt-1.5 text-[0.82rem] leading-snug text-brown-500">
            See how your pitch matched with the original.
          </p>
        </div>

        <ul className="flex items-center gap-4 pt-1 text-[0.8rem] text-brown-600">
          <li className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: COLORS.original }} />
            Original
          </li>
          <li className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: COLORS.user }} />
            Your Voice
          </li>
        </ul>
      </div>

      {/* Graph */}
      <div className="mt-4 flex gap-2">
        {/* Note names */}
        <div className="relative h-52 w-8 shrink-0 md:h-64" aria-hidden="true">
          {axis.map((a) => (
            <span
              key={`${a.label}-${a.value}`}
              className="absolute right-0 -translate-y-1/2 text-[0.68rem] leading-none text-brown-500"
              style={{ bottom: `${pct(a.value)}%`, transform: 'translateY(50%)' }}
            >
              {a.label}
            </span>
          ))}
        </div>

        {/* Plot */}
        <div className="min-w-0 flex-1">
          <div
            ref={plotRef}
            tabIndex={0}
            role="img"
            aria-label={
              readout
                ? `At ${formatTime(activeT)}: your pitch is ${formatCents(readout.cents)} from the original`
                : 'Pitch graph. Use the left and right arrow keys to explore.'
            }
            onPointerMove={setFromEvent}
            onPointerDown={setFromEvent}
            onPointerLeave={(e) => e.pointerType === 'mouse' && setActiveT(null)}
            onKeyDown={onKeyDown}
            className="relative h-52 touch-pan-y overflow-hidden rounded-xl border border-gold-100/70 bg-gradient-to-b from-ivory-100/60 to-blush-50/60 md:h-64"
          >
            {/* Sharp / flat / unstable bands */}
            {annotations.map((a, i) => {
              const issue = ISSUE[a.type] || ISSUE.unstable
              return (
                <div
                  key={`${a.startTime}-${i}`}
                  className="pointer-events-none absolute inset-y-0"
                  style={{
                    left: `${(a.startTime / tMax) * 100}%`,
                    width: `${((a.endTime - a.startTime) / tMax) * 100}%`,
                    backgroundColor: issue.color,
                    opacity: 0.12,
                  }}
                />
              )
            })}

            <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden="true">
              {model.gridY.map((y, i) => (
                <line
                  key={i}
                  x1="0"
                  x2={W}
                  y1={y}
                  y2={y}
                  stroke="#E2C0A6"
                  strokeOpacity="0.45"
                  strokeDasharray="3 5"
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              <path
                d={model.originalPath}
                fill="none"
                stroke={COLORS.original}
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
              <path
                d={model.userPath}
                fill="none"
                stroke={COLORS.user}
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            </svg>

            {/* Cursor, dots and tooltip */}
            {readout && (
              <>
                <div
                  className="pointer-events-none absolute inset-y-0 w-px bg-brown-400/50"
                  style={{ left: `${readout.frac * 100}%` }}
                />
                <span
                  className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 translate-y-1/2 rounded-full border-2 border-ivory-50 shadow-soft"
                  style={{ left: `${readout.frac * 100}%`, bottom: `${pct(readout.o.v)}%`, backgroundColor: COLORS.original }}
                />
                <span
                  className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 translate-y-1/2 rounded-full border-2 border-ivory-50 shadow-soft"
                  style={{ left: `${readout.frac * 100}%`, bottom: `${pct(readout.u.v)}%`, backgroundColor: COLORS.user }}
                />

                <div
                  className="pointer-events-none absolute top-1.5 z-10 w-max max-w-[13rem] rounded-xl border border-gold-100 bg-ivory-50/95 px-3 py-2 shadow-card backdrop-blur-sm"
                  style={{ left: `${readout.frac * 100}%`, transform: `translateX(${tooltipShift})` }}
                >
                  <p className="text-[0.72rem] font-medium tabular-nums leading-none text-brown-500">
                    {formatTime(activeT)}
                  </p>
                  <p className="mt-1.5 text-[0.82rem] font-semibold leading-tight text-brown-900">
                    {readout.state === 'on'
                      ? 'On pitch'
                      : `${ISSUE[readout.state].label} ${formatCents(Math.abs(readout.cents)).replace('+', '')}`}
                  </p>
                  <p className="mt-1 text-[0.72rem] leading-tight text-brown-500">
                    Original near {nearestNote(axis, readout.o.v) || '\u2014'}
                  </p>
                  {readout.note?.label && (
                    <p className="mt-1 text-[0.72rem] leading-tight" style={{ color: (ISSUE[readout.note.type] || ISSUE.unstable).color }}>
                      {readout.note.label}
                    </p>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Time axis */}
          <div className="mt-1.5 flex justify-between text-[0.68rem] tabular-nums leading-none text-brown-400" aria-hidden="true">
            <span>{formatTime(0)}</span>
            <span>{formatTime(tMax / 2)}</span>
            <span>{formatTime(tMax)}</span>
          </div>
        </div>
      </div>

      {/* Summary */}
      {stats && (
        <ul className="mt-4 grid grid-cols-3 gap-2">
          {[
            { key: 'matchedPercent', label: 'Matched', color: '#5F7F55' },
            { key: 'sharpPercent', label: 'Sharp', color: ISSUE.sharp.color },
            { key: 'flatPercent', label: 'Flat', color: ISSUE.flat.color },
          ]
            .filter((s) => Number.isFinite(Number(stats[s.key])))
            .map((s) => (
              <li key={s.key} className="rounded-xl border border-gold-100/70 bg-ivory-50/80 px-2.5 py-2 text-center">
                <p className="font-serif text-[1.2rem] font-semibold leading-none tabular-nums" style={{ color: s.color }}>
                  {Math.round(stats[s.key])}%
                </p>
                <p className="mt-1 text-[0.72rem] leading-none text-brown-500">{s.label}</p>
              </li>
            ))}
        </ul>
      )}

      {/* Where it deviated */}
      {annotations.length > 0 && (
        <div className="mt-4">
          <p className="nm-eyebrow">Where it deviated</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {annotations.map((a, i) => {
              const issue = ISSUE[a.type] || ISSUE.unstable
              return (
                <li key={`${a.startTime}-${i}`}>
                  <button
                    type="button"
                    onClick={() => setActiveT((a.startTime + a.endTime) / 2)}
                    className="flex w-full items-center gap-2.5 rounded-xl border border-gold-100/70 bg-ivory-50/70 px-3 py-2 text-left transition-colors hover:bg-blush-50"
                  >
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: issue.color }} aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate text-[0.82rem] text-brown-800">
                      {a.label || issue.label}
                    </span>
                    <span className="shrink-0 text-[0.72rem] tabular-nums text-brown-500">
                      {formatTime(a.startTime)}{'\u2013'}{formatTime(a.endTime)}
                      {Number.isFinite(Number(a.cents)) && a.cents !== 0 ? ` \u00B7 ${formatCents(a.cents)}` : ''}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </section>
  )
}
