import { isValidElement } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import { cn } from '@/utils/cn'

/**
 * One row in a settings list (Stage "Account Settings" and Profile).
 *
 *   (icon)  Edit Profile   Update your photo, name, email or phone   >
 *
 * Props:
 *   icon         a lucide component or a ready element, shown in a round tile
 *   title        main label
 *   description  quiet line beside (wide screens) or under (phones) the title
 *   value        optional current value shown at the right, e.g. "English"
 *   to           renders a router link
 *   onClick      renders a button
 *   control      optional element at the right instead of the arrow
 *                (for example a toggle switch). With `control`, the row is
 *                not clickable as a whole, so the control receives the click.
 *   danger       soft red styling, e.g. Logout
 *   chevron      false hides the arrow
 *
 * It only draws a row. What a tap does is the caller's job.
 */

function renderIcon(icon, className) {
  if (!icon) return null
  if (isValidElement(icon)) return icon
  const Icon = icon
  return <Icon className={className} strokeWidth={1.8} aria-hidden="true" />
}

export default function SettingsRow({
  icon,
  title,
  description,
  value,
  to,
  onClick,
  control,
  danger = false,
  chevron = true,
  className,
}) {
  const inner = (
    <>
      <span
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
          danger ? 'bg-blush-100 text-status-bad' : 'bg-blush-100 text-brown-500'
        )}
      >
        {renderIcon(icon, 'h-5 w-5')}
      </span>

      <span className="min-w-0 flex-1 sm:flex sm:items-baseline sm:gap-4">
        <span
          className={cn(
            'block shrink-0 text-[0.98rem] font-medium leading-tight',
            danger ? 'text-status-bad' : 'text-brown-900'
          )}
        >
          {title}
        </span>
        {description && (
          <span className="mt-0.5 block truncate text-[0.78rem] leading-snug text-brown-500 sm:mt-0">
            {description}
          </span>
        )}
      </span>

      {value && <span className="shrink-0 text-[0.85rem] text-brown-500">{value}</span>}

      {control
        ? <span className="shrink-0">{control}</span>
        : chevron && (
            <ChevronRight className="h-5 w-5 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
          )}
    </>
  )

  const classes = cn(
    'flex w-full items-center gap-3 rounded-xl border border-gold-100/70 bg-ivory-50/80 px-3 py-2.5 text-left',
    'transition-colors duration-200',
    (to || onClick) && !control && 'hover:bg-blush-50 active:scale-[0.995]',
    className
  )

  if (control) return <div className={classes}>{inner}</div>

  if (to) {
    return (
      <Link to={to} className={classes}>
        {inner}
      </Link>
    )
  }

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={classes}>
        {inner}
      </button>
    )
  }

  return <div className={classes}>{inner}</div>
}
