import { AlertCircle, Pause, Play, User } from 'lucide-react'

import useAudioPlayer from '@/hooks/useAudioPlayer'
import { cn } from '@/utils/cn'
import { formatTime } from '@/utils/formatters'

/**
 * One audio row on the Report: thumbnail, name, play button, waveform, time.
 *
 *   [ art ]  Original      ( play )  ||||||||||||||||||||  00:00 / 04:21
 *            Yograj Bhat
 *
 * Used twice by AudioComparison: "Original" (brown waveform) and
 * "Your Voice" (blue waveform).
 *
 * Props:
 *   label, subtitle   text beside the thumbnail
 *   artwork           { gradient: [c1, c2, c3], motif } for a song tile
 *   avatarUrl         shown instead when there is no artwork (the singer)
 *   waveform          array of peaks, 0 to 1, from the analysis data
 *   duration          seconds, from the analysis data
 *   src               playable URL (real upload or recording), or null
 *   tone              'brown' | 'blue': colour of the played part
 *
 * With no `src` (the mock songs) useAudioPlayer simulates playback from
 * `duration`, so the controls still work. Nothing here is hardcoded.
 */

const BAR_COUNT = 44

const TONES = {
  brown: { played: '#A0623A', rest: '#EBD9C6' },
  blue: { played: '#2F7186', rest: '#CCE1E7' },
}

/** Averages a long peak array down to `count` bars. Empty input gives flat bars. */
function resample(peaks, count) {
  if (!Array.isArray(peaks) || peaks.length === 0) {
    return Array.from({ length: count }, () => 0.18)
  }
  if (peaks.length <= count) return peaks
  const size = peaks.length / count
  return Array.from({ length: count }, (_, i) => {
    const from = Math.floor(i * size)
    const to = Math.max(from + 1, Math.floor((i + 1) * size))
    const slice = peaks.slice(from, to)
    return slice.reduce((s, v) => s + v, 0) / slice.length
  })
}

/** Small drawings laid over the gradient tile, chosen by `artwork.motif`. */
function Motif({ motif }) {
  const common = { viewBox: '0 0 48 48', className: 'absolute inset-0 h-full w-full', 'aria-hidden': true }

  if (motif === 'lamp') {
    return (
      <svg {...common}>
        <ellipse cx="24" cy="36" rx="12" ry="4" fill="#45291A" opacity="0.35" />
        <path d="M14 33 C16 40 32 40 34 33 Z" fill="#7A4726" opacity="0.85" />
        <path d="M24 12 C29 19 28 26 24 30 C20 26 19 19 24 12 Z" fill="#FFF3C9" opacity="0.95" />
      </svg>
    )
  }
  if (motif === 'temple') {
    return (
      <svg {...common}>
        <path d="M6 40 H42 V36 H6 Z" fill="#45291A" opacity="0.4" />
        <path d="M14 36 V26 H34 V36 Z" fill="#45291A" opacity="0.35" />
        <path d="M18 26 C18 18 30 18 30 26 Z" fill="#45291A" opacity="0.35" />
        <path d="M24 12 V19" stroke="#FFF3C9" strokeWidth="1.5" opacity="0.9" />
      </svg>
    )
  }
  // 'mountains' (also the fallback)
  return (
    <svg {...common}>
      <circle cx="34" cy="16" r="5" fill="#FFE9B8" opacity="0.9" />
      <path d="M0 40 L14 20 L24 32 L33 22 L48 40 Z" fill="#2B3550" opacity="0.65" />
      <path d="M0 44 L12 32 L22 40 L34 30 L48 44 Z" fill="#1F2840" opacity="0.7" />
    </svg>
  )
}

function Thumb({ artwork, avatarUrl }) {
  const box = 'relative h-12 w-12 shrink-0 overflow-hidden rounded-xl shadow-soft sm:h-14 sm:w-14'

  if (artwork) {
    const [a, b, c] = artwork.gradient || ['#F3D9A4', '#C99A5B', '#7A4726']
    return (
      <span className={box} style={{ background: `linear-gradient(165deg, ${a} 0%, ${b} 55%, ${c ?? b} 100%)` }}>
        <Motif motif={artwork.motif} />
      </span>
    )
  }

  return (
    <span className={cn(box, 'flex items-center justify-center bg-sage-100 text-sage-500')}>
      {avatarUrl ? (
        <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        <User className="h-6 w-6 sm:h-7 sm:w-7" strokeWidth={2} aria-hidden="true" />
      )}
    </span>
  )
}

export default function AudioPlayer({
  label,
  subtitle,
  artwork,
  avatarUrl,
  waveform,
  duration = 0,
  src = null,
  tone = 'brown',
  className,
}) {
  const player = useAudioPlayer({ src, duration })
  const colors = TONES[tone] || TONES.brown

  const bars = resample(waveform, BAR_COUNT)
  const total = player.duration
  const canPlay = (src || total > 0) && !player.error
  const playedBars = Math.round((player.progress / 100) * bars.length)

  return (
    <div
      className={cn(
        'grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2.5',
        'min-[400px]:grid-cols-[auto_minmax(0,6.5rem)_auto_minmax(0,1fr)_auto] sm:grid-cols-[auto_minmax(0,8rem)_auto_minmax(0,1fr)_auto]',
        className
      )}
    >
      <Thumb artwork={artwork} avatarUrl={avatarUrl} />

      <div className="min-w-0">
        <p className="truncate font-serif text-[1.15rem] font-semibold leading-none text-brown-900 sm:text-[1.3rem]">
          {label}
        </p>
        {subtitle && <p className="mt-1.5 truncate text-[0.78rem] leading-none text-brown-500">{subtitle}</p>}
      </div>

      <button
        type="button"
        onClick={player.toggle}
        disabled={!canPlay}
        aria-label={`${player.isPlaying ? 'Pause' : 'Play'} ${label}`}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-blush-200/70 bg-blush-100 text-brown-500 shadow-soft transition-all hover:bg-blush-200 active:scale-95 disabled:opacity-50 sm:h-12 sm:w-12"
      >
        {player.isPlaying ? (
          <Pause className="h-[1.1rem] w-[1.1rem] fill-current" strokeWidth={2} aria-hidden="true" />
        ) : (
          <Play className="ml-0.5 h-[1.1rem] w-[1.1rem] fill-current" strokeWidth={2} aria-hidden="true" />
        )}
      </button>

      {/* Waveform + invisible scrubber on top of it */}
      <div className="relative col-span-2 h-9 min-[400px]:col-span-1 focus-within:rounded-md focus-within:ring-2 focus-within:ring-gold-400/70">
        <div className="flex h-full items-center gap-[2px]" aria-hidden="true">
          {bars.map((peak, i) => (
            <span
              key={i}
              className="min-w-[2px] flex-1 rounded-full transition-colors duration-150"
              style={{
                height: `${Math.max(12, peak * 100)}%`,
                backgroundColor: i < playedBars ? colors.played : colors.rest,
              }}
            />
          ))}
        </div>

        <input
          type="range"
          min={0}
          max={total > 0 ? total : 1}
          step={0.1}
          value={Math.min(player.currentTime, total > 0 ? total : 1)}
          onChange={(e) => player.seek(Number(e.target.value))}
          disabled={!canPlay}
          aria-label={`Seek ${label}`}
          aria-valuetext={`${formatTime(player.currentTime)} of ${formatTime(total)}`}
          className="nm-range absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        />
      </div>

      {/* Unknown length is hidden, never shown as 00:00 */}
      <span className="whitespace-nowrap text-right text-[0.72rem] tabular-nums leading-none text-brown-500 max-[399px]:hidden sm:text-[0.78rem]">
        {total > 0 ? `${formatTime(player.currentTime)} / ${formatTime(total)}` : formatTime(player.currentTime)}
      </span>

      {player.error && (
        <p role="alert" className="col-span-full flex items-center gap-1.5 text-[0.78rem] text-status-bad">
          <AlertCircle className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
          {player.error === 'unsupported'
            ? 'This browser cannot play this audio.'
            : 'Playback was blocked. Tap play to try again.'}
        </p>
      )}
    </div>
  )
}
