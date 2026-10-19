import { useEffect, useState } from 'react'
import {
  AlarmClock,
  Bell,
  Camera,
  Check,
  CreditCard,
  Crown,
  Headphones,
  Languages,
  LogOut,
  Mail,
  Mic,
  Music,
  Palette,
  Phone,
  Receipt,
  Trash2,
  User,
} from 'lucide-react'

import Badge from '@/components/Badge'
import Button from '@/components/Button'
import Modal from '@/components/Modal'
import SettingsRow from '@/components/SettingsRow'
import StatisticsCard from '@/components/StatisticsCard'
import { useAppState } from '@/context/AppStateContext'
import { useAuth } from '@/context/AuthContext'
import { PREFERENCE_OPTIONS } from '@/data/mockProfileData'
import { deleteAccount } from '@/services/api/auth'
import { getPayments } from '@/services/api/billing'
import { updateProfile as saveProfileFields } from '@/services/api/library'
import { cn } from '@/utils/cn'
import { formatDate, formatPrice, getInitials, pluralize } from '@/utils/formatters'

/**
 * Profile: personal information, vocal profile, preferences and account.
 * Server-backed: name, email, photo, languages, genres, vocal range, payments.
 * Device-only: the Preferences section (no backend setting exists for them).
 */

const NOTE_RE = /^[A-Ga-g][#b]?-?[0-9]$/

function Section({ title, subtitle, children }) {
  return (
    <section aria-label={title} className="animate-fade-up">
      <h2 className="font-serif text-[1.45rem] font-semibold leading-none text-brown-900 md:text-[1.7rem]">{title}</h2>
      {subtitle && <p className="mt-1.5 text-[0.85rem] leading-snug text-brown-500">{subtitle}</p>}
      <div className="mt-3.5">{children}</div>
    </section>
  )
}

function Toggle({ checked, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn('relative h-7 w-12 shrink-0 rounded-full transition-colors duration-200', checked ? 'bg-sage-500' : 'bg-brown-200')}
    >
      <span
        className={cn(
          'absolute left-0.5 top-0.5 h-6 w-6 rounded-full bg-white shadow-soft transition-transform duration-200',
          checked && 'translate-x-5'
        )}
      />
    </button>
  )
}

function RowSelect({ value, options, onChange, label }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
      className="h-9 max-w-[10rem] cursor-pointer rounded-lg border border-gold-100 bg-ivory-100 px-2 text-[0.82rem] font-medium text-brown-800 outline-none hover:bg-blush-50"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  )
}

function InfoTile({ label, value }) {
  return (
    <div className="rounded-xl border border-gold-100/70 bg-ivory-50/80 px-3 py-2.5">
      <p className="text-[0.72rem] leading-none text-brown-500">{label}</p>
      <p className="mt-1.5 font-serif text-[1.2rem] font-semibold leading-none text-brown-900">{value || '\u2014'}</p>
    </div>
  )
}

function Field({ label, icon: Icon, hint, ...props }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[0.78rem] font-medium text-brown-600">{label}</span>
      <span className="flex h-11 items-center gap-2 rounded-xl border border-gold-200 bg-ivory-50 px-3 focus-within:border-brown-300">
        {Icon && <Icon className="h-4 w-4 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />}
        <input
          {...props}
          className="min-w-0 flex-1 bg-transparent text-[0.92rem] text-brown-900 outline-none placeholder:text-brown-300"
        />
      </span>
      {hint && <span className="mt-1 block text-[0.72rem] text-brown-400">{hint}</span>}
    </label>
  )
}

const splitList = (text) =>
  text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)

function errorText(err) {
  if (err?.code === 'USERNAME_TAKEN') return 'That username is already taken.'
  if (err?.code === 'VALIDATION_ERROR') {
    const first = err.details?.fields?.[0]
    return first ? `${first.field}: ${first.message}` : 'Please check the details and try again.'
  }
  return err?.message || 'Something went wrong. Please try again.'
}

export default function Profile() {
  const { signOut } = useAuth()
  const { profile, stats, credits, preferences, updatePreferences, setProfilePhoto, refreshAccount } = useAppState()

  const raw = profile.raw || {}
  const planName = credits.plan ? credits.plan.charAt(0).toUpperCase() + credits.plan.slice(1) : 'Free'

  const [editOpen, setEditOpen] = useState(false)
  const [draft, setDraft] = useState({ name: '', email: '' })
  const [vocalOpen, setVocalOpen] = useState(false)
  const [vocal, setVocal] = useState({ low: '', high: '', languages: '', genres: '' })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)
  const [photoError, setPhotoError] = useState(null)

  const [logoutOpen, setLogoutOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteText, setDeleteText] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  const [payments, setPayments] = useState(null)
  useEffect(() => {
    let alive = true
    getPayments({ page_size: 5 })
      .then((page) => alive && setPayments(page))
      .catch(() => alive && setPayments({ items: [], total: 0 }))
    return () => {
      alive = false
    }
  }, [])

  /* ---------- personal information ---------- */
  const openEdit = () => {
    setDraft({ name: profile.name, email: profile.email })
    setFormError(null)
    setEditOpen(true)
  }

  const saveEdit = async () => {
    setSaving(true)
    setFormError(null)
    try {
      await saveProfileFields({ display_name: draft.name.trim() || null, email: draft.email.trim() || null })
      await refreshAccount()
      setEditOpen(false)
    } catch (err) {
      setFormError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  const handlePhoto = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setPhotoError(null)
    try {
      await setProfilePhoto(file)
    } catch (err) {
      setPhotoError(errorText(err))
    }
  }

  /* ---------- vocal profile ---------- */
  const openVocal = () => {
    setVocal({
      low: raw.vocal_range_low || '',
      high: raw.vocal_range_high || '',
      languages: (raw.preferred_languages || []).join(', '),
      genres: (raw.preferred_genres || []).join(', '),
    })
    setFormError(null)
    setVocalOpen(true)
  }

  const saveVocal = async () => {
    for (const note of [vocal.low, vocal.high]) {
      if (note && !NOTE_RE.test(note.trim())) {
        setFormError('Notes should look like C3, A#4 or Bb2.')
        return
      }
    }
    setSaving(true)
    setFormError(null)
    try {
      await saveProfileFields({
        vocal_range_low: vocal.low.trim() || null,
        vocal_range_high: vocal.high.trim() || null,
        preferred_languages: splitList(vocal.languages),
        preferred_genres: splitList(vocal.genres),
      })
      await refreshAccount()
      setVocalOpen(false)
    } catch (err) {
      setFormError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  /* ---------- account ---------- */
  const handleLogout = async () => {
    setLoggingOut(true)
    await signOut()
  }

  const handleDelete = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteAccount() // clears the session; the route guard returns to sign-in
    } catch (err) {
      setDeleteError(errorText(err))
      setDeleting(false)
    }
  }

  const languages = raw.preferred_languages || []
  const genres = raw.preferred_genres || []

  return (
    <div className="-mt-8 md:-mt-12">
      <div className="animate-fade-up">
        <h1 className="nm-title">Profile</h1>
        <p className="nm-subtitle mt-2 max-w-[34rem]">Your details, voice and preferences.</p>
      </div>

      <div className="mt-5 flex flex-col gap-6">
        {/* Personal information */}
        <Section title="Personal Information">
          <div className="nm-card p-4 sm:p-5">
            <div className="flex items-center gap-4">
              <div className="relative shrink-0">
                <span className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-full border-2 border-ivory-50 bg-sage-100 shadow-card">
                  {profile.avatarUrl ? (
                    <img src={profile.avatarUrl} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <span className="font-serif text-[1.9rem] font-semibold text-sage-600">
                      {getInitials(profile.name) || <User className="h-8 w-8" />}
                    </span>
                  )}
                </span>
                <label className="absolute -bottom-0.5 -right-0.5 flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border-2 border-ivory-50 bg-brown-600 text-ivory-50 shadow-soft hover:scale-105">
                  <Camera className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
                  <span className="sr-only">Change profile photo</span>
                  <input type="file" accept="image/jpeg,image/png,image/webp" onChange={handlePhoto} className="sr-only" />
                </label>
              </div>

              <div className="min-w-0 flex-1">
                <p className="truncate font-serif text-[1.45rem] font-semibold leading-tight text-brown-900">
                  {profile.name || 'Add your name'}
                </p>
                <Badge variant="gold" size="sm" className="mt-1.5">
                  {planName} Account
                </Badge>
              </div>
            </div>
            {photoError && (
              <p role="alert" className="mt-2 text-[0.8rem] text-status-bad">
                {photoError}
              </p>
            )}

            <div className="mt-4 flex flex-col gap-2">
              <SettingsRow icon={User} title="Name" value={profile.name || 'Not added'} chevron={false} />
              <SettingsRow icon={Mail} title="Email" value={profile.email || 'Not added'} chevron={false} />
              <SettingsRow icon={Phone} title="Phone" value={profile.phone} chevron={false} />
            </div>

            <Button variant="secondary" onClick={openEdit} fullWidth className="mt-4">
              Edit personal information
            </Button>
          </div>
        </Section>

        {/* Vocal profile */}
        <Section
          title="Vocal Profile"
          subtitle="Entered by you. NAADAMAYA does not measure your range yet."
        >
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            <InfoTile label="Lowest Note" value={raw.vocal_range_low} />
            <InfoTile label="Highest Note" value={raw.vocal_range_high} />
            <InfoTile label="Experience" value={raw.experience_level ? raw.experience_level.charAt(0).toUpperCase() + raw.experience_level.slice(1) : null} />
          </div>

          <div className="nm-card mt-3 p-4">
            <p className="nm-eyebrow">Preferred Languages</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {languages.length ? (
                languages.map((l) => (
                  <Badge key={l} variant="mist" size="sm">
                    {l}
                  </Badge>
                ))
              ) : (
                <span className="text-[0.82rem] text-brown-400">Not set</span>
              )}
            </div>
            <p className="nm-eyebrow mt-4">Preferred Genres</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {genres.length ? (
                genres.map((g) => (
                  <Badge key={g} variant="blush" size="sm">
                    {g}
                  </Badge>
                ))
              ) : (
                <span className="text-[0.82rem] text-brown-400">Not set</span>
              )}
            </div>
            <Button variant="secondary" size="sm" onClick={openVocal} className="mt-4">
              Edit vocal profile
            </Button>
          </div>

          <div className="mt-3">
            <StatisticsCard
              items={[
                { id: 'practiced', label: 'Songs Practiced', value: stats.songsPracticed, icon: Music },
                { id: 'recorded', label: 'Songs Recorded', value: stats.songsRecorded, icon: Mic },
              ]}
            />
          </div>
        </Section>

        {/* Preferences (this device only) */}
        <Section title="Preferences" subtitle="Saved on this device only.">
          <div className="flex flex-col gap-2">
            <SettingsRow
              icon={Languages}
              title="Language"
              control={<RowSelect label="Language" value={preferences.language} options={PREFERENCE_OPTIONS.language} onChange={(v) => updatePreferences({ language: v })} />}
            />
            <SettingsRow
              icon={Bell}
              title="Notifications"
              description="Practice tips and report alerts"
              control={<Toggle label="Notifications" checked={preferences.notifications} onChange={(v) => updatePreferences({ notifications: v })} />}
            />
            <SettingsRow
              icon={AlarmClock}
              title="Reminders"
              control={<RowSelect label="Reminder preference" value={preferences.reminders} options={PREFERENCE_OPTIONS.reminders} onChange={(v) => updatePreferences({ reminders: v })} />}
            />
            <SettingsRow
              icon={Palette}
              title="Theme"
              description="Only Light is designed so far"
              control={<RowSelect label="Theme" value={preferences.theme} options={PREFERENCE_OPTIONS.theme} onChange={(v) => updatePreferences({ theme: v })} />}
            />
            <SettingsRow
              icon={Headphones}
              title="Audio Quality"
              control={<RowSelect label="Audio quality" value={preferences.audioQuality} options={PREFERENCE_OPTIONS.audioQuality} onChange={(v) => updatePreferences({ audioQuality: v })} />}
            />
          </div>
        </Section>

        {/* Account */}
        <Section title="Account">
          <div className="flex flex-col gap-2">
            <SettingsRow icon={Crown} title="Membership" value={planName} to="/stage" />
            <SettingsRow icon={CreditCard} title="Credits" value={`${pluralize(credits.remaining, 'credit')} left`} to="/credits" />
            <SettingsRow
              icon={Receipt}
              title="Payment History"
              value={payments === null ? 'Loading...' : payments.total ? `${payments.total} payment${payments.total === 1 ? '' : 's'}` : 'No payments yet'}
              chevron={false}
            />
            <SettingsRow icon={LogOut} title="Logout" description="Sign out from your account" danger onClick={() => setLogoutOpen(true)} />
            <SettingsRow
              icon={Trash2}
              title="Delete account"
              description="Permanently remove your data"
              danger
              onClick={() => {
                setDeleteText('')
                setDeleteError(null)
                setDeleteOpen(true)
              }}
            />
          </div>

          {payments?.items?.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1.5">
              {payments.items.map((p) => (
                <li key={p.id} className="flex justify-between gap-3 rounded-xl border border-gold-100/70 bg-ivory-50/70 px-3 py-2 text-[0.85rem] text-brown-700">
                  <span>
                    {p.plan_name || 'Plan'} {'\u00B7'} {p.status}
                  </span>
                  <span className="shrink-0">
                    {formatDate(p.verified_at || p.created_at)} {'\u00B7'} {formatPrice(p.price)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      {/* Edit personal information */}
      <Modal
        open={editOpen}
        onClose={() => !saving && setEditOpen(false)}
        icon={User}
        title="Edit Profile"
        subtitle="Your phone number is your account and cannot be changed here."
        footer={
          <div className="flex gap-2.5">
            <Button variant="ghost" onClick={() => setEditOpen(false)} disabled={saving} className="flex-1">
              Cancel
            </Button>
            <Button variant="primary" leftIcon={Check} loading={saving} onClick={saveEdit} className="flex-[1.4]">
              Save
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3.5 pb-1">
          <Field label="Name" icon={User} value={draft.name} maxLength={80} autoComplete="name" onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
          <Field label="Email (optional)" icon={Mail} type="email" value={draft.email} autoComplete="email" onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))} />
          {formError && <p role="alert" className="text-[0.82rem] text-status-bad">{formError}</p>}
        </div>
      </Modal>

      {/* Edit vocal profile */}
      <Modal
        open={vocalOpen}
        onClose={() => !saving && setVocalOpen(false)}
        icon={Mic}
        title="Vocal Profile"
        subtitle="Leave a field empty to clear it."
        footer={
          <div className="flex gap-2.5">
            <Button variant="ghost" onClick={() => setVocalOpen(false)} disabled={saving} className="flex-1">
              Cancel
            </Button>
            <Button variant="primary" leftIcon={Check} loading={saving} onClick={saveVocal} className="flex-[1.4]">
              Save
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3.5 pb-1">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Lowest note" value={vocal.low} placeholder="C3" maxLength={4} onChange={(e) => setVocal((v) => ({ ...v, low: e.target.value }))} />
            <Field label="Highest note" value={vocal.high} placeholder="A4" maxLength={4} onChange={(e) => setVocal((v) => ({ ...v, high: e.target.value }))} />
          </div>
          <Field label="Languages you sing in" icon={Languages} value={vocal.languages} placeholder="Kannada, Hindi" hint="Separate with commas" onChange={(e) => setVocal((v) => ({ ...v, languages: e.target.value }))} />
          <Field label="Genres" value={vocal.genres} placeholder="Devotional, Light classical" hint="Separate with commas" onChange={(e) => setVocal((v) => ({ ...v, genres: e.target.value }))} />
          {formError && <p role="alert" className="text-[0.82rem] text-status-bad">{formError}</p>}
        </div>
      </Modal>

      {/* Logout */}
      <Modal
        open={logoutOpen}
        onClose={() => !loggingOut && setLogoutOpen(false)}
        icon={LogOut}
        title="Log out?"
        subtitle="You can sign back in any time with your phone number."
        size="sm"
        footer={
          <div className="flex gap-2.5">
            <Button variant="secondary" onClick={() => setLogoutOpen(false)} disabled={loggingOut} className="flex-1">
              Stay
            </Button>
            <Button variant="danger" leftIcon={LogOut} loading={loggingOut} onClick={handleLogout} className="flex-1">
              Log out
            </Button>
          </div>
        }
      >
        <p className="pb-1 text-[0.88rem] leading-snug text-brown-600">Your reports and attempt history stay saved with your account.</p>
      </Modal>

      {/* Delete account */}
      <Modal
        open={deleteOpen}
        onClose={() => !deleting && setDeleteOpen(false)}
        icon={Trash2}
        title="Delete your account?"
        subtitle="This cannot be undone."
        size="sm"
        footer={
          <div className="flex gap-2.5">
            <Button variant="secondary" onClick={() => setDeleteOpen(false)} disabled={deleting} className="flex-1">
              Keep account
            </Button>
            <Button variant="danger" leftIcon={Trash2} loading={deleting} disabled={deleteText.trim().toUpperCase() !== 'DELETE'} onClick={handleDelete} className="flex-1">
              Delete
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3 pb-1">
          <p className="text-[0.88rem] leading-snug text-brown-600">
            Your songs, recordings, reports and profile will be permanently deleted and every device signed out.
            Payment records are kept, unlinked from your identity, for legal and accounting reasons.
          </p>
          <Field label='Type DELETE to confirm' value={deleteText} autoComplete="off" onChange={(e) => setDeleteText(e.target.value)} />
          {deleteError && <p role="alert" className="text-[0.82rem] text-status-bad">{deleteError}</p>}
        </div>
      </Modal>
    </div>
  )
}
