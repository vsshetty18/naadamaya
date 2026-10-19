import { useState } from 'react'
import { Bell, LogOut, Settings, User } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import PaymentNotice from '@/components/PaymentNotice'
import PricingCard from '@/components/PricingCard'
import ProfileCard from '@/components/ProfileCard'
import SettingsRow from '@/components/SettingsRow'
import StatisticsCard from '@/components/StatisticsCard'
import { useAppState } from '@/context/AppStateContext'
import { useAuth } from '@/context/AuthContext'
import usePlans from '@/hooks/usePlans'
import useRazorpay from '@/hooks/useRazorpay'

/**
 * Stage: profile, statistics, membership, settings.
 * Everything comes from the server. A plan is activated only after the
 * backend verifies the Razorpay payment.
 */

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
  const { signOut } = useAuth()
  const { profile, stats, credits, refreshAccount } = useAppState()
  const { plans, loading, error: plansError, reload } = usePlans()

  const [buyingId, setBuyingId] = useState(null)
  const [logoutOpen, setLogoutOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)

  const pay = useRazorpay({ onSuccess: () => refreshAccount() })

  const handleSelect = (plan) => {
    setBuyingId(plan.id)
    pay.buy(plan.code)
  }

  const handleLogout = async () => {
    setLoggingOut(true)
    await signOut() // clears the session; the route guard returns to the sign-in screen
  }

  return (
    <div className="-mt-8 md:-mt-12">
      <div className="relative animate-fade-up">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="nm-title">Stage</h1>
            <p className="nm-subtitle mt-2 max-w-[34rem]">Your profile, progress and journey with NAADAMAYA.</p>
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

        <p className="mt-2 font-serif text-[1rem] italic leading-snug text-brown-600 sm:hidden">
          {'\u201C'}A better you sings a brighter world.{'\u201D'}
        </p>
      </div>

      <div className="mt-5 flex flex-col gap-5">
        <div className="flex flex-col gap-3.5">
          <ProfileCard profile={profile} credits={credits} onEdit={() => navigate('/profile')} />
          <StatisticsCard stats={stats} />
        </div>

        <section aria-label="Membership" className="animate-fade-up">
          <h2 className="font-serif text-[1.6rem] font-semibold leading-none text-brown-900 md:text-[1.9rem]">
            Choose Your Journey
          </h2>
          <p className="mt-1.5 text-[0.88rem] leading-snug text-brown-500">
            Upgrade to unlock more practice, deeper analysis and greater possibilities.
          </p>

          <div className="mt-4">
            <PaymentNotice
              state={pay.state}
              error={pay.error}
              canRetry={pay.canRetryVerification}
              onRetry={pay.retryVerification}
              onDismiss={pay.reset}
            />
          </div>

          {loading && <p className="mt-5 text-[0.88rem] text-brown-500" role="status">Loading plans...</p>}
          {plansError && (
            <div role="alert" className="mt-5 flex items-center gap-3 text-[0.88rem] text-brown-600">
              {plansError}
              <Button variant="secondary" size="sm" onClick={reload}>Try again</Button>
            </div>
          )}

          {plans.length > 0 && (
            <div className="mt-5 grid gap-5 md:grid-cols-3">
              {plans.map((plan) => (
                <PricingCard
                  key={plan.id}
                  plan={plan}
                  currentPlanId={credits.plan}
                  loading={pay.busy && buyingId === plan.id}
                  onSelect={pay.busy ? undefined : handleSelect}
                />
              ))}
            </div>
          )}
        </section>

        <section aria-label="Account settings" className="animate-fade-up">
          <h2 className="font-serif text-[1.6rem] font-semibold leading-none text-brown-900 md:text-[1.9rem]">
            Account Settings
          </h2>
          <p className="mt-1.5 text-[0.88rem] leading-snug text-brown-500">Manage your account and preferences.</p>

          <div className="mt-4 flex flex-col gap-2">
            <SettingsRow icon={User} title="Edit Profile" description="Update your photo, name, email or phone number" to="/profile" />
            <SettingsRow icon={Bell} title="Notifications" description="Manage your notifications and reminders" to="/profile" />
            <SettingsRow icon={Settings} title="App Preferences" description="Theme, language and other settings" to="/profile" />
            <SettingsRow icon={LogOut} title="Logout" description="Sign out from your account" danger onClick={() => setLogoutOpen(true)} />
          </div>
        </section>
      </div>

      <Modal
        open={logoutOpen}
        onClose={() => !loggingOut && setLogoutOpen(false)}
        icon={LogOut}
        title="Log out?"
        subtitle="You can sign back in any time with your phone number."
        size="sm"
        footer={
          <div className="flex gap-2.5">
            <Button variant="secondary" onClick={() => setLogoutOpen(false)} disabled={loggingOut} className="flex-1">
              Stay
            </Button>
            <Button variant="danger" leftIcon={LogOut} loading={loggingOut} onClick={handleLogout} className="flex-1">
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
