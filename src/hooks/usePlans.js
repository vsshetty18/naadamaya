import { useCallback, useEffect, useState } from 'react'

import { getPlans } from '@/services/api/billing'

/**
 * Loads the plans from the backend and converts them to the shape PricingCard
 * already uses. Prices, limits and feature lists come from the server only.
 * Icon and colour are decoration chosen by plan code.
 */
const LOOK = {
  FREE: { icon: 'leaf', tone: 'sage' },
  GO: { icon: 'sprout', tone: 'mist' },
  PRO: { icon: 'crown', tone: 'brown' },
}

function adapt(plan) {
  const look = LOOK[plan.code] || LOOK.FREE
  return {
    id: plan.code.toLowerCase(), // matches credits.plan ("free" | "go" | "pro")
    code: plan.code,
    rank: plan.rank,
    name: plan.name,
    tagline: plan.tagline || '',
    price: plan.price, // rupees
    period: plan.price > 0 ? 'month' : null,
    credits: plan.monthly_limit,
    creditsLabel: `${plan.monthly_limit} credits/month`,
    icon: look.icon,
    tone: look.tone,
    popular: plan.is_popular,
    features: (plan.features || []).map((f) => ({ text: f.text, included: f.included })),
  }
}

export default function usePlans() {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getPlans()
      setPlans(data.map(adapt))
    } catch (err) {
      setError(err?.message || 'We could not load the plans.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return { plans, loading, error, reload: load }
}
