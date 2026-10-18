import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Info, TrendingDown, TrendingUp } from 'lucide-react'

import AttemptHistory from '@/components/AttemptHistory'
import AudioComparison from '@/components/AudioComparison'
import Badge from '@/components/Badge'
import ComparisonSnapshot from '@/components/ComparisonSnapshot'
import DynamicMetricCard from '@/components/DynamicMetricCard'
import KeyInsights from '@/components/KeyInsights'
import OverallScore from '@/components/OverallScore'
import PitchComparison from '@/components/PitchComparison'
import PracticeRecommendations from '@/components/PracticeRecommendations'
import ProcessingState from '@/components/ProcessingState'
import SongTimeline from '@/components/SongTimeline'
import { EmptyReport, ErrorReport, ReportSkeleton } from '@/components/ReportStates'
import {
  BreathAnalysis,
  HowYouPerformed,
  PronunciationAnalysis,
  RhythmComparison,
} from '@/components/AnalysisBlocks'
import { useAppState } from '@/context/AppStateContext'
import { cn } from '@/utils/cn'
import { sortByRelevance } from '@/utils/metricConfig'

/**
 * Report: renders ONE analysis object, whatever it contains.
 * Data comes from the server through AppStateContext (reportAdapter shapes it).
 *
 * Which screen shows (first match wins):
 *   run processing / complete   ProcessingState
 *   run error                   ErrorReport
 *   report loading              ReportSkeleton
 *   report error                ErrorReport
 *   report ready                the report
 *   otherwise                   EmptyReport
 *
 * Every card is drawn only when the analysis contains its data. Metrics that
 * could not be measured are listed in a short "Not measured" note, never as a
 * card with a made-up score. A null overall score shows a dash.
 */

function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches
  )
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = (e) => setMatches(e.matches)
    setMatches(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return matches
}

/** Pill-shaped report picker (native select). Each option is one finished report. */
function SongSelect({ songs, analysis, disabled, onChange }) {
  if (!songs.length && !analysis) return null

  const current = songs.find((s) => s.songId === analysis?.songId)
  const needsExtra = analysis && !current
  const value = current?.key ?? (needsExtra ? '__current' : '')

  return (
    <label className="relative block max-w-[11.5rem] shrink-0 sm:max-w-[16rem]">
      <span className="sr-only">Choose a report</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => e.target.value !== '__current' && onChange(e.target.value)}
        className="h-11 w-full cursor-pointer appearance-none truncate rounded-xl border border-gold-100 bg-ivory-100 pl-3.5 pr-9 text-[0.9rem] font-medium text-brown-800 shadow-soft outline-none transition-colors hover:bg-blush-50 disabled:opacity-60 sm:h-12 sm:text-[0.95rem]"
      >
        {value === '' && (
          <option value="" disabled>
            Choose a report
          </option>
        )}
        {needsExtra && <option value="__current">{analysis.original.title}</option>}
        {songs.map((s) => (
          <option key={s.key} value={s.key}>
            {s.title}
          </option>
        ))}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brown-500"
        strokeWidth={2}
        aria-hidden="true"
      />
    </label>
  )
}

/** Cards in two columns on desktop. Empty rows draw nothing. */
function CardRow({ children }) {
  const items = (Array.isArray(children) ? children : [children]).filter(Boolean)
  if (items.length === 0) return null
  return <div className={cn('grid gap-4 lg:items-start', items.length > 1 && 'lg:grid-cols-2')}>{items}</div>
}

/** Plain note for things the engine could not measure or estimated. */
function Notes({ unavailable, estimatedSections }) {
  if (unavailable.length === 0 && !estimatedSections) return null
  return (
    <section aria-label="About this report" className="nm-card animate-fade-up p-4 sm:p-5">
      <div className="flex items-center gap-2">
        <Info className="h-4 w-4 shrink-0 text-gold-500" strokeWidth={1.8} aria-hidden="true" />
        <h2 className="font-serif text-[1.15rem] font-semibold leading-none text-brown-900">About this report</h2>
      </div>
      <ul className="mt-3 flex flex-col gap-2 text-[0.82rem] leading-snug text-brown-600">
        {unavailable.map((m) => (
          <li key={m.id}>
            <span className="font-medium text-brown-800">{m.name} was not measured.</span> {m.reason}
          </li>
        ))}
        {estimatedSections && (
          <li>
            The song sections are an estimated split of the original, not named verses or choruses.
          </li>
        )}
      </ul>
    </section>
  )
}

function ChangeLine({ previous }) {
  if (!previous || previous.delta === null) return null
  const up = previous.delta > 0
  const flat = Math.abs(previous.delta) < 1
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <p className="mt-2.5 flex items-center gap-1.5 text-[0.82rem] text-brown-600">
      {!flat && <Icon className={cn('h-4 w-4', up ? 'text-sage-500' : 'text-status-bad')} strokeWidth={2} aria-hidden="true" />}
      {flat
        ? `About the same as attempt ${previous.attemptNumber}.`
        : `${up ? 'Up' : 'Down'} ${Math.abs(Math.round(previous.delta))} points since attempt ${previous.attemptNumber}.`}
    </p>
  )
}

export default function Report() {
  const navigate = useNavigate()
  const {
    run,
    report,
    songList,
    viewAnalysis,
    currentHistory,
    runAnalysis,
    cancelAnalysis,
    dismissRun,
  } = useAppState()

  const isWide = useMediaQuery('(min-width: 1024px)')
  const analysis = report.analysis
  const showingRun = run.status === 'processing' || run.status === 'complete'

  // Let "Analysis complete." be seen for a moment, then reveal the report.
  useEffect(() => {
    if (run.status !== 'complete') return undefined
    const timer = setTimeout(dismissRun, 1400)
    return () => clearTimeout(timer)
  }, [run.status, dismissRun])

  const goLearn = () => {
    dismissRun()
    navigate('/')
  }
  const goCredits = () => {
    dismissRun()
    navigate('/credits')
  }

  let body

  if (showingRun) {
    body = <ProcessingState progress={run.progress} onCancel={cancelAnalysis} />
  } else if (run.status === 'error') {
    body = <ErrorReport error={run.error} onRetry={() => runAnalysis()} onLearn={goLearn} onCredits={goCredits} />
  } else if (report.status === 'loading') {
    body = <ReportSkeleton />
  } else if (report.status === 'error') {
    body = (
      <ErrorReport
        error={report.error}
        onLearn={goLearn}
        onCredits={goCredits}
        onRetry={songList[0] ? () => viewAnalysis(songList[0].key) : undefined}
      />
    )
  } else if (report.status === 'ready' && analysis) {
    const metrics = sortByRelevance(analysis.metrics).filter((m) => m && Number.isFinite(Number(m.score)))
    const duration = analysis.original?.duration
    const tags = analysis.songProfile?.tags || []
    const estimatedSections = (analysis.sections || []).some((s) => s.isEstimated)

    body = (
      <div className="flex flex-col gap-4">
        <AudioComparison key={analysis.analysisId} analysis={analysis} />

        <section aria-label="Overall performance" className="nm-card animate-fade-up p-4 sm:p-5">
          <div className="grid gap-4 sm:grid-cols-[auto_minmax(0,1fr)] sm:gap-6">
            <OverallScore score={analysis.overallScore} statusLabel={analysis.statusLabel} size={132} />

            {metrics.length > 0 && (
              <div className="grid grid-cols-2 content-start gap-2.5 min-[400px]:grid-cols-3">
                {metrics.map((m) => (
                  <DynamicMetricCard key={m.id} metric={m} showDescription={isWide} />
                ))}
              </div>
            )}
          </div>

          {(analysis.summary || tags.length > 0 || analysis.previousAttempt) && (
            <div className="mt-4 border-t border-gold-100 pt-3.5">
              {analysis.summary && <p className="text-[0.88rem] leading-snug text-brown-600">{analysis.summary}</p>}
              <ChangeLine previous={analysis.previousAttempt} />
              {tags.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {tags.map((tag) => (
                    <Badge key={tag} variant="mist" size="sm">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>

        <PitchComparison data={analysis.pitchComparison} />

        <CardRow>
          <KeyInsights insights={analysis.insights} showDescriptions={isWide} />
          <ComparisonSnapshot rows={analysis.snapshot} showDifference={isWide} />
        </CardRow>

        <CardRow>
          <SongTimeline sections={analysis.sections} duration={duration} />
          <HowYouPerformed items={analysis.performance} />
        </CardRow>

        <CardRow>
          {analysis.rhythmComparison && (
            <RhythmComparison key="rhythm" data={analysis.rhythmComparison} duration={duration} />
          )}
          {analysis.pronunciationAnalysis && (
            <PronunciationAnalysis key="pron" data={analysis.pronunciationAnalysis} duration={duration} />
          )}
          {analysis.breathAnalysis && (
            <BreathAnalysis key="breath" data={analysis.breathAnalysis} duration={duration} />
          )}
        </CardRow>

        <CardRow>
          <PracticeRecommendations
            key={analysis.analysisId}
            recommendations={analysis.recommendations}
            sections={analysis.sections}
            metrics={analysis.metrics}
          />
          <AttemptHistory history={currentHistory} />
        </CardRow>

        <Notes unavailable={analysis.unavailableMetrics || []} estimatedSections={estimatedSections} />
      </div>
    )
  } else {
    body = (
      <EmptyReport
        onStart={() => navigate('/')}
        hasSavedReports={songList.length > 0}
        onBrowse={songList[0] ? () => viewAnalysis(songList[0].key) : undefined}
      />
    )
  }

  return (
    <div className="-mt-8 md:-mt-12">
      <div className="animate-fade-up">
        <div className="flex items-start justify-between gap-3">
          <h1 className="nm-title">Report</h1>
          <div className="pt-1.5 md:pt-3">
            <SongSelect songs={songList} analysis={analysis} disabled={showingRun} onChange={viewAnalysis} />
          </div>
        </div>

        <p className="nm-subtitle mt-2 max-w-[34rem]">Your detailed comparison and improvement insights.</p>

        {analysis?.meta?.isMock && !showingRun && report.status === 'ready' && (
          <Badge variant="gold" size="sm" dot className="mt-2.5">
            Demo analysis (simulated)
          </Badge>
        )}
      </div>

      <div className="mt-5">{body}</div>
    </div>
  )
}
