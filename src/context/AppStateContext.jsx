import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  analyzeSong,
  getAnalysis,
  listAnalyzedSongs,
  validateAudioInputs,
} from '@/services/analysisService'
import { mockAnalysisData } from '@/data/mockAnalysisData'

/**
 * Shared app state. It holds state and calls analysisService. It contains
 * no analysis logic of its own.
 *
 *  audio      the Original and Your Voice slots filled on Learn
 *  run        the live analysis: idle | processing | complete | error
 *  report     the analysis currently shown on Report: empty | loading | ready | error
 *  history    attempt scores per song, appended after every completed analysis
 *  credits    balance, plan and recent usage
 *  profile    user details, stats and preferences (mock)
 */

/* ==========================================================
   INITIAL MOCK ACCOUNT DATA (no backend yet)
   ========================================================== */

const INITIAL_PROFILE = {
  name: 'V S Vighnesh',
  email: 'vighnesh@example.com',
  phone: '+91 98765 43210',
  avatarUrl: null,
}

const INITIAL_STATS = { songsPracticed: 23, songsRecorded: 7, songsPosted: 2 }

const INITIAL_CREDITS = { plan: 'free', total: 10, remaining: 10 }

const INITIAL_USAGE = [
  { id: 'use_1', title: 'Mungaru Maleye', credits: 1, date: '2026-09-28' },
  { id: 'use_2', title: 'Krishna Nee Begane', credits: 1, date: '2026-09-26' },
  { id: 'use_3', title: 'Hanuman Chalisa', credits: 1, date: '2026-09-24' },
]

const INITIAL_PREFERENCES = {
  language: 'English',
  notifications: true,
  reminders: 'Daily, 7:00 PM',
  theme: 'Light',
  audioQuality: 'High',
}

/** Starts each song's attempt history from its mock analysis. */
function seedHistory() {
  const history = {}
  Object.values(mockAnalysisData).forEach((a) => {
    history[a.songId] = (a.attemptHistory || []).map((entry) => ({ ...entry }))
  })
  return history
}

/* ==========================================================
   HELPERS
   ========================================================== */

const IDLE_RUN = { status: 'idle', progress: null, error: null }
const EMPTY_REPORT = { status: 'empty', analysis: null, error: null }

/** Turns anything thrown into the { code, message, details } shape the UI reads. */
function toErrorState(err) {
  return {
    code: err?.code || 'analysis_failed',
    message: err?.message || 'Something went wrong.',
    details: err?.details || {},
  }
}

/**
 * Gives a slot its own object URL, made from the file or recording.
 * The upload/record modals revoke their URLs when they close, so the app
 * keeps separate copies that it controls.
 */
function ownUrl(audio) {
  if (!audio) return null
  const source = audio.file || audio.blob
  if (!source) return { ...audio, ownsUrl: false }
  return { ...audio, url: URL.createObjectURL(source), ownsUrl: true }
}

function revokeOwned(audio) {
  if (audio?.ownsUrl && audio.url) URL.revokeObjectURL(audio.url)
}

/* ==========================================================
   CONTEXT
   ========================================================== */

const AppStateContext = createContext(null)

export function AppStateProvider({ children }) {
  /* ---------- audio slots (Learn) ---------- */
  const [slots, setSlots] = useState({ original: null, user: null })
  const slotsRef = useRef(slots)

  const setAudio = useCallback((slot, audio) => {
    const nextSlots = { ...slotsRef.current, [slot]: ownUrl(audio) }
    revokeOwned(slotsRef.current[slot])
    slotsRef.current = nextSlots
    setSlots(nextSlots)
  }, [])

  const clearAudio = useCallback((slot) => setAudio(slot, null), [setAudio])

  /* ---------- account ---------- */
  const [profile, setProfile] = useState(INITIAL_PROFILE)
  const [stats, setStats] = useState(INITIAL_STATS)
  const [credits, setCredits] = useState(INITIAL_CREDITS)
  const [usage, setUsage] = useState(INITIAL_USAGE)
  const [preferences, setPreferences] = useState(INITIAL_PREFERENCES)
  const [history, setHistory] = useState(seedHistory)

  const creditsRef = useRef(credits)
  creditsRef.current = credits

  const updateProfile = useCallback((patch) => setProfile((p) => ({ ...p, ...patch })), [])
  const updatePreferences = useCallback((patch) => setPreferences((p) => ({ ...p, ...patch })), [])

  /** MOCK ONLY: no payment. The Stage and Credits pages pass the plan's credit amount. */
  const changePlan = useCallback((planId, monthlyCredits) => {
    setCredits({ plan: planId, total: monthlyCredits, remaining: monthlyCredits })
  }, [])

  /* ---------- report viewing ---------- */
  const [report, setReport] = useState(EMPTY_REPORT)
  const [songList, setSongList] = useState([])
  const viewIdRef = useRef(0)

  useEffect(() => {
    let alive = true
    listAnalyzedSongs()
      .then((list) => alive && setSongList(list))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  /** Loads an existing analysis (the Report song selector). Does not touch history or credits. */
  const viewAnalysis = useCallback(async (keyOrId) => {
    const id = ++viewIdRef.current
    setReport((r) => ({ ...r, status: 'loading', error: null }))
    try {
      const analysis = await getAnalysis(keyOrId)
      if (id !== viewIdRef.current) return
      setReport({ status: 'ready', analysis, error: null })
    } catch (err) {
      if (id !== viewIdRef.current) return
      setReport({ status: 'error', analysis: null, error: toErrorState(err) })
    }
  }, [])

  /* ---------- running a new analysis ---------- */
  const [run, setRun] = useState(IDLE_RUN)
  const runIdRef = useRef(0)
  const abortRef = useRef(null)

  const runAnalysis = useCallback(async (options = {}) => {
    abortRef.current?.abort()
    const runId = ++runIdRef.current
    const controller = new AbortController()
    abortRef.current = controller

    const { original, user } = slotsRef.current

    // Fail early, before any processing screen appears.
    try {
      validateAudioInputs(original, user)
    } catch (err) {
      setRun({ status: 'error', progress: null, error: toErrorState(err) })
      return null
    }
    if (creditsRef.current.remaining < 1) {
      setRun({
        status: 'error',
        progress: null,
        error: { code: 'no_credits', message: 'You have no analysis credits left.', details: {} },
      })
      return null
    }

    // The analysis gets its own audio URLs, so the Report players keep working
    // even if the user later replaces a slot on Learn.
    const snapshotOriginal = ownUrl(original)
    const snapshotUser = ownUrl(user)
    const isRecordedTake = !user.file

    setRun({
      status: 'processing',
      progress: { stepIndex: 0, totalSteps: 0, stepId: null, label: '', percent: 0 },
      error: null,
    })

    try {
      const analysis = await analyzeSong(snapshotOriginal, snapshotUser, {
        ...options,
        signal: controller.signal,
        onProgress: (p) => {
          if (runIdRef.current === runId) setRun((r) => ({ ...r, progress: p }))
        },
      })

      // A newer run replaced this one, so drop the stale result.
      if (runIdRef.current !== runId) {
        revokeOwned(snapshotOriginal)
        revokeOwned(snapshotUser)
        return null
      }

      viewIdRef.current += 1 // cancels any report load still in flight
      setReport({ status: 'ready', analysis, error: null })

      setHistory((prev) => {
        const list = prev[analysis.songId] || []
        const lastAttempt = list.length ? list[list.length - 1].attempt : 0
        return {
          ...prev,
          [analysis.songId]: [
            ...list,
            { attempt: lastAttempt + 1, score: analysis.overallScore, date: analysis.createdAt },
          ],
        }
      })

      // Credits are only spent on a completed analysis, never on a failed one.
      setCredits((c) => ({ ...c, remaining: Math.max(0, c.remaining - 1) }))
      setUsage((u) => [
        { id: analysis.analysisId, title: analysis.original.title, credits: 1, date: analysis.createdAt },
        ...u,
      ])
      setStats((s) => ({
        ...s,
        songsPracticed: s.songsPracticed + 1,
        songsRecorded: s.songsRecorded + (isRecordedTake ? 1 : 0),
      }))

      setRun((r) => ({ ...r, status: 'complete', error: null }))
      return analysis
    } catch (err) {
      revokeOwned(snapshotOriginal)
      revokeOwned(snapshotUser)
      if (runIdRef.current !== runId) return null

      if (err?.code === 'cancelled') {
        setRun(IDLE_RUN)
      } else {
        setRun({ status: 'error', progress: null, error: toErrorState(err) })
      }
      return null
    }
  }, [])

  const cancelAnalysis = useCallback(() => abortRef.current?.abort(), [])

  /** Clears a finished or failed run so the Report shows the report or empty state again. */
  const dismissRun = useCallback(() => {
    setRun((r) => (r.status === 'processing' ? r : IDLE_RUN))
  }, [])

  // Stop timers and release object URLs if the whole app unmounts.
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      revokeOwned(slotsRef.current.original)
      revokeOwned(slotsRef.current.user)
    }
  }, [])

  /* ---------- derived ---------- */
  const currentHistory = useMemo(() => {
    const analysis = report.analysis
    if (!analysis) return []
    return history[analysis.songId] || analysis.attemptHistory || []
  }, [report.analysis, history])

  const creditPercent =
    credits.total > 0 ? Math.round((credits.remaining / credits.total) * 100) : 0

  const value = useMemo(
    () => ({
      // audio slots
      original: slots.original,
      userVoice: slots.user,
      hasBothAudio: Boolean(slots.original && slots.user),
      setAudio,
      clearAudio,

      // running an analysis
      run, // { status, progress, error }
      isProcessing: run.status === 'processing',
      runAnalysis,
      cancelAnalysis,
      dismissRun,

      // viewing a report
      report, // { status, analysis, error }
      songList,
      viewAnalysis,
      history,
      currentHistory,

      // account
      profile,
      updateProfile,
      stats,
      credits,
      creditPercent,
      usage,
      changePlan,
      preferences,
      updatePreferences,
    }),
    [
      slots, setAudio, clearAudio,
      run, runAnalysis, cancelAnalysis, dismissRun,
      report, songList, viewAnalysis, history, currentHistory,
      profile, updateProfile, stats, credits, creditPercent, usage, changePlan,
      preferences, updatePreferences,
    ]
  )

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}

export function useAppState() {
  const ctx = useContext(AppStateContext)
  if (!ctx) throw new Error('useAppState must be used inside <AppStateProvider>')
  return ctx
}
