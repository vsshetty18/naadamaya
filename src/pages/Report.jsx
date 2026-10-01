import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'

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
 *
 * Which screen shows (first match wins):
 *   run processing / complete   ProcessingState
 *   run error                   ErrorReport
 *   report empty                EmptyReport
 *   report loading              ReportSkeleton
 *   report error                ErrorReport
 *   report ready                the report
 *
 * Every card below is drawn only when the analysis contains its data.
 * No scores, titles or insights are written in this file.
 */

/** True while the viewport matches a CSS media query. */
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

/** Pill-shaped song picker (native select, so it works well on phones). */
function SongSelect({ songs, analysis, disabled, onChange }) {
  const currentKey = analysis ? songs.find((s) => s.songId === analysis.songId)?.key : undefined
  const needsExtra = analysis && !currentKey
  const value = currentKey ?? (needsExtra ? '__current' : '')

  if (!songs.length && !analysis) return null

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

/** Lays out cards in two columns on desktop. Empty lists draw nothing. */
function CardRow({ children }) {
  const items = (Array.isArray(children) ? children : [children]).filter(Boolean)
  if (items.length === 0) return null
  return (
    <div className={cn('grid gap-4 lg:items-start', items.length > 1 && 'lg:grid-cols-2')}>{items}</div>
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

  /* ---------- body ---------- */
  let body

  if (showingRun) {
    body = <ProcessingState progress={run.progress} onCancel={cancelAnalysis} />
  } else if (run.status === 'error') {
    body = (
      <ErrorReport
        error={run.error}
        onRetry={() => runAnalysis()}
        onLearn={goLearn}
        onCredits={goCredits}
      />
    )
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
    const metrics = sortByRelevance(analysis.metrics).filter(
      (m) => m && Number.isFinite(Number(m.score))
    )
    const duration = analysis.original?.duration
    const tags = analysis.songProfile?.tags || []

    body = (
      <div className="flex flex-col gap-4">
        <AudioComparison key={analysis.analysisId} analysis={analysis} />

        {/* Overall score + the metrics THIS song returned */}
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

          {(analysis.summary || tags.length > 0) && (
            <div className="mt-4 border-t border-gold-100 pt-3.5">
              {analysis.summary && (
                <p className="text-[0.88rem] leading-snug text-brown-600">{analysis.summary}</p>
              )}
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
      {/* Title block */}
      <div className="animate-fade-up">
        <div className="flex items-start justify-between gap-3">
          <h1 className="nm-title">Report</h1>
          <div className="pt-1.5 md:pt-3">
            <SongSelect
              songs={songList}
              analysis={analysis}
              disabled={showingRun}
              onChange={viewAnalysis}
            />
          </div>
        </div>

        <p className="nm-subtitle mt-2 max-w-[34rem]">Your detailed comparison and improvement insights.</p>

        {analysis?.meta?.isMock && !showingRun && report.status === 'ready' && (
          <Badge variant="gold" size="sm" dot className="mt-2.5">
            Demo analysis
          </Badge>
        )}
      </div>

      <div className="mt-5">{body}</div>
    </div>
  )
}
