import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { cn } from '@/utils/cn'

/**
 * The single button used everywhere in Naadamaya.
 *
 * Variants (each matches a button in your references):
 *   cta       the large REPORT button (brown, wide-tracked, arrow at the right)
 *   primary   solid brown, e.g. "Upgrade to Pro"
 *   go        solid blue, e.g. "Upgrade to Go"
 *   upload    pale blue tile, e.g. "Upload"
 *   record    pale peach tile, e.g. "Record"
 *   current   pale sage, e.g. "Current Plan"
 *   secondary thin brown outline
 *   ghost     text only, for quiet actions
 *   danger    soft red, e.g. "Remove", "Discard"
 *
 * Props:
 *   variant, size ('sm' | 'md' | 'lg')
 *   leftIcon / rightIcon   a lucide component or an element
 *   loading                shows a spinner and disables the button
 *   fullWidth
 *   to                     renders a router <Link> instead of a <button>
 *
 * It only draws a button. It never decides what a click does.
 */

const BASE =
  'relative inline-flex select-none items-center justify-center gap-2 font-sans font-medium ' +
  'transition-all duration-200 ease-out active:scale-[0.98] ' +
  'disabled:pointer-events-none disabled:opacity-60'

const VARIANTS = {
  cta:
    'bg-cta-brown text-ivory-50 shadow-cta hover:brightness-105 hover:shadow-lifted ' +
    'font-display uppercase tracking-cta',
  primary:
    'bg-cta-brown text-ivory-50 shadow-cta hover:brightness-105',
  go:
    'bg-mist-500 text-white shadow-soft hover:bg-mist-600',
  upload:
    'border border-mist-200/70 bg-mist-100 text-mist-500 hover:bg-mist-200/70',
  record:
    'border border-blush-200/70 bg-blush-100 text-brown-500 hover:bg-blush-200/70',
  current:
    'bg-sage-100 text-sage-600',
  secondary:
    'border border-brown-200 bg-transparent text-brown-600 hover:bg-brown-50',
  ghost:
    'bg-transparent text-brown-500 hover:bg-brown-50',
  danger:
    'border border-blush-300 bg-blush-100 text-status-bad hover:bg-blush-200',
}

const SIZES = {
  sm: 'h-9 rounded-xl px-3 text-[0.8rem]',
  md: 'h-11 rounded-xl px-4 text-[0.92rem]',
  lg: 'h-12 rounded-xl2 px-6 text-base',
}

// The CTA is taller and pill-like, as in the reference.
const CTA_SIZE = 'h-[3.4rem] rounded-full px-6 text-[0.95rem] md:h-16'

/** Accepts either a lucide component (Upload) or a ready element (<Upload />). */
function renderIcon(icon, className) {
  if (!icon) return null
  if (typeof icon === 'function' || (typeof icon === 'object' && icon.$$typeof === undefined)) {
    const Icon = icon
    return <Icon className={className} strokeWidth={1.8} aria-hidden="true" />
  }
  return icon
}

const Button = forwardRef(function Button(
  {
    variant = 'primary',
    size = 'md',
    leftIcon,
    rightIcon,
    loading = false,
    fullWidth = false,
    disabled = false,
    to,
    type = 'button',
    className,
    children,
    ...rest
  },
  ref
) {
  const isCta = variant === 'cta'
  const iconSize = size === 'sm' ? 'h-4 w-4' : 'h-[1.15rem] w-[1.15rem]'

  const classes = cn(
    BASE,
    VARIANTS[variant] || VARIANTS.primary,
    isCta ? CTA_SIZE : SIZES[size] || SIZES.md,
    fullWidth && 'w-full',
    className
  )

  const content = (
    <>
      {loading ? (
        <Loader2 className={cn(iconSize, 'animate-spin')} aria-hidden="true" />
      ) : (
        renderIcon(leftIcon, iconSize)
      )}

      {children && <span className={isCta ? 'pl-1' : undefined}>{children}</span>}

      {/* On the CTA the arrow sits at the far right, like the reference. */}
      {rightIcon &&
        (isCta ? (
          <span className="absolute right-5 top-1/2 -translate-y-1/2">
            {renderIcon(rightIcon, iconSize)}
          </span>
        ) : (
          renderIcon(rightIcon, iconSize)
        ))}
    </>
  )

  // Router link (a disabled link is dropped from the tab order and click-blocked).
  if (to) {
    const isOff = disabled || loading
    return (
      <Link
        ref={ref}
        to={to}
        className={cn(classes, isOff && 'pointer-events-none opacity-60')}
        aria-disabled={isOff || undefined}
        tabIndex={isOff ? -1 : undefined}
        {...rest}
      >
        {content}
      </Link>
    )
  }

  return (
    <button
      ref={ref}
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {content}
    </button>
  )
})

export default Button
