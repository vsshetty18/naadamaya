import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { AlertCircle, ArrowLeft, ArrowRight, Loader2, Phone } from 'lucide-react'

import Button from '@/components/Button'
import HeroArt from '@/components/HeroArt'
import logoMark from '@/assets/logo-mark.png'
import { useAuth } from '@/context/AuthContext'
import { sendOtp, verifyOtp } from '@/services/api/auth'
import { cn } from '@/utils/cn'

/**
 * Sign in with a phone number and a one-time code. No passwords, no email.
 *
 *   Step 1  "Welcome to NAADAMAYA": phone number, Continue
 *   Step 2  "OTP verification": 6 boxes, Verify, resend timer
 *
 * The same flow creates the account the first time and signs in afterwards:
 * the backend decides from the phone number. A brand-new account is sent to
 * onboarding by ProtectedRoute.
 *
 * All rules (limits, expiry, attempts) are enforced by the backend. This
 * screen only shows what it says. The development code is shown only when
 * the server returns one, which it never does in production.
 */

const OTP_LENGTH = 6
const COUNTRY_PREFIX = '+91'

/** "98765 43210" -> "+9198765 43210". A number typed with its own "+" is sent as typed. */
function toPhone(input) {
  const text = input.trim()
  return text.startsWith('+') ? text : `${COUNTRY_PREFIX}${text.replace(/\D/g, '')}`
}

function errorMessage(err) {
  if (err?.isNetwork) return 'We could not reach NAADAMAYA. Check your connection and try again.'
  switch (err?.code) {
    case 'INVALID_PHONE_NUMBER':
      return err.message
    case 'OTP_RATE_LIMITED':
      return err.retryAfter && err.retryAfter < 600
        ? `Please wait ${err.retryAfter} seconds and try again.`
        : err.message
    case 'INVALID_OTP':
      return 'That code is not correct. Please check it and try again.'
    case 'OTP_EXPIRED':
      return 'That code has expired. Request a new one.'
    case 'ACCOUNT_DISABLED':
      return 'This account is not active.'
    default:
      return err?.message || 'Something went wrong. Please try again.'
  }
}

/* ==========================================================
   The six code boxes
   ========================================================== */
function CodeInput({ value, onChange, onComplete, disabled, hasError }) {
  const refs = useRef([])
  const digits = Array.from({ length: OTP_LENGTH }, (_, i) => value[i] || '')

  const focus = (i) => refs.current[Math.max(0, Math.min(OTP_LENGTH - 1, i))]?.focus()

  const update = (next) => {
    onChange(next)
    if (next.length === OTP_LENGTH) onComplete?.(next)
  }

  const handleChange = (i, e) => {
    const typed = e.target.value.replace(/\D/g, '')
    if (!typed) return
    // Several digits at once (paste, or a code suggested by the phone) fill the boxes in order.
    const next = (value.slice(0, i) + typed).slice(0, OTP_LENGTH)
    update(next)
    focus(next.length >= OTP_LENGTH ? OTP_LENGTH - 1 : next.length)
  }

  const handleKeyDown = (i, e) => {
    if (e.key === 'Backspace') {
      e.preventDefault()
      if (digits[i]) update(value.slice(0, i) + value.slice(i + 1))
      else if (i > 0) {
        update(value.slice(0, i - 1) + value.slice(i))
        focus(i - 1)
      }
    } else if (e.key === 'ArrowLeft') focus(i - 1)
    else if (e.key === 'ArrowRight') focus(i + 1)
  }

  const handlePaste = (e) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_LENGTH)
    if (!pasted) return
    e.preventDefault()
    update(pasted)
    focus(pasted.length >= OTP_LENGTH ? OTP_LENGTH - 1 : pasted.length)
  }

  return (
    <div className="flex justify-center gap-2 sm:gap-2.5" role="group" aria-label="6-digit code">
      {digits.map((digit, i) => (
        <input
          key={i}
          ref={(el) => (refs.current[i] = el)}
          value={digit}
          onChange={(e) => handleChange(i, e)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={handlePaste}
          onFocus={(e) => e.target.select()}
          disabled={disabled}
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={OTP_LENGTH}
          aria-label={`Digit ${i + 1}`}
          autoFocus={i === 0}
          className={cn(
            'h-[3.4rem] w-[2.7rem] rounded-xl border bg-ivory-50 text-center font-serif text-[1.6rem] font-semibold text-brown-900',
            'outline-none transition-colors disabled:opacity-60 sm:h-14 sm:w-12',
            hasError ? 'border-status-bad' : digit ? 'border-brown-300' : 'border-gold-200',
            'focus:border-brown-400 focus:ring-2 focus:ring-gold-300/60'
          )}
        />
      ))}
    </div>
  )
}

/* ==========================================================
   The page
   ========================================================== */
export default function Login() {
  const { status, signIn } = useAuth()
  const location = useLocation()
  const destination = location.state?.from || '/'

  const [step, setStep] = useState('phone') // 'phone' | 'code'
  const [phoneInput, setPhoneInput] = useState('')
  const [sent, setSent] = useState(null) // response of send-otp
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [cooldown, setCooldown] = useState(0)

  // Resend countdown.
  useEffect(() => {
    if (cooldown <= 0) return undefined
    const timer = setTimeout(() => setCooldown((c) => c - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  const requestCode = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await sendOtp(toPhone(phoneInput))
      setSent(result)
      setCooldown(result.resend_after || 30)
      setCode('')
      setStep('code')
    } catch (err) {
      setError(errorMessage(err))
      if (err?.code === 'OTP_RATE_LIMITED' && err.retryAfter && err.retryAfter < 600) setCooldown(err.retryAfter)
    } finally {
      setBusy(false)
    }
  }, [phoneInput])

  const submitCode = useCallback(
    async (value) => {
      if (busy || value.length !== OTP_LENGTH) return
      setBusy(true)
      setError(null)
      try {
        const result = await verifyOtp(toPhone(phoneInput), value)
        signIn(result) // status becomes 'authenticated' and the redirect below takes over
      } catch (err) {
        setError(errorMessage(err))
        if (err?.code !== 'NETWORK_ERROR') setCode('')
        setBusy(false)
      }
    },
    [busy, phoneInput, signIn]
  )

  // Already signed in (or just signed in): leave this screen.
  if (status === 'authenticated') return <Navigate to={destination} replace />

  const phoneDigits = phoneInput.replace(/\D/g, '')
  const phoneReady = phoneInput.trim().startsWith('+') ? phoneDigits.length >= 8 : phoneDigits.length === 10

  return (
    <div className="relative min-h-dvh">
      {/* Hero with the logo */}
      <div className="relative isolate h-56 overflow-hidden sm:h-64">
        <HeroArt className="absolute inset-0 -z-10" />
        <div className="safe-top">
          <div className="mx-auto flex max-w-desktop items-center gap-3 px-4 pt-5 md:px-8">
            <span className="flex h-[3.4rem] w-[3.4rem] shrink-0 items-center justify-center rounded-full border border-brown-300/70 bg-ivory-50/70 shadow-soft md:h-16 md:w-16">
              <img src={logoMark} alt="" className="h-[2.5rem] w-[2.5rem] object-contain md:h-12 md:w-12" draggable="false" />
            </span>
            <span className="flex flex-col">
              <span className="nm-wordmark text-[1.35rem] leading-none sm:text-[1.7rem] md:text-[2rem]">NAADAMAYA</span>
              <span className="nm-tagline mt-1.5 text-[0.52rem] sm:text-[0.6rem] md:text-[0.68rem]">sing. evolve. globally.</span>
            </span>
          </div>
        </div>
      </div>

      <main className="mx-auto -mt-6 w-full max-w-app px-4 pb-10">
        <section className="nm-card animate-fade-up px-5 py-7 sm:px-7">
          {step === 'phone' ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                if (phoneReady && !busy) requestCode()
              }}
              noValidate
            >
              <h1 className="font-serif text-[1.9rem] font-semibold leading-tight text-brown-900">
                Welcome to NAADAMAYA
              </h1>
              <p className="nm-subtitle mt-2">Enter your phone number. We will send you a code to sign in.</p>

              <label className="mt-6 block">
                <span className="mb-1.5 block text-[0.78rem] font-medium text-brown-600">Phone number</span>
                <span
                  className={cn(
                    'flex h-[3.2rem] items-center gap-2 rounded-xl border bg-ivory-50 px-3 focus-within:border-brown-400 focus-within:ring-2 focus-within:ring-gold-300/60',
                    error ? 'border-status-bad' : 'border-gold-200'
                  )}
                >
                  <Phone className="h-4 w-4 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
                  <span className="border-r border-gold-200 pr-2 text-[0.95rem] font-medium text-brown-700">{COUNTRY_PREFIX}</span>
                  <input
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel-national"
                    autoFocus
                    value={phoneInput}
                    onChange={(e) => {
                      setPhoneInput(e.target.value)
                      setError(null)
                    }}
                    placeholder="98765 43210"
                    maxLength={20}
                    aria-label="Phone number"
                    aria-invalid={Boolean(error)}
                    className="min-w-0 flex-1 bg-transparent text-[1.05rem] tracking-wide text-brown-900 outline-none placeholder:text-brown-300"
                  />
                </span>
              </label>

              {error && <ErrorLine message={error} />}

              <Button
                type="submit"
                variant="primary"
                size="lg"
                fullWidth
                loading={busy}
                disabled={!phoneReady}
                rightIcon={ArrowRight}
                className="mt-5"
              >
                {busy ? 'Sending code...' : 'Continue'}
              </Button>

              <p className="mt-4 text-center text-[0.75rem] leading-snug text-brown-400">
                One phone number is one NAADAMAYA account.
              </p>
            </form>
          ) : (
            <div>
              <button
                type="button"
                onClick={() => {
                  setStep('phone')
                  setError(null)
                  setCode('')
                }}
                className="-ml-1 mb-3 flex items-center gap-1 rounded-lg px-1 py-1 text-[0.85rem] text-brown-500 hover:text-brown-700"
              >
                <ArrowLeft className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
                Change number
              </button>

              <h1 className="font-serif text-[1.9rem] font-semibold leading-tight text-brown-900">OTP verification</h1>
              <p className="nm-subtitle mt-2">
                Enter the 6-digit code sent to <span className="whitespace-nowrap font-medium text-brown-800">{sent?.masked_phone}</span>
              </p>

              <div className="mt-6">
                <CodeInput value={code} onChange={setCode} onComplete={submitCode} disabled={busy} hasError={Boolean(error)} />
              </div>

              {sent?.development_otp && (
                <p className="mt-3 rounded-lg border border-gold-200 bg-gold-50 px-3 py-2 text-center text-[0.78rem] text-brown-600">
                  Development mode: your code is <span className="font-semibold tabular-nums">{sent.development_otp}</span>
                </p>
              )}

              {error && <ErrorLine message={error} center />}

              <Button
                variant="primary"
                size="lg"
                fullWidth
                loading={busy}
                disabled={code.length !== OTP_LENGTH}
                onClick={() => submitCode(code)}
                className="mt-5"
              >
                {busy ? 'Verifying...' : 'Verify'}
              </Button>

              <div className="mt-4 text-center text-[0.85rem] text-brown-500">
                {cooldown > 0 ? (
                  <span aria-live="polite">Resend code in {cooldown}s</span>
                ) : (
                  <button
                    type="button"
                    onClick={requestCode}
                    disabled={busy}
                    className="font-medium text-brown-600 underline-offset-2 hover:underline disabled:opacity-60"
                  >
                    {busy ? <Loader2 className="inline h-4 w-4 animate-spin" aria-hidden="true" /> : 'Resend code'}
                  </button>
                )}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

function ErrorLine({ message, center = false }) {
  return (
    <p role="alert" className={cn('mt-3 flex items-start gap-1.5 text-[0.82rem] text-status-bad', center && 'justify-center text-center')}>
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
      {message}
    </p>
  )
}
