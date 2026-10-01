import { useState } from 'react'
import { Info, Music } from 'lucide-react'

import CreditCard from '@/components/CreditCard'
import PricingCard from '@/components/PricingCard'
import { PLANS } from '@/data/plans'
import { useAppState } from '@/context/AppStateContext'
import { formatDate, pluralize } from '@/utils/formatters'

/**
 * Credits: the analysis balance, recent usage and plans.
 *
 * Everything shown comes from AppStateContext (balance, plan, usage list)
 * and the shared PLANS data. Choosing a plan is MOCK ONLY: it calls
 * changePlan(), with no payment.
 */

export default function Credits() {
  const { credits, usage, changePlan } = useAppState()
  const [changingTo, setChangingTo] = useState(null)

  const handleSelect = (plan) => {
    setChangingTo(plan.id)
    // Short pause so the button's loading state is visible (mock only).
    setTimeout(() => {
      changePlan(plan.id, plan.credits)
      setChangingTo(null)
    }, 700)
  }

  return (
    <div className="-mt-8 md:-mt-12">
      {/* Title block */}
      <div className="animate-fade-up">
        <h1 className="nm-title">Credits</h1>
        <p className="nm-subtitle mt-2 max-w-[34rem]">Your Naadamaya analysis balance.</p>
      </div>

      <div className="mt-5 flex flex-col gap-5">
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <CreditCard credits={credits} />

          {/* Recent usage */}
          <section aria-label="Recent analysis" className="nm-card animate-fade-up p-4 sm:p-5">
            <h2 className="font-serif text-[1.35rem] font-semibold leading-none text-brown-900 sm:text-[1.5rem]">
              Recent Analysis
            </h2>

            {usage.length === 0 ? (
              <p className="mt-4 text-[0.88rem] leading-snug text-brown-500">
                No analyses yet. Your first report will appear here.
              </p>
            ) : (
              <ul className="mt-3.5 flex flex-col gap-2">
                {usage.slice(0, 6).map((u) => (
                  <li
                    key={u.id}
                    className="flex items-center gap-3 rounded-xl border border-gold-100/70 bg-ivory-50/70 px-3 py-2.5"
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-mist-100 text-mist-500">
                      <Music className="h-5 w-5" strokeWidth={1.8} aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-serif text-[1.05rem] font-semibold leading-tight text-brown-900">
                        {u.title}
                      </span>
                      <span className="mt-0.5 block text-[0.74rem] leading-none text-brown-500">
                        {formatDate(u.date)}
                      </span>
                    </span>
                    <span className="shrink-0 text-[0.8rem] font-medium text-brown-600">
                      {pluralize(u.credits, 'credit')} used
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        {/* Get more credits */}
        <section aria-label="Get more credits" className="animate-fade-up">
          <h2 className="font-serif text-[1.6rem] font-semibold leading-none text-brown-900 md:text-[1.9rem]">
            Get More Credits
          </h2>
          <p className="mt-1.5 text-[0.88rem] leading-snug text-brown-500">
            Choose the plan that fits your practice.
          </p>

          <div className="mt-5 grid gap-5 md:grid-cols-3">
            {PLANS.map((plan) => (
              <PricingCard
                key={plan.id}
                plan={plan}
                currentPlanId={credits.plan}
                compact
                loading={changingTo === plan.id}
                onSelect={handleSelect}
              />
            ))}
          </div>
        </section>

        {/* Info */}
        <p className="flex items-start gap-2 rounded-xl border border-gold-100 bg-gold-50/60 px-3.5 py-3 text-[0.82rem] leading-snug text-brown-600">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-gold-500" strokeWidth={1.8} aria-hidden="true" />
          Credits are used when Naadamaya generates a detailed singing analysis report.
        </p>
      </div>
    </div>
  )
}
