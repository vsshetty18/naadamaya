/**
 * NAADAMAYA auth API (phone number + OTP).
 *
 *   const sent = await sendOtp('98765 43210')
 *   const result = await verifyOtp('98765 43210', '123456')
 *   await logout()
 *   const me = await getMe()
 *
 * Tokens are never handled by components: verifyOtp stores the session in
 * apiClient, and logout clears it. Phone numbers are sent as typed; the
 * backend normalises them to one canonical form (+919876543210).
 */

import api, { session } from '@/services/apiClient'

/** Sends a code. Returns { masked_phone, expires_in, resend_after, development_otp }. */
export function sendOtp(phoneNumber) {
  return api.post('/auth/send-otp', { phone_number: phoneNumber }, { auth: false })
}

/**
 * Checks the code. On success the session is stored and the result is
 * { is_new_user, user, expires_in, ... }. Tokens are NOT returned to callers.
 */
export async function verifyOtp(phoneNumber, otp, deviceLabel) {
  const data = await api.post(
    '/auth/verify-otp',
    { phone_number: phoneNumber, otp, device_label: deviceLabel || guessDeviceLabel() },
    { auth: false }
  )
  session.set(data)
  const { access_token, refresh_token, ...safe } = data
  return safe
}

/** The signed-in account. Used on app start to restore the session. */
export function getMe() {
  return api.get('/auth/me')
}

/**
 * Signs out. Never fails: the local session is always cleared, even if the
 * server cannot be reached.
 */
export async function logout({ allDevices = false } = {}) {
  const refreshToken = session.getRefreshToken()
  try {
    await api.post('/auth/logout', { refresh_token: refreshToken, all_devices: allDevices }, { auth: false })
  } catch {
    /* the server will expire the token on its own */
  } finally {
    session.clear('signed_out')
  }
}

/** Permanently deletes the account (needs the typed word DELETE). */
export async function deleteAccount() {
  const result = await api.del('/users/me', { confirm: 'DELETE' })
  session.clear('account_deleted')
  return result
}

function guessDeviceLabel() {
  const ua = navigator.userAgent || ''
  const os = /Android/i.test(ua) ? 'Android' : /iPhone|iPad/i.test(ua) ? 'iOS' : /Windows/i.test(ua) ? 'Windows' : /Mac/i.test(ua) ? 'Mac' : 'Device'
  const browser = /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Firefox\//.test(ua) ? 'Firefox' : /Safari\//.test(ua) ? 'Safari' : 'Browser'
  return `${browser} on ${os}`
}
