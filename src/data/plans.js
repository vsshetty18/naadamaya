/**
 * The Free, Go and Pro plans, in one place.
 * Stage ("Choose Your Journey") and Credits ("Get more credits") both read
 * this list, so prices, credit amounts and feature lists can never differ
 * between the two pages.
 *
 * MOCK ONLY: there is no payment or subscription backend yet. A real one
 * would return this list from an API, and PricingCard would not change.
 *
 * This file holds data only. Icons are named here (`icon`) and the
 * PricingCard component turns each name into a lucide icon, so the data
 * stays plain and can later come from a server.
 *
 * Plan wording follows your Stage reference.
 */

export const PLANS = [
  {
    id: 'free',
    rank: 0,
    name: 'Free',
    tagline: 'Get started on your musical journey.',
    price: 0,
    period: null, // no "/ month" on the free plan
    credits: 10,
    creditsLabel: '10 credits/month',
    icon: 'leaf', // sage
    tone: 'sage',
    popular: false,
    features: [
      { text: '10 analysis credits', included: true },
      { text: 'Basic comparison report', included: true },
      { text: 'Standard analysis', included: true },
      { text: 'Advanced insights', included: false },
      { text: 'Priority processing', included: false },
      { text: 'AI suggestions', included: false },
    ],
  },
  {
    id: 'go',
    rank: 1,
    name: 'Go',
    tagline: 'For consistent learners who want to grow more.',
    price: 199,
    period: 'month',
    credits: 30,
    creditsLabel: '30 credits/month',
    icon: 'sprout', // blue
    tone: 'mist',
    popular: false,
    features: [
      { text: '30 analysis credits', included: true },
      { text: 'Detailed comparison report', included: true },
      { text: 'Advanced analysis', included: true },
      { text: 'AI suggestions', included: true },
      { text: 'Priority processing', included: false },
      { text: 'Early access to new features', included: false },
    ],
  },
  {
    id: 'pro',
    rank: 2,
    name: 'Pro',
    tagline: 'For serious singers ready to go beyond.',
    price: 449,
    period: 'month',
    credits: 100,
    creditsLabel: '100 credits/month',
    icon: 'crown', // brown / gold
    tone: 'brown',
    popular: true, // shows the "Most Popular" tab
    features: [
      { text: '100 analysis credits', included: true },
      { text: 'Complete AI report', included: true },
      { text: 'Advanced insights & tips', included: true },
      { text: 'Priority processing', included: true },
      { text: 'Early access to new features', included: true },
      { text: 'Support & community access', included: true },
    ],
  },
]

export const DEFAULT_PLAN_ID = 'free'

/** Finds a plan by id. Returns undefined for an unknown id. */
export function getPlan(id) {
  return PLANS.find((p) => p.id === id)
}

/**
 * What a plan's button should say and do, relative to the user's current plan.
 *   state: 'current' | 'upgrade' | 'downgrade'
 *   label: "Current Plan", "Upgrade to Go", "Switch to Free"
 */
export function getPlanAction(currentPlanId, plan) {
  const current = getPlan(currentPlanId) || getPlan(DEFAULT_PLAN_ID)

  if (plan.id === current.id) return { state: 'current', label: 'Current Plan' }
  if (plan.rank > current.rank) return { state: 'upgrade', label: `Upgrade to ${plan.name}` }
  return { state: 'downgrade', label: `Switch to ${plan.name}` }
}
