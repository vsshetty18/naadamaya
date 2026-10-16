/**
 * NAADAMAYA API client. Every request in the app goes through here.
 *
 *   const data = await api.get('/usage')
 *   const data = await api.post('/analysis/start', { recording_id }, { idempotencyKey })
 *   const data = await api.upload('/songs/reference', formData)
 *   const blob = await api.blob('/songs/<id>/audio')      // audio that needs the token
 *
 * What it handles:
 *   - Adds "Authorization: Bearer <access token>".
 *   - Errors always arrive as an ApiError { status, code, message, details,
 *     requestId, retryAfter }, never as raw fetch errors.
 *   - 401: it refreshes the session ONCE and retries the request. Several
 *     requests failing at the same moment share ONE refresh call. This matters,
 *     because the backend treats a refresh token used twice as stolen and ends
 *     the whole session.
 *   - If the refresh itself is refused, the session is cleared and listeners
 *     (AuthContext) are told, so the app returns to the sign-in screen.
 *   - A network failure while refreshing does NOT sign the user out.
 *   - 403, 429 and 5xx are not retried. Their code and message are surfaced.
 *
 * Token storage (a deliberate trade-off):
 *   access token   memory only, lost on reload (re-created by refreshing)
 *   refresh token  localStorage, so a reload keeps the user signed in.
 *                  Any script running on the page can read localStorage, so the
 *                  site must stay free of XSS (React escapes output by default).
 *
 * Only public values live here. No secret is ever used by the frontend.
 */

const BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '') + '/api/v1'
const REFRESH_KEY = 'naadamaya.refresh_token'
const DEFAULT_TIMEOUT_MS = 30_000
const UPLOAD_TIMEOUT_MS = 180_000

/* ==========================================================
   Errors
   ========================================================== */
export class ApiError extends Error {
  constructor({ status = 0, code = 'UNKNOWN_ERROR', message, details = {}, requestId = null, retryAfter = null }) {
    super(message || 'Something went wrong. Please try again.')
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details // extra fields from the server, e.g. upgrade_required, fields
    this.requestId = requestId
    this.retryAfter = retryAfter
  }

  get isAuth() {
    return this.status === 401
  }
  get isNetwork() {
    return this.code === 'NETWORK_ERROR' || this.code === 'TIMEOUT'
  }
}

export const isApiError = (err) => err instanceof ApiError

/* ==========================================================
   Session storage
   ========================================================== */
let accessToken = null
const listeners = new Set()

function readRefresh() {
  try {
    return localStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}
function writeRefresh(value) {
  try {
    if (value) localStorage.setItem(REFRESH_KEY, value)
    else localStorage.removeItem(REFRESH_KEY)
  } catch {
    /* storage blocked: the session simply lasts until reload */
  }
}

export const session = {
  /** Called after sign-in or refresh with { access_token, refresh_token }. */
  set({ access_token, refresh_token }) {
    accessToken = access_token || null
    if (refresh_token) writeRefresh(refresh_token)
  },
  clear(reason = 'signed_out') {
    accessToken = null
    writeRefresh(null)
    listeners.forEach((fn) => fn({ type: 'cleared', reason }))
  },
  hasRefreshToken: () => Boolean(readRefresh()),
  getRefreshToken: readRefresh,
  hasAccessToken: () => Boolean(accessToken),
  /** AuthContext listens here. Returns an unsubscribe function. */
  subscribe(fn) {
    listeners.add(fn)
    return () => listeners.delete(fn)
  },
}

/* ==========================================================
   Low-level request
   ========================================================== */
function toApiError(response, body) {
  const err = body?.error || {}
  const { code, message, ...details } = err
  const retryHeader = Number(response.headers.get('Retry-After'))
  return new ApiError({
    status: response.status,
    code: code || (response.status >= 500 ? 'INTERNAL_ERROR' : 'REQUEST_FAILED'),
    message,
    details,
    requestId: body?.request_id || response.headers.get('X-Request-ID'),
    retryAfter: details.retry_after ?? (Number.isFinite(retryHeader) && retryHeader > 0 ? retryHeader : null),
  })
}

async function rawFetch(path, { method = 'GET', body, headers = {}, signal, timeout = DEFAULT_TIMEOUT_MS, auth = true } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), timeout)
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason)
    else signal.addEventListener('abort', () => controller.abort(signal.reason), { once: true })
  }

  const finalHeaders = { Accept: 'application/json', ...headers }
  if (auth && accessToken) finalHeaders.Authorization = `Bearer ${accessToken}`

  try {
    return await fetch(`${BASE_URL}${path}`, { method, body, headers: finalHeaders, signal: controller.signal })
  } catch (err) {
    if (signal?.aborted) throw err // the caller cancelled on purpose: pass it through untouched
    if (err?.name === 'TimeoutError' || controller.signal.reason?.name === 'TimeoutError') {
      throw new ApiError({ code: 'TIMEOUT', message: 'This is taking too long. Please try again.' })
    }
    throw new ApiError({ code: 'NETWORK_ERROR', message: 'We could not reach NAADAMAYA. Check your connection.' })
  } finally {
    clearTimeout(timer)
  }
}

async function parseBody(response) {
  if (response.status === 204) return null
  const type = response.headers.get('content-type') || ''
  if (!type.includes('application/json')) return null
  try {
    return await response.json()
  } catch {
    return null
  }
}

/* ==========================================================
   Refresh (one at a time, shared)
   ========================================================== */
let refreshing = null

/** Exchanges the stored refresh token for a new pair. Resolves true on success. */
export function refreshSession() {
  if (refreshing) return refreshing

  refreshing = (async () => {
    const token = readRefresh()
    if (!token) return false

    // rawFetch throws ApiError(NETWORK_ERROR) on a network problem: that propagates,
    // and the session is kept so the user is not signed out by a bad connection.
    const response = await rawFetch('/auth/refresh', {
      method: 'POST',
      auth: false,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: token }),
    })

    if (response.ok) {
      const data = await parseBody(response)
      session.set(data)
      return true
    }
    if (response.status >= 500 || response.status === 429) {
      throw toApiError(response, await parseBody(response)) // temporary: keep the session
    }
    session.clear('refresh_rejected') // 401/403: the session is really over
    return false
  })().finally(() => {
    refreshing = null
  })

  return refreshing
}

/* ==========================================================
   Public request function
   ========================================================== */
async function request(path, options = {}) {
  const { json, form, idempotencyKey, auth = true, parse = 'json', ...rest } = options
  const headers = { ...(rest.headers || {}) }
  let body

  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = form // the browser sets the multipart boundary itself
  }
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey

  const send = () => rawFetch(path, { ...rest, headers, body, auth })

  // A reload loses the in-memory access token: get one before the first call.
  if (auth && !accessToken && readRefresh()) {
    await refreshSession()
  }

  let response = await send()

  if (auth && response.status === 401 && readRefresh()) {
    const refreshed = await refreshSession()
    if (refreshed) response = await send() // retried exactly once
  }

  if (!response.ok) {
    const err = toApiError(response, await parseBody(response))
    if (auth && err.status === 401 && !readRefresh()) session.clear('unauthenticated')
    throw err
  }

  if (parse === 'blob') return response.blob()
  return parseBody(response)
}

export const api = {
  get: (path, options) => request(path, { ...options, method: 'GET' }),
  post: (path, json, options) => request(path, { ...options, method: 'POST', json }),
  put: (path, json, options) => request(path, { ...options, method: 'PUT', json }),
  del: (path, json, options) => request(path, { ...options, method: 'DELETE', json }),
  /** multipart upload: pass a FormData. Longer timeout for audio. */
  upload: (path, form, options) =>
    request(path, { timeout: UPLOAD_TIMEOUT_MS, ...options, method: 'POST', form }),
  /** Files that need the token (audio, photo on local storage). Returns a Blob. */
  blob: (path, options) => request(path, { ...options, method: 'GET', parse: 'blob' }),
  /** Builds a query string, skipping empty values. */
  qs(params = {}) {
    const q = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && q.set(k, v))
    const s = q.toString()
    return s ? `?${s}` : ''
  },
}

/** A fresh key for "Start analysis", so a double-tap or retry cannot charge twice. */
export function newIdempotencyKey() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export default api
