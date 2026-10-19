import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'

import Button from '@/components/Button'

/**
 * Shows where a purchase is. Success is shown only after the backend has
 * verified the payment (useRazorpay reaches 'success' only then).
 */
export default function PaymentNotice({ state, error, canRetry, onRetry, onDismiss }) {
  if (state === 'idle' || state === 'checkout') return null

  if (state === 'creating' || state === 'verifying') {
    return (
      <p role="status" className="flex items-center gap-2 rounded-xl border border-gold-200 bg-gold-50/70 px-3.5 py-3 text-[0.85rem] text-brown-600">
        <Loader2 className="h-4 w-4 animate-spin text-brown-400" aria-hidden="true" />
        {state === 'creating' ? 'Starting your payment...' : 'Verifying your payment. Please do not close this page.'}
      </p>
    )
  }

  if (state === 'success') {
    return (
      <div role="status" className="flex items-center justify-between gap-3 rounded-xl border border-sage-200 bg-sage-50 px-3.5 py-3 text-[0.85rem] text-sage-600">
        <span className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Payment verified. Your plan is now active.
        </span>
        <Button variant="ghost" size="sm" onClick={onDismiss}>OK</Button>
      </div>
    )
  }

  return (
    <div role="alert" className="rounded-xl border border-blush-300 bg-blush-50 px-3.5 py-3 text-[0.85rem] text-brown-700">
      <p className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-status-bad" aria-hidden="true" />
        {error}
      </p>
      <div className="mt-2 flex gap-2">
        {canRetry && <Button variant="primary" size="sm" onClick={onRetry}>Check again</Button>}
        <Button variant="ghost" size="sm" onClick={onDismiss}>Dismiss</Button>
      </div>
    </div>
  )
}
