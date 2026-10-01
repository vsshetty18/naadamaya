import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, BarChart3, BookOpen, Music, Sparkles, User } from 'lucide-react'

import AudioUploadCard from '@/components/AudioUploadCard'
import Button from '@/components/Button'
import RecordModal from '@/components/RecordModal'
import UploadModal from '@/components/UploadModal'
import { useAppState } from '@/context/AppStateContext'
import { validateAudioInputs } from '@/services/analysisService'

/**
 * Learn: the singer provides the original song and their own voice,
 * then asks for a comparison report.
 *
 * This page only collects audio and starts a run. The processing screen and
 * the report itself live on the Report page. No analysis happens here.
 */

const SLOTS = {
  original: {
    key: 'original',
    title: 'Original',
    description: 'Upload the original song (reference).',
    icon: Music,
    tone: 'mist',
  },
  user: {
    key: 'user',
    title: 'Your Voice',
    description: 'Upload or record your singing.',
    icon: User,
    tone: 'sage',
  },
}

/** Small decorative feather and flute for the info card (kept subtle). */
function FeatherDecor({ className }) {
  return (
    <svg viewBox="0 0 60 90" className={className} aria-hidden="true">
      <g transform="rotate(20 30 45)">
        <path d="M30 6 C48 24 46 52 30 66 C14 52 12 24 30 6 Z" fill="#CBD9C1" opacity="0.7" />
        <ellipse cx="30" cy="34" rx="8" ry="12" fill="#EBD3A0" />
        <ellipse cx="30" cy="35" rx="4.5" ry="7.5" fill="#2F7186" opacity="0.8" />
        <path d="M30 66 C28 76 24 84 20 88" stroke="#A9BF9A" strokeWidth="1.4" fill="none" strokeLinecap="round" />
      </g>
    </svg>
  )
}

export default function Learn() {
  const navigate = useNavigate()
  const {
    original,
    userVoice,
    setAudio,
    clearAudio,
    runAnalysis,
    isProcessing,
  } = useAppState()

  const [uploadSlot, setUploadSlot] = useState(null) // 'original' | 'user' | null
  const [recordSlot, setRecordSlot] = useState(null)
  const [slotErrors, setSlotErrors] = useState({ original: null, user: null })
  const [simulate, setSimulate] = useState('') // dev only: force a failure screen

  const audioFor = { original, user: userVoice }

  const setSlotError = (slot, message) =>
    setSlotErrors((prev) => ({ ...prev, [slot]: message }))

  const handleConfirm = (slot) => (audio) => {
    setAudio(slot, audio)
    setSlotError(slot, null)
  }

  const handleRemove = (slot) => () => {
    clearAudio(slot)
    setSlotError(slot, null)
  }

  const handleReport = () => {
    // Already running: just go and watch it.
    if (isProcessing) {
      navigate('/report')
      return
    }

    // Flag every missing slot at once, next to the card that needs it.
    const missing = {
      original: original ? null : 'Add the original song to continue.',
      user: userVoice ? null : 'Add your singing to continue.',
    }
    if (missing.original || missing.user) {
      setSlotErrors(missing)
      return
    }

    // Format check (a missing slot was handled above).
    try {
      validateAudioInputs(original, userVoice)
    } catch (err) {
      const slot = err.details?.slot
      if (slot) setSlotError(slot, err.message)
      return
    }

    setSlotErrors({ original: null, user: null })

    // Start the run, then show its progress on the Report page.
    runAnalysis(simulate ? { simulate } : {})
    navigate('/report')
  }

  return (
    <div className="-mt-8 pb-2 md:-mt-12">
      {/* Title block */}
      <div className="relative animate-fade-up">
        <h1 className="nm-title">Learn</h1>
        <p className="nm-subtitle mt-2 max-w-[34rem] pr-10">
          Upload the original song and your voice to get a detailed comparison report and learn what to
          improve.
        </p>
        <FeatherDecor className="pointer-events-none absolute -top-2 right-0 h-20 w-12 opacity-50 md:h-28 md:w-16" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.35fr_1fr] lg:items-start lg:gap-8">
        {/* Inputs and CTA */}
        <div className="flex flex-col gap-3.5">
          {[SLOTS.original, SLOTS.user].map((slot, i) => (
            <AudioUploadCard
              key={slot.key}
              title={slot.title}
              description={slot.description}
              icon={slot.icon}
              tone={slot.tone}
              audio={audioFor[slot.key]}
              error={slotErrors[slot.key]}
              disabled={isProcessing}
              onUpload={() => setUploadSlot(slot.key)}
              onRecord={() => setRecordSlot(slot.key)}
              onRemove={handleRemove(slot.key)}
              className="stagger"
              style={{ '--d': i }}
            />
          ))}

          <Button
            variant="cta"
            leftIcon={BarChart3}
            rightIcon={ArrowRight}
            onClick={handleReport}
            fullWidth
            className="mt-1"
          >
            Report
          </Button>

          {/* Dev-only: preview the failure screens without breaking anything */}
          {import.meta.env.DEV && (
            <label className="flex items-center justify-between gap-3 rounded-xl border border-dashed border-gold-200 px-3 py-2 text-[0.75rem] text-brown-500">
              <span>Dev: simulate a failed run</span>
              <select
                value={simulate}
                onChange={(e) => setSimulate(e.target.value)}
                className="rounded-lg border border-gold-200 bg-ivory-50 px-2 py-1 text-[0.75rem] text-brown-700"
              >
                <option value="">None</option>
                <option value="failure">Analysis failed</option>
                <option value="timeout">Timeout</option>
                <option value="network">Network error</option>
              </select>
            </label>
          )}
        </div>

        {/* Information card */}
        <section className="nm-card relative overflow-hidden px-6 py-8 text-center animate-fade-up lg:py-12">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-gold-50/70" />

          <div className="relative mx-auto flex w-fit flex-col items-center">
            <Sparkles className="h-5 w-5 text-gold-400" strokeWidth={1.6} aria-hidden="true" />
            <BookOpen className="-mt-0.5 h-16 w-16 text-gold-500" strokeWidth={1.2} aria-hidden="true" />
          </div>

          <h2 className="relative mt-3 font-serif text-[1.45rem] font-semibold leading-snug text-brown-900 md:text-[1.7rem]">
            Your comparison report will show
          </h2>
          <p className="relative mt-1.5 font-serif text-[1.1rem] leading-snug text-brown-500 md:text-[1.25rem]">
            what all should be improved
            <br />
            to sound like the original.
          </p>

          <FeatherDecor className="pointer-events-none absolute -bottom-3 right-2 h-24 w-14 opacity-60" />
        </section>
      </div>

      {/* Modals (one of each, reused for both slots) */}
      <UploadModal
        open={uploadSlot !== null}
        title={uploadSlot ? SLOTS[uploadSlot].title : ''}
        onClose={() => setUploadSlot(null)}
        onConfirm={(audio) => uploadSlot && handleConfirm(uploadSlot)(audio)}
      />
      <RecordModal
        open={recordSlot !== null}
        title={recordSlot ? SLOTS[recordSlot].title : ''}
        onClose={() => setRecordSlot(null)}
        onConfirm={(audio) => recordSlot && handleConfirm(recordSlot)(audio)}
      />
    </div>
  )
}
