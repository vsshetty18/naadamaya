import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bell,
  Camera,
  Check,
  CreditCard,
  Crown,
  Headphones,
  LogOut,
  Mail,
  Mic,
  Music,
  Palette,
  Phone,
  Receipt,
  User,
  Languages,
  AlarmClock,
} from 'lucide-react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import SettingsRow from '@/components/SettingsRow'
import StatisticsCard from '@/components/StatisticsCard'
import Badge from '@/components/Badge'
import { getPlan } from '@/data/plans'
import {
  MOCK_PAYMENT_HISTORY,
  MOCK_VOCAL_PROFILE,
  PREFERENCE_OPTIONS,
} from '@/data/mockProfileData'
import { useAppState } from '@/context/AppStateContext'
import { cn } from '@/utils/cn'
import { formatDate, formatPrice, getInitials, pluralize } from '@/utils/formatters'

/**
 * Profile: personal information, vocal profile, preferences and account.
 *
 * Personal details and preferences are edited in AppStateContext (frontend
 * state only, nothing is saved anywhere). The vocal profile is mock data.
 */

function Section({ title, subtitle, children }) {
  return (
    <section aria-label={title} className="animate-fade-up">
      <h2 className="font-serif text-[1.45rem] font-semibold leading-none text-brown-900 md:text-[1.7rem]">
        {title}
      </h2>
      {subtitle && <p className="mt-1.5 text-[0.85rem] leading-snug text-brown-500">{subtitle}</p>}
      <div className="mt-3.5">{children}</div>
    </section>
  )
}

/** Small on/off switch. */
function Toggle({ checked, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-7 w-12 shrink-0 rounded-full transition-colors duration-200',
        checked ? 'bg-sage-500' : 'bg-brown-200'
      )}
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

/** Native select styled to sit inside a settings row. */
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
      <p className="mt-1.5 font-serif text-[1.2rem] font-semibold leading-none text-brown-900">{value}</p>
    </div>
  )
}

function Field({ label, icon: Icon, ...props }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[0.78rem] font-medium text-brown-600">{label}</span>
      <span className="flex h-11 items-center gap-2 rounded-xl border border-gold-200 bg-ivory-50 px-3 focus-within:border-brown-300">
        <Icon className="h-4 w-4 shrink-0 text-brown-400" strokeWidth={1.8} aria-hidden="true" />
        <input
          {...props}
          className="min-w-0 flex-1 bg-transparent text-[0.92rem] text-brown-900 outline-none placeholder:text-brown-300"
        />
      </span>
    </label>
  )
}

export default function Profile() {
  const navigate = useNavigate()
  const { profile, updateProfile, stats, credits, preferences, updatePreferences } = useAppState()

  const [editOpen, setEditOpen] = useState(false)
  const [draft, setDraft] = useState(profile)
  const [logoutOpen, setLogoutOpen] = useState(false)

  const plan = getPlan(credits.plan)
  const vocal = MOCK_VOCAL_PROFILE

  const openEdit = () => {
    setDraft(profile)
    setEditOpen(true)
  }

  const saveEdit = () => {
    updateProfile({
      name: draft.name.trim() || profile.name,
      email: draft.email.trim(),
      phone: draft.phone.trim(),
    })
    setEditOpen(false)
  }

  const handlePhoto = (e) => {
    const file = e.target.files?.[0]
    if (!file || !file.type.startsWith('image/')) return
    // Frontend only: the photo lives in this browser session.
    setDraft((d) => ({ ...d, avatarUrl: URL.createObjectURL(file) }))
    updateProfile({ avatarUrl: URL.createObjectURL(file) })
    e.target.value = ''
  }

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
                  <input type="file" accept="image/*" onChange={handlePhoto} className="sr-only" />
                </label>
              </div>

              <div className="min-w-0 flex-1">
                <p className="truncate font-serif text-[1.45rem] font-semibold leading-tight text-brown-900">
                  {profile.name}
                </p>
                <Badge variant="gold" size="sm" className="mt-1.5">
                  {plan ? `${plan.name} Account` : 'Free Account'}
                </Badge>
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-2">
              <SettingsRow icon={User} title="Name" value={profile.name} chevron={false} />
              <SettingsRow icon={Mail} title="Email" value={profile.email || 'Not added'} chevron={false} />
              <SettingsRow icon={Phone} title="Phone" value={profile.phone || 'Not added'} chevron={false} />
            </div>

            <Button variant="secondary" onClick={openEdit} fullWidth className="mt-4">
              Edit personal information
            </Button>
          </div>
        </Section>

        {/* Vocal profile */}
        <Section title="Vocal Profile" subtitle="Sample values for now. Naadamaya will learn your voice over time.">
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            <InfoTile label="Vocal Range" value={vocal.vocalRange} />
            <InfoTile label="Lowest Note" value={vocal.lowestNote} />
            <InfoTile label="Highest Note" value={vocal.highestNote} />
          </div>

          <div className="nm-card mt-3 p-4">
            <p className="nm-eyebrow">Preferred Languages</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {vocal.preferredLanguages.map((l) => (
                <Badge key={l} variant="mist" size="sm">
                  {l}
                </Badge>
              ))}
            </div>
            <p className="nm-eyebrow mt-4">Preferred Genres</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {vocal.preferredGenres.map((g) => (
                <Badge key={g} variant="blush" size="sm">
                  {g}
                </Badge>
              ))}
            </div>
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

        {/* Preferences */}
        <Section title="Preferences">
          <div className="flex flex-col gap-2">
            <SettingsRow
              icon={Languages}
              title="Language"
              control={
                <RowSelect
                  label="Language"
                  value={preferences.language}
                  options={PREFERENCE_OPTIONS.language}
                  onChange={(v) => updatePreferences({ language: v })}
                />
              }
            />
            <SettingsRow
              icon={Bell}
              title="Notifications"
              description="Practice tips and report alerts"
              control={
                <Toggle
                  label="Notifications"
                  checked={preferences.notifications}
                  onChange={(v) => updatePreferences({ notifications: v })}
                />
              }
            />
            <SettingsRow
              icon={AlarmClock}
              title="Reminders"
              control={
                <RowSelect
                  label="Reminder preference"
                  value={preferences.reminders}
                  options={PREFERENCE_OPTIONS.reminders}
                  onChange={(v) => updatePreferences({ reminders: v })}
                />
              }
            />
            <SettingsRow
              icon={Palette}
              title="Theme"
              description="Only Light is designed so far"
              control={
                <RowSelect
                  label="Theme"
                  value={preferences.theme}
                  options={PREFERENCE_OPTIONS.theme}
                  onChange={(v) => updatePreferences({ theme: v })}
                />
              }
            />
            <SettingsRow
              icon={Headphones}
              title="Audio Quality"
              control={
                <RowSelect
                  label="Audio quality"
                  value={preferences.audioQuality}
                  options={PREFERENCE_OPTIONS.audioQuality}
                  onChange={(v) => updatePreferences({ audioQuality: v })}
                />
              }
            />
          </div>
        </Section>

        {/* Account */}
        <Section title="Account">
          <div className="flex flex-col gap-2">
            <SettingsRow
              icon={Crown}
              title="Membership"
              value={plan ? plan.name : 'Free'}
              to="/stage"
            />
            <SettingsRow
              icon={CreditCard}
              title="Credits"
              value={`${pluralize(credits.remaining, 'credit')} left`}
              to="/credits"
            />
            <SettingsRow
              icon={Receipt}
              title="Payment History"
              value={MOCK_PAYMENT_HISTORY.length ? `${MOCK_PAYMENT_HISTORY.length} payments` : 'No payments yet'}
              chevron={false}
            />
            <SettingsRow
              icon={LogOut}
              title="Logout"
              description="Sign out from your account"
              danger
              onClick={() => setLogoutOpen(true)}
            />
          </div>

          {MOCK_PAYMENT_HISTORY.length > 0 && (
            <ul className="mt-3 flex flex-col gap-1.5">
              {MOCK_PAYMENT_HISTORY.map((p) => (
                <li key={p.id} className="flex justify-between rounded-xl border border-gold-100/70 bg-ivory-50/70 px-3 py-2 text-[0.85rem] text-brown-700">
                  <span>{p.description}</span>
                  <span>
                    {formatDate(p.date)} {'\u00B7'} {formatPrice(p.amount)}
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
        onClose={() => setEditOpen(false)}
        icon={User}
        title="Edit Profile"
        subtitle="Changes stay in this browser for now."
        footer={
          <div className="flex gap-2.5">
            <Button variant="ghost" onClick={() => setEditOpen(false)} className="flex-1">
              Cancel
            </Button>
            <Button variant="primary" leftIcon={Check} onClick={saveEdit} className="flex-[1.4]">
              Save
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3.5 pb-1">
          <Field
            label="Name"
            icon={User}
            value={draft.name}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            autoComplete="name"
          />
          <Field
            label="Email"
            icon={Mail}
            type="email"
            value={draft.email}
            onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
            autoComplete="email"
          />
          <Field
            label="Phone"
            icon={Phone}
            type="tel"
            value={draft.phone}
            onChange={(e) => setDraft((d) => ({ ...d, phone: e.target.value }))}
            autoComplete="tel"
          />
        </div>
      </Modal>

      {/* Logout confirmation (mock) */}
      <Modal
        open={logoutOpen}
        onClose={() => setLogoutOpen(false)}
        icon={LogOut}
        title="Log out?"
        subtitle="You can sign back in any time."
        size="sm"
        footer={
          <div className="flex gap-2.5">
            <Button variant="secondary" onClick={() => setLogoutOpen(false)} className="flex-1">
              Stay
            </Button>
            <Button
              variant="danger"
              leftIcon={LogOut}
              onClick={() => {
                setLogoutOpen(false)
                navigate('/')
              }}
              className="flex-1"
            >
              Log out
            </Button>
          </div>
        }
      >
        <p className="pb-1 text-[0.88rem] leading-snug text-brown-600">
          Your reports and attempt history stay saved with your account.
        </p>
      </Modal>
    </div>
  )
}
