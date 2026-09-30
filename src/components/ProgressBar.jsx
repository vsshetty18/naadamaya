import { cn } from '@/utils/cn'
import { clamp } from '@/utils/formatters'

/**
 * Horizontal progress bar.
 *
 * Used for:
 *   - metric score bars on the Report cards (colour comes from metricConfig)
 *   - the credit bar in the bottom navigation and on Credits
 *   - upload progress in the Upload modal
 *
 * Props:
 *   value      0 to 100 (clamped, bad input becomes 0)
 *   color      any CSS colour for the fill, e.g. from getMetricConfig(id).color
 *   track      any CSS colour for the empty part
 *   tone       'good' | 'warn' | 'bad' | 'brand': a preset used when no color is given
 *   size       'xs' | 'sm' | 'md' | 'lg'
 *   animate    grows from empty on first render
 *   label      accessible name, e.g. "Pitch Accuracy"
 *
 * It draws a bar. It never decides what the number means.
 */

const TONES = {
  good: { color: '#5F7F55', track: '#E3EBDD' },
  warn: { color: '#D9862F', track: '#F8E7DD' },
  bad: { color: '#C4574F', track: '#F8E7DD' },
  brand: { color: '#93582F', track: '#F0DDCF' },
}

const SIZES = {
  xs: 'h-1',
  sm: 'h-1.5',
  md: 'h-2',
  lg: 'h-3',
}

export default function ProgressBar({
  value = 0,
  color,
  track,
  tone = 'good',
  size = 'sm',
  animate = true,
  label,
  className,
  ...rest
}) {
  const pct = clamp(value, 0, 100)
  const preset = TONES[tone] || TONES.good

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-label={label}
      className={cn('w-full overflow-hidden rounded-full', SIZES[size] || SIZES.sm, className)}
      style={{ backgroundColor: track || preset.track }}
      {...rest}
    >
      <div
        className={cn('h-full origin-left rounded-full', animate && 'animate-bar-grow')}
        style={{
          width: `${pct}%`,
          backgroundColor: color || preset.color,
          transition: 'width 0.5s cubic-bezier(0.22, 1, 0.36, 1)',
        }}
      />
    </div>
  )
}
