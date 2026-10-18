import { useCallback, useEffect, useRef, useState } from 'react'

import { createOrder, verifyPayment } from '@/services/api/billing'

/**
 * Runs the Razorpay purchase flow for a plan.
 *
 *   const { buy, state, error, reset } = useRazorpay({ onSuccess })
 *   buy('PRO')
 *
 * state: 'idle' | 'creating' | 'checkout' | 'verifying' | 'success' | 'failed'
 *
 * Steps (the frontend never decides that a payment worked):
 *   1. createOrder(planCode)       backend reads the price from the database
 *   2. open Razorpay Checkout      loaded from checkout.razorpay.com on demand
 *   3. Checkout returns three ids  NOT treated as success
 *   4. verifyPayment(ids)          the backend recomputes the signature and
 *                                  asks Razorpay itself. Its answer is the truth.
 *   5. onSuccess(result)           the caller then refreshes usage and the subscription
 *
 * If verification fails after the user paid (for example a network drop),
 * state is 'failed' with a message telling them not to pay again. Calling
 * verify again with the same ids is safe (already_processed).
 *
 * Only the public key id (from createOrder) is used. No secret is here.
 */

const CHECKOUT_SRC = 'https://checkout.razorpay.com/v1/checkout.js'

function loadCheckout() {
  if (window.Razorpay) return Promise.resolve(true)
  return new Promise((resolve) => {
    const existing = document.querySelector(`script[src="${CHECKOUT_SRC}"]`)
    const script = existing || document.createElement('script')
    script.addEventListener('load', () => resolve(Boolean(window.Razorpay)), { once: true })
    script.addEventListener('error', () => resolve(false), { once: true })
    if (!existing) {
      script.src = CHECKOUT_SRC
      script.async = true
      document.body.appendChild(script)
    }
  })
}

export default function useRazorpay({ onSuccess } = {}) {
  const [state, setState] = useState('idle')
  const [error, setError] = useState(null)
  const pending = useRef(null) // ids returned by Checkout, kept for a safe retry of verification
  const mounted = useRef(true)
  const onSuccessRef = useRef(onSuccess)

  useEffect(() => {
    onSuccessRef.current = onSuccess
  }, [onSuccess])
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const set = useCallback((next, message = null) => {
    if (!mounted.current) return
    setState(next)
    setError(message)
  }, [])

  const verify = useCallback(
    async (ids) => {
      set('verifying')
      try {
        const result = await verifyPayment(ids)
        pending.current = null
        set('success')
        onSuccessRef.current?.(result)
      } catch (err) {
        set(
          'failed',
          err?.isNetwork || err?.status >= 500
            ? 'We could not confirm your payment yet. If money was deducted, do not pay again: tap "Check again".'
            : 'We could not verify this payment. If money was deducted, it will be reviewed. Please contact support.'
        )
      }
    },
    [set]
  )

  /** After a failed verification (network drop): asks the backend again with the same ids. */
  const retryVerification = useCallback(() => {
    if (pending.current) return verify(pending.current)
    return undefined
  }, [verify])

  const buy = useCallback(
    async (planCode) => {
      if (['creating', 'checkout', 'verifying'].includes(state)) return
      pending.current = null
      set('creating')

      let order
      try {
        order = await createOrder(planCode)
      } catch (err) {
        set('failed', err?.message || 'We could not start the payment. Please try again.')
        return
      }

      if (!(await loadCheckout())) {
        set('failed', 'We could not load the payment window. Check your connection and try again.')
        return
      }

      set('checkout')
      const checkout = new window.Razorpay({
        key: order.key_id,
        order_id: order.order_id,
        amount: order.amount,
        currency: order.currency,
        name: order.name,
        description: order.description,
        prefill: { contact: order.prefill_contact || undefined },
        theme: { color: '#93582F' },
        handler: (response) => {
          // Checkout says it finished. That is NOT proof: ask the backend.
          const ids = {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          }
          pending.current = ids
          verify(ids)
        },
        modal: {
          ondismiss: () => {
            if (!pending.current) set('idle') // closed without paying
          },
        },
      })
      checkout.on('payment.failed', (response) => {
        set('failed', response?.error?.description || 'The payment did not go through. You have not been charged.')
      })
      checkout.open()
    },
    [state, set, verify]
  )

  const reset = useCallback(() => {
    pending.current = null
    set('idle')
  }, [set])

  return {
    buy,
    retryVerification,
    reset,
    state,
    error,
    busy: ['creating', 'checkout', 'verifying'].includes(state),
    canRetryVerification: state === 'failed' && Boolean(pending.current),
  }
}
