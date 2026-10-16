/**
 * NAADAMAYA billing API: plans, subscription, Razorpay orders and verification.
 *
 *   const plans = await getPlans()
 *   const order = await createOrder('PRO')
 *   const result = await verifyPayment({ razorpay_order_id, razorpay_payment_id, razorpay_signature })
 *
 * Rules:
 *   - The frontend sends only a plan code. The price always comes from the
 *     backend, so it cannot be changed from the browser.
 *   - verifyPayment's response is the ONLY truth about a payment. Never treat
 *     Razorpay Checkout's success callback as "paid". After verifying, refresh
 *     usage and the subscription from the server.
 *   - Only the public key id (order.key_id) is ever received here.
 */

import api from '@/services/apiClient'

/** Public: works before sign-in. When signed in, the current plan has is_current=true. */
export const getPlans = () => api.get('/subscriptions/plans')

export const getSubscription = () => api.get('/subscriptions/me')

/** Creates a Razorpay order for a plan code ("GO" or "PRO"). */
export const createOrder = (planCode) => api.post('/payments/create-order', { plan_code: planCode })

/**
 * Sends what Razorpay Checkout returned to the backend, which recomputes the
 * signature and checks the payment with Razorpay itself.
 * Safe to call twice: the second response has already_processed=true.
 */
export const verifyPayment = ({ razorpay_order_id, razorpay_payment_id, razorpay_signature }) =>
  api.post('/payments/verify', { razorpay_order_id, razorpay_payment_id, razorpay_signature })

export const getPayments = (params = {}) => api.get(`/payments${api.qs(params)}`)
