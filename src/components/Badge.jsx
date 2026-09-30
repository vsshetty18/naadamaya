import { isValidElement } from 'react'

import { cn } from '@/utils/cn'

/**
 * Small pill for status, labels and tags.
 *
 * Variants:
 *   popular   solid brown tab, e.g. "Most Popular" on the Pro card
 *   good      sage, e.g. the "Good Job!" pill under the score ring
 *   warn      warm amber, e.g. "Needs Practice"
 *   bad       soft red, e.g. "Needs Improvement"
 *   gold      cream and gold, e.g. "Free Account", "Improved"
 *   mist      pale blue, e.g. "Melodic" song tags
 *   blush     pale peach
 *   neutral   quiet brown-on-ivory, the default
 *
 * Props:
 *   variant, size ('sm' | 'md')
 *   icon    a lucide component or a ready element, shown before the label
 *   dot     shows a small coloured dot instead of an icon
 *
 * It only draws a pill. Which label or tone to show comes from the caller
 * (for example getScoreStatus in scoreHelpers).
 */

const BASE =
  'inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill border font-sans font-medium leading-none'

const VARIANTS = {
  popular: 'border-transparent bg-brown-500 text-ivory-50 shadow-soft',
  good: 'border-sage-200 bg-sage-50 text-sage-600',
  warn: 'border-blush-200 bg-blush-50 text-status-warn',
  bad: 'border-blush-300 bg-blush-100 text-status-bad',
  gold: 'border-gold-200 bg-gold-50 text-brown-600',
  mist: 'border-mist-200 bg-mist-50 text-mist-500',
  blush: 'border-blush-200 bg-blush-50 text-brown-500',
  neutral: 'border-gold-100 bg-ivory-100 text-brown-600',
}

const DOT_COLORS = {
  popular: 'bg-ivory-50',
  good: 'bg-sage-500',
  warn: 'bg-status-warn',
  bad: 'bg-status-bad',
  gold: 'bg-gold-500',
  mist: 'bg-mist-500',
  blush: 'bg-brown-300',
  neutral: 'bg-brown-300',
}

const SIZES = {
  sm: 'px-2 py-1 text-[0.68rem]',
  md: 'px-3 py-1.5 text-[0.8rem]',
}

/** Accepts a lucide component (Sparkles) or a ready element (<Sparkles />). */
function renderIcon(icon, className) {
  if (!icon) return null
  if (isValidElement(icon)) return icon
  const Icon = icon
  return <Icon className={className} strokeWidth={2} aria-hidden="true" />
}

export default function Badge({
  variant = 'neutral',
  size = 'md',
  icon,
  dot = false,
  className,
  children,
  ...rest
}) {
  const iconSize = size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5'

  return (
    <span
      className={cn(BASE, VARIANTS[variant] || VARIANTS.neutral, SIZES[size] || SIZES.md, className)}
      {...rest}
    >
      {dot && !icon && (
        <span
          className={cn('h-1.5 w-1.5 rounded-full', DOT_COLORS[variant] || DOT_COLORS.neutral)}
          aria-hidden="true"
        />
      )}
      {renderIcon(icon, iconSize)}
      {children}
    </span>
  )
}
