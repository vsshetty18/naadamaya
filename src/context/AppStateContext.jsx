import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { useAuth } from '@/context/AuthContext'
import { ApiError } from '@/services/apiClient'
import {
  getDashboard,
  getReport,
  getUsage,
  getProgressOverview,
  listAnalyses,
  startAnalysis,
  waitForAnalysis,
} from '@/services/api/analysis'
import {
  fetchMediaUrl,
  getProfile,
  updateProfile as saveProfile,
  uploadProfilePhoto,
  uploadRecording,
  uploadReferenceSong,
} from '@/services/api/library'
import { adaptProgress, adaptReport, attachAudio } from '@/services/reportAdapter'

/**
 * NAADAMAYA app state, backed by the real API.
 *
 * Everything here comes from the server: profile, credits, statistics, recent
 * usage, the list of reports and the report on screen. Nothing is mocked.
 * Credits and usage are never calculated here, so they cannot be tampered with.
 *
 * Local only (no backend for them yet): the two audio slots on Learn, and the
 * Preferences screen values (theme, reminders, ...).
 *
 * Must be rendered INSIDE <AuthProvider>. Data loads when the user is signed
 * in and is cleared when they sign out.
 */

const EMPTY_PROFILE = { name: '', email: '', phone: '', avatarUrl: null }
const EMPTY_CREDITS = { plan: 'free', total: 0, remaining: 0 }
const EMPTY_STATS = { songsPracticed: 0, songsRecorded: 0, songsPosted: null } // posting is not built
const IDLE_RUN = { status: 'idle', progress: null, error: null }
const EMPTY_REPORT = { status: 'empty', analysis: null, error: null }

const INITIAL_PREFERENCES = {
  language: 'English',
  notifications: true,
  reminders: 'Daily, 7:00 PM',
  theme: 'Light',
  audioQuality: 'High',
}

/* ---------------- errors shown by ErrorReport ---------------- */
function toErrorState(err, slot) {
  if (!(err instanceof ApiError)) {
    return { code: 'analysis_failed', message: err?.message || 'Something went wrong.', details: {} }
  }
  const map = {
    USAGE_LIMIT_REACHED: 'no_credits',
    NETWORK_ERROR: 'network_error',
    TIMEOUT: 'timeout',
    INVALID_AUDIO: 'unsupported_format',
    UNSUPPORTED_MEDIA_TYPE: 'unsupported_format',
    FILE_TOO_LARGE: 'unsupported_format',
    RESOURCE_NOT_FOUND: 'not_found',
  }
  return {
    code: map[err.code] || 'analysis_failed',
    message: err.message,
    details: { ...err.details, slot },
  }
}

const AppStateContext = createContext(null)

export function AppStateProvider({ children }) {
  const { status: authStatus } = useAuth()
  const signedIn = authStatus === 'authenticated'

  /* ---------- account (from the server) ---------- */
  const [profile, setProfile] = useState(EMPTY_PROFILE)
  const [stats, setStats] = useState(EMPTY_STATS)
  const [credits, setCredits] = useState(EMPTY_CREDITS)
  const [usage, setUsage] = useState([])
  const [accountLoaded, setAccountLoaded] = useState(false)
  const [preferences, setPreferences] = useState(INITIAL_PREFERENCES)
  const avatarBlob = useRef(null)

  const applyProfile = useCallback(async (p) => {
    let avatarUrl = null
    try {
      avatarUrl = await fetchMediaUrl(p.profile_photo_url)
    } catch {
      avatarUrl = null
    }
    if (avatarBlob.current) URL.revokeObjectURL(avatarBlob.current)
    avatarBlob.current = avatarUrl && avatarUrl.startsWith('blob:') ? avatarUrl : null
    setProfile({
      name: p.display_name || '',
      email: p.email || '',
      phone: p.phone_number || '',
      avatarUrl,
      raw: p,
    })
  }, [])

  const applyUsage = useCallback((u) => {
    setCredits({ plan: String(u.plan_code || 'FREE').toLowerCase(), total: u.limit, remaining: u.remaining })
    setUsage(
      (u.recent || []).map((r, i) => ({
        id: r.analysis_id || `usage-${i}`,
        title: r.title || 'Deleted song',
        credits: r.credits,
        date: r.date,
      }))
    )
  }, [])

  /** Reloads profile, credits and statistics. Call after anything that changes them. */
  const refreshAccount = useCallback(async () => {
    const [p, u, o] = await Promise.allSettled([getProfile(), getUsage(), getProgressOverview()])
    if (p.status === 'fulfilled') await applyProfile(p.value)
    if (u.status === 'fulfilled') applyUsage(u.value)
    if (o.status === 'fulfilled') {
      setStats({
        songsPracticed: o.value.songs_practiced,
        songsRecorded: o.value.songs_recorded,
        songsPosted: null,
      })
    }
    setAccountLoaded(true)
  }, [applyProfile, applyUsage])

  const updateProfile = useCallback(
    async (patch) => {
      const fields = {}
      if ('name' in patch) fields.display_name = patch.name || null
      if ('email' in patch) fields.email = patch.email || null
      if (Object.keys(fields).length) {
        const saved = await saveProfile(fields)
        await applyProfile(saved)
      }
    },
    [applyProfile]
  )

  const setProfilePhoto = useCallback(
    async (file) => {
      await applyProfile(await uploadProfilePhoto(file))
    },
    [applyProfile]
  )

  const updatePreferences = useCallback((patch) => setPreferences((p) => ({ ...p, ...patch })), [])

  /* ---------- audio slots on Learn ---------- */
  const [slots, setSlots] = useState({ original: null, user: null })
  const slotsRef = useRef(slots)
  const uploaded = useRef(new WeakMap()) // audio object -> { songId } or { recordingId }

  const ownUrl = (audio) => {
    if (!audio) return null
    const source = audio.file || audio.blob
    if (!source) return { ...audio, ownsUrl: false }
    return { ...audio, url: URL.createObjectURL(source), ownsUrl: true }
  }
  const revokeOwned = (audio) => {
    if (audio?.ownsUrl && audio.url) URL.revokeObjectURL(audio.url)
  }

  const setAudio = useCallback((slot, audio) => {
    revokeOwned(slotsRef.current[slot])
    const next = { ...slotsRef.current, [slot]: ownUrl(audio) }
    slotsRef.current = next
    setSlots(next)
  }, [])
  const clearAudio = useCallback((slot) => setAudio(slot, null), [setAudio])

  /* ---------- reports ---------- */
  const [report, setReport] = useState(EMPTY_REPORT)
  const [songList, setSongList] = useState([])
  const viewId = useRef(0)
  const releaseAudio = useRef(() => {})

  const showReport = useCallback(async (reportData) => {
    const adapted = adaptReport(reportData)
    const { analysis, release } = await attachAudio(adapted)
    releaseAudio.current()
    releaseAudio.current = release
    return analysis
  }, [])

  const refreshSongList = useCallback(async () => {
    try {
      const page = await listAnalyses({ page_size: 50 })
      const seen = new Set()
      const list = []
      for (const a of page.items) {
        if (a.status !== 'COMPLETED' || seen.has(a.song_id)) continue
        seen.add(a.song_id) // newest attempt per song
        list.push({ key: a.id, songId: a.song_id, title: a.song_title || 'Song', artist: a.song_artist, duration: null })
      }
      setSongList(list)
    } catch {
      /* the dropdown simply stays as it was */
    }
  }, [])

  /** Loads one finished report (the Report song selector). Does not touch credits. */
  const viewAnalysis = useCallback(
    async (analysisId) => {
      const id = ++viewId.current
      setReport((r) => ({ ...r, status: 'loading', error: null }))
      try {
        const analysis = await showReport(await getReport(analysisId))
        if (id !== viewId.current) return
        setReport({ status: 'ready', analysis, error: null })
      } catch (err) {
        if (id !== viewId.current) return
        setReport({ status: 'error', analysis: null, error: toErrorState(err) })
      }
    },
    [showReport]
  )

  /* ---------- running an analysis ---------- */
  const [run, setRun] = useState(IDLE_RUN)
  const runId = useRef(0)
  const abortRef = useRef(null)
  const keys = useRef(new Map()) // recordingId -> idempotency key, reused when retrying

  const runAnalysis = useCallback(async () => {
    abortRef.current?.abort()
    const myRun = ++runId.current
    const controller = new AbortController()
    abortRef.current = controller
    const alive = () => runId.current === myRun
    const fail = (err, slot) => alive() && setRun({ status: 'error', progress: null, error: toErrorState(err, slot) })

    const { original, user } = slotsRef.current
    const missing = (slot, text) => ({ code: 'audio_missing', message: text, details: { slot } })
    if (!original) return setRun({ status: 'error', progress: null, error: missing('original', 'The original song is missing.') })
    if (!user) return setRun({ status: 'error', progress: null, error: missing('user', 'Your voice recording is missing.') })
    for (const [slot, audio] of [['original', original], ['user', user]]) {
      if (!audio.file && !audio.blob) {
        return setRun({
          status: 'error',
          progress: null,
          error: missing(slot, 'A demo recording has no audio to analyse. Record with a microphone or upload a file.'),
        })
      }
    }
    if (accountLoaded && credits.remaining < 1) {
      return setRun({
        status: 'error',
        progress: null,
        error: { code: 'no_credits', message: 'You have no analysis credits left.', details: {} },
      })
    }

    const step = (label, percent) =>
      alive() &&
      setRun({ status: 'processing', progress: { status: 'processing', stepIndex: 0, totalSteps: 8, stepId: 'UPLOAD', label, percent }, error: null })

    let slot = 'original'
    try {
      step('Uploading your audio...', 1)

      // Uploads are remembered per audio object, so a retry never uploads twice.
      let song = uploaded.current.get(original)
      if (!song) {
        song = await uploadReferenceSong(original.file || original.blob)
        uploaded.current.set(original, song)
      }
      slot = 'user'
      let rec = uploaded.current.get(user)
      if (!rec) {
        rec = await uploadRecording(user.file || user.blob, song.id, { source: user.file ? 'upload' : 'browser_recording' })
        uploaded.current.set(user, rec)
      }

      const started = await startAnalysis(rec.id, { songId: song.id, idempotencyKey: keys.current.get(rec.id) })
      keys.current.set(rec.id, started.idempotencyKey) // a retry after a network error reuses it
      if (started.credits_remaining != null) setCredits((c) => ({ ...c, remaining: started.credits_remaining }))

      const final = await waitForAnalysis(started.analysis_id, {
        signal: controller.signal,
        onProgress: (s) => alive() && setRun({ status: 'processing', progress: adaptProgress(s), error: null }),
      })
      if (!alive()) return

      if (final.status === 'FAILED') {
        refreshAccount() // the credit was refunded
        keys.current.delete(rec.id)
        return setRun({
          status: 'error',
          progress: null,
          error: {
            code: final.error?.code === 'TIMEOUT' ? 'timeout' : 'analysis_failed',
            message: final.error?.message || 'We could not finish analysing this performance.',
            details: { credit_refunded: final.error?.credit_refunded },
          },
        })
      }

      const analysis = await showReport(await getReport(started.analysis_id))
      if (!alive()) return
      keys.current.delete(rec.id)
      viewId.current += 1
      setReport({ status: 'ready', analysis, error: null })
      setRun({ status: 'complete', progress: adaptProgress({ ...final, status: 'COMPLETED' }), error: null })
      refreshAccount()
      refreshSongList()
    } catch (err) {
      if (err?.name === 'AbortError') return alive() && setRun(IDLE_RUN)
      fail(err, slot)
    }
  }, [accountLoaded, credits.remaining, refreshAccount, refreshSongList, showReport])

  const cancelAnalysis = useCallback(() => abortRef.current?.abort(), [])
  const dismissRun = useCallback(() => setRun((r) => (r.status === 'processing' ? r : IDLE_RUN)), [])

  /* ---------- load on sign-in, clear on sign-out ---------- */
  useEffect(() => {
    if (signedIn) {
      refreshAccount()
      refreshSongList()
      return undefined
    }
    abortRef.current?.abort()
    releaseAudio.current()
    if (avatarBlob.current) URL.revokeObjectURL(avatarBlob.current)
    avatarBlob.current = null
    revokeOwned(slotsRef.current.original)
    revokeOwned(slotsRef.current.user)
    slotsRef.current = { original: null, user: null }
    setSlots(slotsRef.current)
    setProfile(EMPTY_PROFILE)
    setStats(EMPTY_STATS)
    setCredits(EMPTY_CREDITS)
    setUsage([])
    setSongList([])
    setReport(EMPTY_REPORT)
    setRun(IDLE_RUN)
    setAccountLoaded(false)
    return undefined
  }, [signedIn, refreshAccount, refreshSongList])

  /* ---------- derived ---------- */
  const currentHistory = useMemo(() => report.analysis?.attemptHistory || [], [report.analysis])
  const creditPercent = credits.total > 0 ? Math.round((credits.remaining / credits.total) * 100) : 0

  const value = useMemo(
    () => ({
      original: slots.original,
      userVoice: slots.user,
      hasBothAudio: Boolean(slots.original && slots.user),
      setAudio,
      clearAudio,

      run,
      isProcessing: run.status === 'processing',
      runAnalysis,
      cancelAnalysis,
      dismissRun,

      report,
      songList,
      viewAnalysis,
      history: {},
      currentHistory,

      profile,
      updateProfile,
      setProfilePhoto,
      stats,
      credits,
      creditPercent,
      usage,
      accountLoaded,
      refreshAccount,
      // Plans are bought through Razorpay (useRazorpay). The mock changePlan is gone:
      // this only reloads the real credits and plan from the server.
      changePlan: refreshAccount,
      preferences,
      updatePreferences,
    }),
    [
      slots, setAudio, clearAudio, run, runAnalysis, cancelAnalysis, dismissRun,
      report, songList, viewAnalysis, currentHistory, profile, updateProfile, setProfilePhoto,
      stats, credits, creditPercent, usage, accountLoaded, refreshAccount, preferences, updatePreferences,
    ]
  )

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}

export function useAppState() {
  const ctx = useContext(AppStateContext)
  if (!ctx) throw new Error('useAppState must be used inside <AppStateProvider>')
  return ctx
}
