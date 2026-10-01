import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, LogOut, Settings, User } from 'lucide-react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import PricingCard from '@/components/PricingCard'
import ProfileCard from '@/components/ProfileCard'
import SettingsRow from '@/components/SettingsRow'
import StatisticsCard from '@/components/StatisticsCard'
import { PLANS } from '@/data/plans'
import { useAppState } from '@/context/AppStateContext'

/**
 * Stage: the singer's journey (profile, statistics, membership, settings).
 *
 * Everything shown comes from AppStateContext and the shared PLANS data.
 * Choosing a plan and logging out are MOCK ONLY: there is no payment and
 * no authentication yet.
 */

/** Small decorative feather beside the quote (kept subtle). */
function FeatherDecor({ className }) {
  return (
    <svg viewBox="0 0 60 90" className={className} aria-hidden="true">
      <g transform="rotate(20 30 45)">
        <path d="M30 6 C48 24 46 52 30 66 C14 52 12 24 30 6 Z" fill="#CBD9C1" opacity="0.7" />
        <ellipse cx="30" cy="34" rx="8" ry="12" fill="#EBD3A0" />
        <ellipse cx="30" cy="35" rx="4.5" ry="7.5" fill="#2F7186" opacity="0.8" />
        <path d="M30 66 C28 76 24 84 20 88" stroke="#A9BF9A" strokeWidth="1.4" fill="none" strokeLinecap="round" />
      </g>
    </svg>
  )
}

export default function Stage() {
  const navigate = useNavigate()
  const { profile, stats, credits, changePlan } = useAppState()

  const [changingTo, setChangingTo] = useState(null)
  const [logoutOpen, setLogoutOpen] = useState(false)

  const handleSelect = (plan) => {
    setChangingTo(plan.id)
    // Short pause so the button's loading state is visible (mock only).
    setTimeout(() => {
      changePlan(plan.id, plan.credits)
      setChangingTo(null)
    }, 700)
  }

  const handleLogout = () => {
    // MOCK ONLY: no session exists yet. A real app would clear it here.
    setLogoutOpen(false)
    navigate('/')
  }

  return (
    <div className="-mt-8 md:-mt-12">
      {/* Title block */}
      <div className="relative animate-fade-up">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="nm-title">Stage</h1>
            <p className="nm-subtitle mt-2 max-w-[34rem]">
              Your profile, progress and journey with Naadamaya.
            </p>
          </div>

          <figure className="relative hidden shrink-0 pt-2 text-right sm:block md:pt-4">
            <FeatherDecor className="pointer-events-none absolute -left-12 top-0 h-16 w-10 opacity-60 md:-left-14 md:h-20 md:w-12" />
            <blockquote className="font-serif text-[1.05rem] italic leading-snug text-brown-600 md:text-[1.25rem]">
              {'\u201C'}A better you
              <br />
              sings a brighter world.{'\u201D'}
            </blockquote>
          </figure>
        </div>

        {/* Quote on phones sits under the subtitle */}
        <p className="mt-2 font-serif text-[1rem] italic leading-snug text-brown-600 sm:hidden">
          {'\u201C'}A better you sings a brighter world.{'\u201D'}
        </p>
      </div>

      <div className="mt-5 flex flex-col gap-5">
        {/* Profile and statistics */}
        <div className="flex flex-col gap-3.5">
          <ProfileCard profile={profile} credits={credits} onEdit={() => navigate('/profile')} />
          <StatisticsCard stats={stats} />
        </div>

        {/* Membership */}
        <section aria-label="Membership" className="animate-fade-up">
          <h2 className="font-serif text-[1.6rem] font-semibold leading-none text-brown-900 md:text-[1.9rem]">
            Choose Your Journey
          </h2>
          <p className="mt-1.5 text-[0.88rem] leading-snug text-brown-500">
            Upgrade to unlock more practice, deeper analysis and greater possibilities.
          </p>

          <div className="mt-5 grid gap-5 md:grid-cols-3">
            {PLANS.map((plan) => (
              <PricingCard
                key={plan.id}
                plan={plan}
                currentPlanId={credits.plan}
                loading={changingTo === plan.id}
                onSelect={handleSelect}
              />
            ))}
          </div>
        </section>

        {/* Account settings */}
        <section aria-label="Account settings" className="animate-fade-up">
          <h2 className="font-serif text-[1.6rem] font-semibold leading-none text-brown-900 md:text-[1.9rem]">
            Account Settings
          </h2>
          <p className="mt-1.5 text-[0.88rem] leading-snug text-brown-500">
            Manage your account and preferences.
          </p>

          <div className="mt-4 flex flex-col gap-2">
            <SettingsRow
              icon={User}
              title="Edit Profile"
              description="Update your photo, name, email or phone number"
              to="/profile"
            />
            <SettingsRow
              icon={Bell}
              title="Notifications"
              description="Manage your notifications and reminders"
              to="/profile"
            />
            <SettingsRow
              icon={Settings}
              title="App Preferences"
              description="Theme, language and other settings"
              to="/profile"
            />
            <SettingsRow
              icon={LogOut}
              title="Logout"
              description="Sign out from your account"
              danger
              onClick={() => setLogoutOpen(true)}
            />
          </div>
        </section>
      </div>

      {/* Logout confirmation */}
      <Modal
        open={logoutOpen}
        onClose={() => setLogoutOpen(false)}
        icon={LogOut}
        title="Log out?"
        subtitle="You can sign back in any time."
        size="sm"
        footer={
          <div className="flex gap-2.5">
            <Button variant="secondary" onClick={() => setLogoutOpen(false)} className="flex-1">
              Stay
            </Button>
            <Button variant="danger" leftIcon={LogOut} onClick={handleLogout} className="flex-1">
              Log out
            </Button>
          </div>
        }
      >
        <p className="pb-1 text-[0.88rem] leading-snug text-brown-600">
          Your reports and attempt history stay saved with your account.
        </p>
      </Modal>
    </div>
  )
}
