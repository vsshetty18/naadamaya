import { useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'

import { cn } from '@/utils/cn'

/**
 * Shared modal / bottom sheet.
 *
 * On phones it slides up from the bottom as a sheet. From `md` (tablet and
 * desktop) it becomes a centered dialog. Used by the Upload modal, the
 * Record modal, the settings dialogs and any confirmation.
 *
 * Props:
 *   open          whether it is visible
 *   onClose       called on the X button, Escape and a backdrop click
 *   title         heading text
 *   subtitle      small line under the title
 *   icon          a lucide component or element shown in the header
 *   size          'sm' | 'md' | 'lg' (dialog width from `md` up)
 *   footer        content pinned to the bottom (buttons)
 *   dismissible   false blocks Escape and backdrop close (for example while
 *                 a microphone permission prompt is open)
 *   showClose     false hides the X button
 *
 * It only draws the frame. What goes inside is the caller's job.
 */

const SIZES = {
  sm: 'md:max-w-sm',
  md: 'md:max-w-md',
  lg: 'md:max-w-2xl',
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])'

export default function Modal({
  open,
  onClose,
  title,
  subtitle,
  icon,
  size = 'md',
  footer,
  dismissible = true,
  showClose = true,
  className,
  children,
}) {
  const titleId = useId()
  const panelRef = useRef(null)
  const onCloseRef = useRef(onClose)
  const dismissibleRef = useRef(dismissible)

  useEffect(() => {
    onCloseRef.current = onClose
    dismissibleRef.current = dismissible
  }, [onClose, dismissible])

  // Escape to close, Tab kept inside the panel, scroll locked behind it.
  useEffect(() => {
    if (!open) return undefined

    const previouslyFocused = document.activeElement
    const scrollbar = window.innerWidth - document.documentElement.clientWidth
    const prevOverflow = document.body.style.overflow
    const prevPadding = document.body.style.paddingRight
    document.body.style.overflow = 'hidden'
    if (scrollbar > 0) document.body.style.paddingRight = `${scrollbar}px`

    // Move focus into the panel.
    const raf = requestAnimationFrame(() => {
      const panel = panelRef.current
      if (!panel) return
      const first = panel.querySelector(FOCUSABLE)
      ;(first || panel).focus()
    })

    const onKey = (e) => {
      if (e.key === 'Escape' && dismissibleRef.current) {
        e.stopPropagation()
        onCloseRef.current?.()
        return
      }
      if (e.key !== 'Tab') return

      const panel = panelRef.current
      if (!panel) return
      const items = Array.from(panel.querySelectorAll(FOCUSABLE))
      if (items.length === 0) {
        e.preventDefault()
        panel.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKey)

    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      document.body.style.paddingRight = prevPadding
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus()
    }
  }, [open])

  if (!open) return null

  const Icon = typeof icon === 'function' || (icon && icon.$$typeof && !icon.type) ? icon : null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center md:p-6">
      {/* Backdrop */}
      <div
        className="absolute inset-0 animate-fade-in bg-brown-900/40 backdrop-blur-[2px]"
        onClick={dismissible ? onClose : undefined}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        className={cn(
          'relative flex max-h-[92dvh] w-full flex-col overflow-hidden outline-none',
          'rounded-t-xl3 border border-gold-100/80 bg-ivory shadow-lifted',
          'animate-slide-up md:max-h-[86dvh] md:animate-scale-in md:rounded-xl3',
          SIZES[size] || SIZES.md,
          className
        )}
      >
        {/* Grab handle (phones only) */}
        <div className="mx-auto mt-2.5 h-1 w-10 shrink-0 rounded-full bg-brown-200 md:hidden" aria-hidden="true" />

        {(title || showClose) && (
          <div className="flex shrink-0 items-start gap-3 px-5 pb-3 pt-4 md:px-6 md:pt-5">
            {icon && (
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gold-50 text-brown-500">
                {Icon ? <Icon className="h-5 w-5" strokeWidth={1.8} aria-hidden="true" /> : icon}
              </div>
            )}

            <div className="min-w-0 flex-1">
              {title && (
                <h2 id={titleId} className="font-serif text-[1.45rem] font-semibold leading-tight text-brown-900">
                  {title}
                </h2>
              )}
              {subtitle && <p className="mt-0.5 text-[0.85rem] leading-snug text-brown-500">{subtitle}</p>}
            </div>

            {showClose && (
              <button
                type="button"
                onClick={onClose}
                disabled={!dismissible}
                aria-label="Close"
                className="-mr-1.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-brown-500 transition-colors hover:bg-brown-50"
              >
                <X className="h-5 w-5" strokeWidth={1.8} aria-hidden="true" />
              </button>
            )}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5 md:px-6">{children}</div>

        {footer && (
          <div className="safe-bottom shrink-0 border-t border-gold-100 bg-ivory-50 px-5 py-4 md:px-6">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  )
}
