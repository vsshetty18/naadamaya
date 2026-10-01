import AudioPlayer from '@/components/AudioPlayer'
import { cn } from '@/utils/cn'
import { formatDate } from '@/utils/formatters'

/**
 * The top card of the Report: the Original and Your Voice players together.
 *
 *   [ art ]  Original      ( play )  ||||||||||||  00:00 / 04:21
 *            Yograj Bhat
 *   ------------------------------------------------------------
 *   [ you ]  Your Voice    ( play )  ||||||||||||  00:00 / 04:18
 *            Recorded . 28 Sep 2026
 *
 * Props:
 *   analysis   the analysis object (see mockAnalysisData for the shape)
 *
 * Every value is read from `analysis`. Nothing is hardcoded, so a different
 * song gives a different title, artist, duration, waveform and artwork.
 * Optional fields that are missing are simply left out.
 */

export default function AudioComparison({ analysis, className }) {
  if (!analysis?.original || !analysis?.user) return null

  const { original, user } = analysis
  const recordedOn = formatDate(user.recordedAt)

  return (
    <section
      aria-label="Audio comparison"
      className={cn('nm-card animate-fade-up p-3.5 sm:p-5', className)}
    >
      <AudioPlayer
        label="Original"
        subtitle={[original.title, original.artist].filter(Boolean).join(' \u00B7 ')}
        artwork={original.artwork}
        waveform={original.waveform}
        duration={original.duration}
        src={original.audioUrl}
        tone="brown"
      />

      <div className="nm-divider my-3.5 sm:my-4" />

      <AudioPlayer
        label="Your Voice"
        subtitle={recordedOn ? `Recorded \u00B7 ${recordedOn}` : 'Your recording'}
        avatarUrl={user.avatarUrl}
        waveform={user.waveform}
        duration={user.duration}
        src={user.audioUrl}
        tone="blue"
      />
    </section>
  )
}
