import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight, User } from 'lucide-react'

import Button from '@/components/Button'
import { useAuth } from '@/context/AuthContext'
import { updateProfile } from '@/services/api/library'
import { cn } from '@/utils/cn'

/**
 * Minimal onboarding after a first sign-in. Everything is optional.
 *
 *   name, languages you sing in, experience level
 *
 * "Continue" saves what was entered and marks onboarding complete.
 * "Skip for now" only marks it complete. Nothing else is required to use
 * NAADAMAYA, and the rest of the profile can be filled in later on the
 * Profile screen.
 *
 * Both paths call PUT /profile with onboarding_completed=true, so the
 * server remembers it and the singer is not asked again.
 */

const LANGUAGES = ['Kannada', 'Hindi', 'English', 'Tamil', 'Telugu', 'Sanskrit']
const LEVELS = [
  { value: 'beginner', label: 'Beginner' },
  { value: 'intermediate', label: 'Intermediate' },
  { value: 'advanced', label: 'Advanced' },
  { value: 'professional', label: 'Professional' },
]

function Chip({ active, children, ...props }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        'rounded-pill border px-3.5 py-2 text-[0.85rem] font-medium transition-colors',
        active ? 'border-brown-400 bg-blush-100 text-brown-700' : 'border-gold-200 bg-ivory-50 text-brown-500 hover:bg-blush-50'
      )}
      {...props}
    >
      {children}
    </button>
  )
}

export default function Onboarding() {
  const navigate = useNavigate()
  const { finishOnboarding } = useAuth()

  const [name, setName] = useState('')
  const [languages, setLanguages] = useState([])
  const [level, setLevel] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const toggleLanguage = (lang) =>
    setLanguages((list) => (list.includes(lang) ? list.filter((l) => l !== lang) : [...list, lang]))

  const finish = async (save) => {
    setBusy(true)
    setError(null)
    const fields = { onboarding_completed: true }
    if (save) {
      if (name.trim()) fields.display_name = name.trim()
      if (languages.length) fields.preferred_languages = languages
      if (level) fields.experience_level = level
    }
    try {
      await updateProfile(fields)
      finishOnboarding()
      navigate('/', { replace: true })
    } catch (err) {
      setError(
        err?.code === 'VALIDATION_ERROR'
          ? 'Please check your name and try again.'
          : err?.message || 'Something went wrong. Please try again.'
      )
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto min-h-dvh w-full max-w-app px-4 py-10">
      <section className="nm-card animate-fade-up px-5 py-7 sm:px-7">
        <h1 className="font-serif text-[1.9rem] font-semibold leading-tight text-brown-900">Tell us about you</h1>
        <p className="nm-subtitle mt-2">All optional. You can change this any time on your profile.</p>

        <label className="mt-6 block">
          <span className="mb-1.5 block text-[0.78rem] font-medium text-brown-600">Your name</span>
          <span className="flex h-12 items-center gap-2 rounded-xl border border-gold-200 bg-ivory-50 px-3 focus-within:border-brown-400">
            <User className="h-4 w-4 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
              autoComplete="name"
              placeholder="e.g. V S Vighnesh"
              className="min-w-0 flex-1 bg-transparent text-[0.95rem] text-brown-900 outline-none placeholder:text-brown-300"
            />
          </span>
        </label>

        <fieldset className="mt-6">
          <legend className="mb-2 text-[0.78rem] font-medium text-brown-600">Languages you sing in</legend>
          <div className="flex flex-wrap gap-2">
            {LANGUAGES.map((lang) => (
              <Chip key={lang} active={languages.includes(lang)} onClick={() => toggleLanguage(lang)}>
                {lang}
              </Chip>
            ))}
          </div>
        </fieldset>

        <fieldset className="mt-6">
          <legend className="mb-2 text-[0.78rem] font-medium text-brown-600">Experience</legend>
          <div className="flex flex-wrap gap-2">
            {LEVELS.map((l) => (
              <Chip key={l.value} active={level === l.value} onClick={() => setLevel(level === l.value ? null : l.value)}>
                {l.label}
              </Chip>
            ))}
          </div>
        </fieldset>

        {error && (
          <p role="alert" className="mt-4 flex items-start gap-1.5 text-[0.82rem] text-status-bad">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={2} aria-hidden="true" />
            {error}
          </p>
        )}

        <Button variant="primary" size="lg" fullWidth loading={busy} rightIcon={ArrowRight} onClick={() => finish(true)} className="mt-6">
          Continue
        </Button>
        <Button variant="ghost" fullWidth disabled={busy} onClick={() => finish(false)} className="mt-2">
          Skip for now
        </Button>
      </section>
    </main>
  )
}
