import { Check, Crown, Leaf, Sprout, X } from 'lucide-react'

import Badge from '@/components/Badge'
import Button from '@/components/Button'
import { getPlanAction } from '@/data/plans'
import { cn } from '@/utils/cn'
import { formatPrice } from '@/utils/formatters'

/**
 * One plan card, used on Stage ("Choose Your Journey") and on Credits.
 *
 *   [icon]  Free                    [Most Popular]
 *           Get started on your musical journey.
 *   ₹0
 *   (check) 10 analysis credits
 *   (x)     Advanced insights        (greyed out)
 *   [ Current Plan ]
 *
 * Props:
 *   plan             one entry from PLANS (src/data/plans.js)
 *   currentPlanId    the user's plan (AppStateContext credits.plan)
 *   onSelect(plan)   called when the button is pressed on a non-current plan
 *   compact          Credits layout: shows the credits line instead of the
 *                    full feature list
 *   loading          disables the button while a change is in progress
 *
 * It only draws a card. Choosing a plan is the caller's job, and there is
 * no payment here (mock only).
 */

const ICONS = { leaf: Leaf, sprout: Sprout, crown: Crown }

const TONES = {
  sage: {
    card: 'border-sage-200/80 bg-gradient-to-b from-sage-50 to-ivory-50',
    iconBg: 'bg-sage-100 text-sage-500',
    check: 'bg-sage-500 text-white',
    button: 'current',
  },
  mist: {
    card: 'border-mist-200/80 bg-gradient-to-b from-mist-50 to-ivory-50',
    iconBg: 'bg-mist-100 text-mist-500',
    check: 'bg-mist-500 text-white',
    button: 'go',
  },
  brown: {
    card: 'border-gold-300 bg-pro-glow shadow-lifted',
    iconBg: 'bg-gold-50 text-brown-500',
    check: 'bg-brown-500 text-white',
    button: 'primary',
  },
}

export default function PricingCard({
  plan,
  currentPlanId,
  onSelect,
  compact = false,
  loading = false,
  className,
}) {
  if (!plan) return null

  const tone = TONES[plan.tone] || TONES.sage
  const Icon = ICONS[plan.icon] || Leaf
  const action = getPlanAction(currentPlanId, plan)
  const isCurrent = action.state === 'current'

  // The current plan always looks calm. Others use their own colour.
  const buttonVariant = isCurrent ? 'current' : action.state === 'downgrade' ? 'secondary' : tone.button === 'current' ? 'primary' : tone.button

  return (
    <article
      aria-label={`${plan.name} plan`}
      className={cn(
        'relative flex flex-col rounded-card border p-4 shadow-card sm:p-5',
        tone.card,
        className
      )}
    >
      {plan.popular && (
        <Badge variant="popular" size="sm" className="absolute -top-2.5 right-4">
          Most Popular
        </Badge>
      )}

      <div className="flex items-start gap-3">
        <span className={cn('flex h-12 w-12 shrink-0 items-center justify-center rounded-full', tone.iconBg)}>
          <Icon className="h-6 w-6" strokeWidth={1.8} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h3 className="font-serif text-[1.5rem] font-semibold leading-none text-brown-900">{plan.name}</h3>
          <p className="mt-1.5 text-[0.78rem] leading-snug text-brown-500">{plan.tagline}</p>
        </div>
      </div>

      <p className="mt-4 flex items-baseline gap-1.5 font-serif text-brown-900">
        <span className="text-[2.1rem] font-semibold leading-none tabular-nums">{formatPrice(plan.price)}</span>
        {plan.period && <span className="font-sans text-[0.9rem] text-brown-500">/ {plan.period}</span>}
      </p>

      {compact ? (
        <p className="mt-3 flex items-center gap-2 text-[0.9rem] font-medium text-brown-700">
          <span className={cn('flex h-5 w-5 items-center justify-center rounded-full', tone.check)} aria-hidden="true">
            <Check className="h-3 w-3" strokeWidth={3} />
          </span>
          {plan.creditsLabel}
        </p>
      ) : (
        <ul className="mt-4 flex flex-1 flex-col gap-2.5">
          {plan.features.map((f) => (
            <li key={f.text} className={cn('flex items-start gap-2.5 text-[0.85rem] leading-snug', f.included ? 'text-brown-800' : 'text-brown-300')}>
              <span
                className={cn(
                  'mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full',
                  f.included ? tone.check : 'bg-ivory-200 text-brown-300'
                )}
                aria-hidden="true"
              >
                {f.included ? <Check className="h-3 w-3" strokeWidth={3} /> : <X className="h-3 w-3" strokeWidth={3} />}
              </span>
              <span>
                {f.text}
                <span className="sr-only">{f.included ? ' (included)' : ' (not included)'}</span>
              </span>
            </li>
          ))}
        </ul>
      )}

      <Button
        variant={buttonVariant}
        onClick={() => onSelect?.(plan)}
        disabled={isCurrent}
        loading={loading && !isCurrent}
        fullWidth
        className="mt-5"
      >
        {action.label}
      </Button>
    </article>
  )
}
