/**
 * NAADAMAYA analysis display constants.
 *
 * The real analysis work happens on the backend (see services/api/analysis.js).
 * This file only holds the step list the ProcessingState screen shows. The steps
 * are the backend stage names, in the same order the worker reports them.
 *
 * The mock engine that used to live here (mockAnalysisData, analyzeSong,
 * simulated failures) has been removed. Mock results now exist ONLY on the
 * backend, when ANALYSIS_MODE=mock, and are labelled as simulated.
 */

export const ANALYSIS_STEPS = [
  { id: 'UPLOAD', label: 'Uploading your audio...' },
  { id: 'PREPROCESSING', label: 'Preparing your audio...' },
  { id: 'ALIGNMENT', label: 'Aligning your singing with the original...' },
  { id: 'PITCH_ANALYSIS', label: 'Analyzing pitch...' },
  { id: 'RHYTHM_ANALYSIS', label: 'Checking rhythm and timing...' },
  { id: 'STABILITY_ANALYSIS', label: 'Analyzing vocal stability...' },
  { id: 'SCORING', label: 'Scoring your performance...' },
  { id: 'REPORT_GENERATION', label: 'Preparing your report...' },
]

export const COMPLETE_LABEL = 'Analysis complete.'

/**
 * Kept so older imports keep compiling. Learn no longer calls it: starting an
 * analysis is done by AppStateContext.runAnalysis().
 */
export function validateAudioInputs(original, user) {
  if (!original) throw Object.assign(new Error('The original song is missing.'), { code: 'audio_missing', details: { slot: 'original' } })
  if (!user) throw Object.assign(new Error('Your voice recording is missing.'), { code: 'audio_missing', details: { slot: 'user' } })
}
