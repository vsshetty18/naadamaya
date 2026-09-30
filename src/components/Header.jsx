import { Link, useLocation } from 'react-router-dom'
import { User } from 'lucide-react'

import HeroArt from '@/components/HeroArt'
import logoMark from '@/assets/logo-mark.png'
import { useAppState } from '@/context/AppStateContext'
import { cn } from '@/utils/cn'
import { getInitials } from '@/utils/formatters'

/**
 * The shared Naadamaya header, used on every page.
 *
 *   [ logo badge ]  NAADAMAYA                      [ profile ]
 *                   sing. evolve. globally.
 *   ------------------------------------------------------------
 *   hero scene (flute, peacock feather, blossoms, "Soul Therapy.")
 *
 * Props:
 *   nav       optional desktop navigation, shown from `lg` up.
 *             AppLayout passes it in, so the header itself knows no routes.
 *   showHero  false gives a compact bar without the hero scene.
 */

function ProfileButton() {
  const { pathname } = useLocation()
  const { profile } = useAppState()
  const active = pathname === '/profile'

  return (
    <Link
      to="/profile"
      aria-label="Open profile"
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-2xl border shadow-soft',
        'transition-all duration-200 hover:shadow-card active:scale-95 md:h-14 md:w-14',
        active ? 'border-brown-300 bg-blush-100' : 'border-blush-200/70 bg-blush-50'
      )}
    >
      {profile.avatarUrl ? (
        <img src={profile.avatarUrl} alt="" className="h-full w-full object-cover" />
      ) : profile.name ? (
        <span className="relative flex h-full w-full items-center justify-center">
          <User className="h-6 w-6 text-brown-500 md:h-7 md:w-7" strokeWidth={2} aria-hidden="true" />
          <span className="sr-only">{getInitials(profile.name)}</span>
        </span>
      ) : (
        <User className="h-6 w-6 text-brown-500" strokeWidth={2} aria-hidden="true" />
      )}
    </Link>
  )
}

export default function Header({ nav, showHero = true, className }) {
  return (
    <header className={cn('relative isolate overflow-hidden', className)}>
      {/* Hero scene sits behind everything */}
      {showHero && <HeroArt className="absolute inset-0 -z-10" />}

      {/* Top bar */}
      <div className="safe-top">
        <div className="mx-auto flex w-full max-w-desktop items-center gap-3 px-4 pb-2 pt-4 md:px-8 md:pt-6">
          <Link
            to="/"
            aria-label="Naadamaya home"
            className="flex min-w-0 flex-1 items-center gap-3 md:flex-none md:gap-4"
          >
            <span className="flex h-[3.4rem] w-[3.4rem] shrink-0 items-center justify-center rounded-full border border-brown-300/70 bg-ivory-50/70 shadow-soft md:h-16 md:w-16">
              <img
                src={logoMark}
                alt=""
                className="h-[2.5rem] w-[2.5rem] object-contain md:h-12 md:w-12"
                draggable="false"
              />
            </span>

            <span className="flex min-w-0 flex-col">
              <span className="nm-wordmark truncate text-[1.35rem] leading-none sm:text-[1.7rem] md:text-[2rem]">
                Naadamaya
              </span>
              <span className="nm-tagline mt-1.5 truncate text-[0.52rem] sm:text-[0.6rem] md:text-[0.68rem]">
                sing. evolve. globally.
              </span>
            </span>
          </Link>

          {/* Desktop navigation slot */}
          {nav && <div className="ml-auto mr-2 hidden lg:block">{nav}</div>}

          <ProfileButton />
        </div>
      </div>

      {/* Space for the hero scene to show through */}
      {showHero && <div className="h-40 sm:h-44 md:h-52" aria-hidden="true" />}
    </header>
  )
}
