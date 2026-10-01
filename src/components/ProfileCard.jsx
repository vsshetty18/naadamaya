import { Link } from 'react-router-dom'
import { Camera, ChevronRight, Crown, Mail, Pencil, Phone, User } from 'lucide-react'

import { cn } from '@/utils/cn'
import { getInitials, pluralize } from '@/utils/formatters'
import { getPlan } from '@/data/plans'

/**
 * The profile card at the top of Stage.
 *
 *   [photo + camera]   V S Vighnesh (pencil)        [ crown  Free Account   > ]
 *                      mail  vighnesh@example.com   [ 10 credits remaining   ]
 *                      phone +91 98765 43210
 *
 * Props:
 *   profile        { name, email, phone, avatarUrl } from AppStateContext
 *   credits        { plan, total, remaining } from AppStateContext
 *   onEdit         called by the pencil and the camera button
 *   membershipTo   where the membership tile goes (default "/credits")
 *
 * Every value comes from props. Missing email or phone rows are left out.
 */

export default function ProfileCard({ profile, credits, onEdit, membershipTo = '/credits', className }) {
  if (!profile) return null

  const plan = getPlan(credits?.plan)
  const planName = plan ? `${plan.name} Account` : 'Free Account'
  const remaining = Number(credits?.remaining) || 0

  return (
    <section
      aria-label="Profile"
      className={cn('nm-card animate-fade-up p-4 sm:p-5', className)}
    >
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          {/* Photo with camera button */}
          <div className="relative shrink-0">
            <span className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-full border-2 border-ivory-50 bg-sage-100 text-sage-500 shadow-card sm:h-24 sm:w-24">
              {profile.avatarUrl ? (
                <img src={profile.avatarUrl} alt="" className="h-full w-full object-cover" />
              ) : profile.name ? (
                <span className="font-serif text-[1.9rem] font-semibold text-sage-600">
                  {getInitials(profile.name)}
                </span>
              ) : (
                <User className="h-9 w-9" strokeWidth={1.8} aria-hidden="true" />
              )}
            </span>
            <button
              type="button"
              onClick={onEdit}
              aria-label="Change profile photo"
              className="absolute -bottom-0.5 -right-0.5 flex h-8 w-8 items-center justify-center rounded-full border-2 border-ivory-50 bg-brown-600 text-ivory-50 shadow-soft transition-transform hover:scale-105 active:scale-95"
            >
              <Camera className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
            </button>
          </div>

          {/* Details */}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate font-serif text-[1.45rem] font-semibold leading-tight text-brown-900 sm:text-[1.7rem]">
                {profile.name || 'Your name'}
              </h2>
              <button
                type="button"
                onClick={onEdit}
                aria-label="Edit profile"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-brown-400 transition-colors hover:bg-blush-100 hover:text-brown-600"
              >
                <Pencil className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
              </button>
            </div>

            <ul className="mt-1.5 flex flex-col gap-1 text-[0.85rem] text-brown-600">
              {profile.email && (
                <li className="flex min-w-0 items-center gap-2">
                  <Mail className="h-4 w-4 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
                  <span className="truncate">{profile.email}</span>
                </li>
              )}
              {profile.phone && (
                <li className="flex min-w-0 items-center gap-2">
                  <Phone className="h-4 w-4 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
                  <span className="truncate">{profile.phone}</span>
                </li>
              )}
            </ul>
          </div>
        </div>

        {/* Membership tile */}
        <Link
          to={membershipTo}
          className="flex items-center gap-3 rounded-xl border border-gold-200/70 bg-gold-50/80 px-4 py-3 transition-colors hover:bg-gold-100/70 md:min-w-[15rem]"
        >
          <Crown className="h-6 w-6 shrink-0 text-gold-500" strokeWidth={1.6} aria-hidden="true" />
          <span className="min-w-0 flex-1">
            <span className="block font-serif text-[1.15rem] font-semibold leading-tight text-brown-900">
              {planName}
            </span>
            <span className="mt-0.5 block text-[0.78rem] leading-none text-brown-500">
              {pluralize(remaining, 'credit')} remaining
            </span>
          </span>
          <ChevronRight className="h-5 w-5 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
        </Link>
      </div>
    </section>
  )
}
