import { NavLink } from 'react-router-dom'
import { BarChart3, Crown, Home, Star } from 'lucide-react'

import ProgressBar from '@/components/ProgressBar'
import { useAppState } from '@/context/AppStateContext'
import { cn } from '@/utils/cn'
import { pluralize } from '@/utils/formatters'

/**
 * Global navigation: Learn, Report, Credits, Stage.
 *
 *   BottomNavigation     fixed bar for phones and tablets (hidden from `lg` up)
 *   DesktopNavigation    horizontal links for the Header `nav` slot (`lg` up)
 *
 * Both read the same NAV_ITEMS, so the destinations can never drift apart.
 * The Credits item carries the credit progress indicator, as in the references.
 */

export const NAV_ITEMS = [
  { id: 'learn', label: 'Learn', to: '/', icon: Home, end: true, filled: true },
  { id: 'report', label: 'Report', to: '/report', icon: BarChart3 },
  { id: 'credits', label: 'Credits', to: '/credits', icon: Crown, credits: true },
  { id: 'stage', label: 'Stage', to: '/stage', icon: Star, filled: true },
]

/** Live credit info from app state, formatted for the indicator. */
function useCreditInfo() {
  const { credits, creditPercent } = useAppState()
  return {
    percent: creditPercent,
    label: `${credits.remaining} of ${pluralize(credits.total, 'credit')} remaining`,
    remaining: credits.remaining,
  }
}

/* ==========================================================
   MOBILE / TABLET
   ========================================================== */

function BottomItem({ item, credit }) {
  const Icon = item.icon

  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        cn(
          'group flex flex-col items-center justify-center gap-1 rounded-2xl px-1 py-2.5',
          'transition-colors duration-200',
          isActive ? 'bg-blush-100 text-brown-600' : 'text-brown-400 hover:text-brown-600'
        )
      }
    >
      {({ isActive }) => (
        <>
          {item.credits ? (
            // Crown + credit bar in a small pill, exactly like the reference.
            <span
              className="flex w-full items-center gap-1.5 rounded-full border border-gold-100 bg-ivory-100/80 px-2 py-1.5"
              title={credit.label}
            >
              <Icon className="h-4 w-4 shrink-0 text-gold-500" strokeWidth={2} aria-hidden="true" />
              <ProgressBar
                value={credit.percent}
                tone="good"
                size="md"
                label={credit.label}
                className="min-w-0 flex-1"
              />
            </span>
          ) : (
            <Icon
              className={cn('h-6 w-6', item.filled && isActive && 'fill-current')}
              strokeWidth={isActive ? 2.2 : 1.8}
              aria-hidden="true"
            />
          )}

          <span className={cn('text-[0.8rem] leading-none', isActive ? 'font-semibold' : 'font-medium')}>
            {item.label}
          </span>
        </>
      )}
    </NavLink>
  )
}

export default function BottomNavigation({ className }) {
  const credit = useCreditInfo()

  return (
    <nav
      aria-label="Main"
      className={cn('fixed inset-x-0 bottom-0 z-40 px-3 pb-3 lg:hidden', className)}
      style={{ paddingBottom: 'calc(0.75rem + var(--safe-bottom))' }}
    >
      <div className="mx-auto max-w-app rounded-xl3 border border-gold-100/80 bg-ivory-50/95 p-1.5 shadow-nav backdrop-blur-md">
        <div className="grid grid-cols-[1fr_1fr_1.75fr_1fr] items-stretch gap-1">
          {NAV_ITEMS.map((item) => (
            <BottomItem key={item.id} item={item} credit={credit} />
          ))}
        </div>
      </div>
    </nav>
  )
}

/* ==========================================================
   DESKTOP (Header `nav` slot, `lg` and up)
   ========================================================== */

export function DesktopNavigation({ className }) {
  const credit = useCreditInfo()

  return (
    <nav aria-label="Main" className={cn('flex items-center gap-1.5', className)}>
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon
        return (
          <NavLink
            key={item.id}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 rounded-full px-4 py-2.5 text-[0.95rem] transition-colors duration-200',
                isActive
                  ? 'bg-blush-100 font-semibold text-brown-600'
                  : 'font-medium text-brown-500 hover:bg-brown-50 hover:text-brown-700'
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={cn(
                    'h-[1.15rem] w-[1.15rem]',
                    item.credits && 'text-gold-500',
                    item.filled && isActive && 'fill-current'
                  )}
                  strokeWidth={2}
                  aria-hidden="true"
                />
                {item.label}
                {item.credits && (
                  <ProgressBar
                    value={credit.percent}
                    tone="good"
                    size="md"
                    label={credit.label}
                    className="w-14"
                  />
                )}
              </>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}
