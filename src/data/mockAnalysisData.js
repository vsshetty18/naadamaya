/**
 * MOCK analysis responses. This file stands in for the future
 * POST /api/analyze response. Nothing in the UI may hardcode these values;
 * components only ever read them from an analysis object.
 *
 * Three songs, three genuinely different reports:
 *   songA  Mungaru Maleye     melodic ballad, 6 metrics, breath + pronunciation + rhythm blocks
 *   songB  Krishna Nee Begane classical devotional, 6 metrics, ornament/svara focus, NO rhythm block
 *   songC  Hanuman Chalisa    fast rhythmic recitation, 5 metrics, NO breath block
 *
 * Optional blocks (pitchComparison, sections, rhythmComparison,
 * pronunciationAnalysis, breathAnalysis) exist only when the engine returned
 * them. The report renders a card only if its block is present.
 */

/* ==========================================================
   DETERMINISTIC GENERATORS
   The real engine returns dense arrays. Here we generate them from a seed so
   every song has its own pitch line and waveform, and reloads look identical.
   ========================================================== */

const round = (n, d = 0) => {
  const f = 10 ** d
  return Math.round(n * f) / f
}

/** Small seeded random number generator (mulberry32). */
function mulberry32(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Waveform peaks, 0.12 to 1. Drives the AudioPlayer bars. */
function buildWaveform(seed, bars = 56) {
  const rand = mulberry32(seed)
  return Array.from({ length: bars }, (_, i) => {
    const envelope = 0.5 + 0.3 * Math.sin((i / bars) * Math.PI * 3 + seed)
    const v = envelope * 0.6 + rand() * 0.4
    return round(Math.min(1, Math.max(0.12, v)), 2)
  })
}

/**
 * Original melody contour in semitones above the tonic (Sa = 0).
 * `scale` is the set of notes the melody moves between, `hold` how long each
 * note is held, `gamaka` adds oscillation, `lifts` raises chosen time ranges
 * (for example a high-note section).
 */
function buildMelody({ seed, duration, points = 96, scale, hold = 4, gamaka = 0, lifts = [] }) {
  const rand = mulberry32(seed)
  const targets = []
  let idx = Math.floor(scale.length / 2)

  while (targets.length < points) {
    idx = Math.max(0, Math.min(scale.length - 1, idx + Math.round((rand() - 0.5) * 4)))
    for (let k = 0; k < hold && targets.length < points; k++) targets.push(scale[idx])
  }

  const timeAt = (i) => (i / (points - 1)) * duration

  lifts.forEach(({ from, to, add }) => {
    targets.forEach((v, i) => {
      const t = timeAt(i)
      if (t >= from && t <= to) targets[i] = v + add
    })
  })

  // Moving average turns steps into natural glides between notes.
  return targets.map((_, i) => {
    let sum = 0
    let n = 0
    for (let k = -2; k <= 2; k++) {
      const j = i + k
      if (j >= 0 && j < points) {
        sum += targets[j]
        n++
      }
    }
    return { t: round(timeAt(i), 1), v: round(sum / n + gamaka * Math.sin(i * 1.9), 2) }
  })
}

/** The singer's contour: the original plus drift and wobble in chosen ranges. */
function buildUserPitch(original, { seed, baseOffset = 0, noise = 0.08, deviations = [] }) {
  const rand = mulberry32(seed)
  return original.map(({ t, v }) => {
    let offset = baseOffset
    let jitter = noise
    deviations.forEach((d) => {
      if (t >= d.from && t <= d.to) {
        const w = Math.min(1, Math.sin((Math.PI * (t - d.from)) / (d.to - d.from)) * 1.6)
        offset += (d.offset || 0) * w
        jitter += (d.jitter || 0) * w
      }
    })
    return { t, v: round(v + offset + (rand() - 0.5) * 2 * jitter, 2) }
  })
}

/**
 * Assembles the full pitchComparison block, including the summary numbers the
 * real engine would compute (matched / sharp / flat share, mean deviation).
 */
function createPitchComparison({ axis, melody, user }) {
  const originalPitchData = buildMelody(melody)
  const userPitchData = buildUserPitch(originalPitchData, user)
  const deviations = user.deviations || []

  const annotations = deviations.map((d) => ({
    startTime: d.from,
    endTime: d.to,
    type: Math.abs(d.offset || 0) >= 0.2 ? (d.offset > 0 ? 'sharp' : 'flat') : 'unstable',
    cents: Math.round((d.offset || 0) * 100),
    label: d.label,
  }))

  let matched = 0
  let sharp = 0
  let flat = 0
  let diffSum = 0
  originalPitchData.forEach((o, i) => {
    const diff = userPitchData[i].v - o.v
    diffSum += diff
    if (diff >= 0.25) sharp++
    else if (diff <= -0.25) flat++
    else matched++
  })
  const n = originalPitchData.length

  return {
    axis, // [{ label, value }] ascending; the graph draws the highest value at the top
    originalPitchData, // [{ t (seconds), v (semitones above Sa) }]
    userPitchData,
    annotations, // where the singer went sharp, flat or unstable
    stats: {
      matchedPercent: round((matched / n) * 100),
      sharpPercent: round((sharp / n) * 100),
      flatPercent: round((flat / n) * 100),
    },
    meanDeviationCents: Math.round((diffSum / n) * 100),
  }
}

const mean = (list) => Math.round(list.reduce((s, v) => s + v, 0) / list.length)

/* ==========================================================
   SONG A: Mungaru Maleye (melodic ballad)
   ========================================================== */

const pitchA = createPitchComparison({
  axis: [
    { label: 'Sa', value: 0 },
    { label: 'Re', value: 2 },
    { label: 'Ga', value: 4 },
    { label: 'Ma', value: 5 },
    { label: 'Pa', value: 7 },
    { label: 'Sa', value: 12 },
  ],
  melody: {
    seed: 101,
    duration: 261,
    scale: [0, 2, 4, 5, 7, 9],
    hold: 4,
    lifts: [{ from: 158, to: 196, add: 3 }],
  },
  user: {
    seed: 202,
    baseOffset: 0.03,
    noise: 0.09,
    deviations: [
      { from: 66, to: 92, offset: 0.32, label: 'Drifted sharp in the chorus' },
      { from: 120, to: 132, offset: -0.3, label: 'Slightly flat at the Verse 2 entry' },
      { from: 162, to: 192, offset: 0.55, jitter: 0.35, label: 'Sharp and unsteady on the high notes' },
    ],
  },
})

const songA = {
  songId: 'song_mungaru_maleye',
  analysisId: 'an_20260928_mm01',
  createdAt: '2026-09-28',
  meta: { engineVersion: 'mock-1', isMock: true },

  overallScore: 78,
  statusLabel: null, // null: the UI derives the label from the score
  summary:
    'Your melody stayed close to the original. The match slipped on the higher notes and the longer phrases.',

  original: {
    title: 'Mungaru Maleye',
    artist: 'Yograj Bhat',
    duration: 261,
    tempo: 82,
    key: 'F#',
    artwork: { gradient: ['#F2B880', '#B9695A', '#3B4A66'], motif: 'mountains' },
    waveform: buildWaveform(11),
    audioUrl: null,
  },
  user: {
    displayName: 'V S Vighnesh',
    avatarUrl: null,
    recordedAt: '2026-09-28',
    duration: 258,
    tempo: 84,
    waveform: buildWaveform(12),
    audioUrl: null,
  },

  songProfile: {
    summary: 'A slow, melody-led song with a lifted high-note section and long phrases.',
    tags: ['Melodic', 'Slow tempo', 'Long phrases', 'High notes'],
  },

  metrics: [
    { id: 'pitch_accuracy', name: 'Pitch Accuracy', score: 82, status: 'good', relevance: 'high', description: 'Notes landed close to the original in most phrases.' },
    { id: 'rhythm', name: 'Rhythm & Timing', score: 76, status: 'good', relevance: 'high', description: 'Mostly in time, but Verse 2 entered late.' },
    { id: 'stability', name: 'Stability', score: 70, status: 'needs_improvement', relevance: 'high', description: 'Held notes wavered, mainly in the high-note section.' },
    { id: 'expression', name: 'Expression', score: 80, status: 'good', relevance: 'medium', description: 'Your dynamics followed the mood of the original.' },
    { id: 'pronunciation', name: 'Pronunciation', score: 88, status: 'good', relevance: 'medium', description: 'Words were clear and well shaped.' },
    { id: 'breath_control', name: 'Breath Control', score: 72, status: 'needs_improvement', relevance: 'high', description: 'Longer phrases ran short of breath.' },
  ],

  performance: [
    { type: 'positive', text: 'Your melody closely followed the original through most of the song.' },
    { type: 'positive', text: 'Pronunciation stayed clear and natural in the verses.' },
    { type: 'improvement', text: 'Verse 2 entered a little later than the original.' },
    { type: 'improvement', text: 'Breath ran short on the longer phrases.' },
    { type: 'issue', text: 'Pitch drifted sharp and unsteady in the high-note section.' },
  ],

  sections: [
    { id: 'verse_1', sectionName: 'Verse 1', startTime: 0, endTime: 58, score: 88, status: 'good', issues: [] },
    { id: 'chorus', sectionName: 'Chorus', startTime: 58, endTime: 104, score: 79, status: 'warning', issues: [{ type: 'pitch', label: 'Pitch deviation' }] },
    { id: 'verse_2', sectionName: 'Verse 2', startTime: 104, endTime: 158, score: 72, status: 'warning', issues: [{ type: 'timing', label: 'Timing issue' }] },
    { id: 'high_notes', sectionName: 'High-note section', startTime: 158, endTime: 196, score: 58, status: 'critical', issues: [{ type: 'stability', label: 'Stability issue' }, { type: 'pitch', label: 'Drifted sharp' }] },
    { id: 'final_chorus', sectionName: 'Final chorus', startTime: 196, endTime: 261, score: 84, status: 'good', issues: [], note: 'Improved' },
  ],

  pitchComparison: pitchA,

  rhythmComparison: {
    unit: 'ms', // positive = late, negative = early
    entries: [
      { label: 'Verse 1', startTime: 0, offsetMs: 10 },
      { label: 'Chorus', startTime: 58, offsetMs: 45 },
      { label: 'Verse 2', startTime: 104, offsetMs: 140 },
      { label: 'High-note section', startTime: 158, offsetMs: 60 },
      { label: 'Final chorus', startTime: 196, offsetMs: -15 },
    ],
  },

  pronunciationAnalysis: {
    items: [
      { startTime: 12, endTime: 34, status: 'clear', note: 'Vowels were open and clear in Verse 1.' },
      { startTime: 92, endTime: 104, status: 'unclear', note: 'Soft consonants blurred at the end of the chorus.' },
      { startTime: 210, endTime: 250, status: 'clear', note: 'Diction stayed crisp through the final chorus.' },
    ],
  },

  breathAnalysis: {
    phrases: [
      { startTime: 40, endTime: 58, status: 'steady', note: 'Comfortable phrase length.' },
      { startTime: 170, endTime: 196, status: 'strained', note: 'Breath ran out before the phrase finished.' },
      { startTime: 228, endTime: 261, status: 'short', note: 'Breath was taken earlier than in the original.' },
    ],
  },

  insights: [
    { type: 'positive', title: 'Good pitch accuracy in most parts!', description: 'Most notes sat close to the original.' },
    { type: 'positive', title: 'Your pronunciation is clear.', description: 'Words were easy to follow throughout.' },
    { type: 'improvement', title: 'Try to maintain consistent pitch in higher notes.', description: 'Pitch became sharp and unsteady above the middle range.' },
    { type: 'improvement', title: 'Work on breath control for longer lines.', description: 'Long phrases ended with less support than they began with.' },
  ],

  recommendations: [
    { id: 'rec_a1', priority: 1, title: 'Steady the high notes', description: 'Practice the high-note section slowly against a drone, holding each note until it stops moving.', metricId: 'stability', sectionId: 'high_notes', duration: '10 min' },
    { id: 'rec_a2', priority: 2, title: 'Build breath for long lines', description: 'Sing the longest phrases on one breath at a slower tempo, then speed up gradually.', metricId: 'breath_control', sectionId: 'final_chorus', duration: '8 min' },
    { id: 'rec_a3', priority: 3, title: 'Enter Verse 2 on time', description: 'Sing along with the original at 80% tempo and aim to start each line together.', metricId: 'rhythm', sectionId: 'verse_2', duration: '6 min' },
    { id: 'rec_a4', priority: 4, title: 'Repeat the chorus', description: 'Record the chorus twice and compare where the pitch drifts sharp.', metricId: 'pitch_accuracy', sectionId: 'chorus', duration: '5 min' },
  ],

  snapshot: [
    { id: 'average_pitch', label: 'Average Pitch', format: 'text', original: 'F#', user: 'F#', difference: null },
    { id: 'tempo', label: 'Tempo (BPM)', format: 'number', original: 82, user: 84, difference: 2 },
    { id: 'duration', label: 'Duration', format: 'time', original: 261, user: 258, difference: -3 },
    { id: 'pitch_deviation', label: 'Pitch Deviation', format: 'cents', original: null, user: pitchA.meanDeviationCents, difference: null },
    { id: 'stability_score', label: 'Stability Score', format: 'score', original: null, user: 70, difference: null },
  ],

  attemptHistory: [
    { attempt: 1, score: 65, date: '2026-09-18' },
    { attempt: 2, score: 71, date: '2026-09-22' },
    { attempt: 3, score: 74, date: '2026-09-25' },
    { attempt: 4, score: 78, date: '2026-09-28' },
  ],
}

/* ==========================================================
   SONG B: Krishna Nee Begane (classical devotional, svara + gamaka focus)
   ========================================================== */

const pitchB = createPitchComparison({
  axis: [
    { label: 'Ni', value: -1 },
    { label: 'Sa', value: 0 },
    { label: 'Re', value: 2 },
    { label: 'Ga', value: 4 },
    { label: 'Ma#', value: 6 },
    { label: 'Pa', value: 7 },
    { label: 'Dha', value: 9 },
    { label: 'Ni', value: 11 },
    { label: 'Sa', value: 12 },
  ],
  melody: {
    seed: 303,
    duration: 347,
    scale: [0, 2, 4, 6, 7, 9, 11],
    hold: 6,
    gamaka: 0.3,
    lifts: [{ from: 198, to: 276, add: 1 }],
  },
  user: {
    seed: 404,
    baseOffset: -0.06,
    noise: 0.07,
    deviations: [
      { from: 140, to: 185, offset: -0.28, jitter: 0.1, label: 'Gamakas softened and slightly flat' },
      { from: 224, to: 258, offset: -0.34, jitter: 0.22, label: 'Sagged flat on the long phrase' },
    ],
  },
})

const songB = {
  songId: 'song_krishna_nee_begane',
  analysisId: 'an_20260926_kb01',
  createdAt: '2026-09-26',
  meta: { engineVersion: 'mock-1', isMock: true },

  overallScore: 85,
  statusLabel: 'Beautifully sung!', // backend-supplied wording overrides the default label
  summary:
    'Your svaras were placed with great care. Gamakas and breath support on long phrases are the next step.',

  original: {
    title: 'Krishna Nee Begane',
    artist: 'Traditional (Vyasatirtha)',
    duration: 347,
    tempo: 68,
    key: 'C#',
    artwork: { gradient: ['#F3D9A4', '#C99A5B', '#7A4726'], motif: 'lamp' },
    waveform: buildWaveform(21),
    audioUrl: null,
  },
  user: {
    displayName: 'V S Vighnesh',
    avatarUrl: null,
    recordedAt: '2026-09-26',
    duration: 352,
    tempo: 65,
    waveform: buildWaveform(22),
    audioUrl: null,
  },

  songProfile: {
    summary: 'A slow classical devotional built on svara accuracy, gamakas and sustained notes.',
    tags: ['Svara-led', 'Gamakas', 'Sustained notes', 'Slow tempo'],
  },

  metrics: [
    { id: 'svara_accuracy', name: 'Svara Accuracy', score: 91, status: 'excellent', relevance: 'high', description: 'Svaras landed on the correct notes.' },
    { id: 'pitch_accuracy', name: 'Pitch Accuracy', score: 89, status: 'very_good', relevance: 'high', description: 'Very close pitch placement throughout.' },
    { id: 'note_sustain', name: 'Note Sustain', score: 84, status: 'good', relevance: 'high', description: 'Held notes were steady for most of their length.' },
    { id: 'ornamentation', name: 'Gamaka & Ornamentation', score: 74, status: 'needs_improvement', relevance: 'high', description: 'Oscillations were softer than in the reference.' },
    { id: 'breath_control', name: 'Breath Control', score: 79, status: 'needs_improvement', relevance: 'high', description: 'Pitch sagged near the end of long phrases.' },
    { id: 'expression', name: 'Expression', score: 90, status: 'excellent', relevance: 'medium', description: 'Phrasing carried the devotional mood well.' },
  ],

  performance: [
    { type: 'positive', text: 'Svara placement was very close to the reference.' },
    { type: 'positive', text: 'Expressive phrasing followed the emotional arc of the song.' },
    { type: 'improvement', text: 'Gamakas need more definition in the Anupallavi.' },
    { type: 'improvement', text: 'Breath support faded on the long phrase in the Charanam.' },
  ],

  sections: [
    { id: 'alapana', sectionName: 'Alapana', startTime: 0, endTime: 62, score: 90, status: 'good', issues: [] },
    { id: 'pallavi', sectionName: 'Pallavi', startTime: 62, endTime: 130, score: 88, status: 'good', issues: [] },
    { id: 'anupallavi', sectionName: 'Anupallavi', startTime: 130, endTime: 198, score: 76, status: 'warning', issues: [{ type: 'ornamentation', label: 'Gamakas softened' }] },
    { id: 'charanam', sectionName: 'Charanam', startTime: 198, endTime: 276, score: 72, status: 'warning', issues: [{ type: 'breath', label: 'Breath cut a long phrase' }, { type: 'pitch', label: 'Sagged flat' }] },
    { id: 'pallavi_return', sectionName: 'Pallavi (return)', startTime: 276, endTime: 347, score: 90, status: 'good', issues: [], note: 'Improved' },
  ],

  pitchComparison: pitchB,

  // No rhythmComparison: this song is sung in a free, flowing tempo, so the engine did not return one.

  breathAnalysis: {
    phrases: [
      { startTime: 8, endTime: 40, status: 'steady', note: 'Long alapana phrases were well supported.' },
      { startTime: 224, endTime: 258, status: 'strained', note: 'Breath faded before the phrase ended.' },
      { startTime: 300, endTime: 340, status: 'steady', note: 'Closing phrase was calm and even.' },
    ],
  },

  insights: [
    { type: 'positive', title: 'Svara placement is very close', description: 'Your svaras landed on the right notes through the alapana and pallavi.' },
    { type: 'positive', title: 'Expressive phrasing', description: 'Your dynamics followed the emotional arc of the original.' },
    { type: 'improvement', title: 'Gamakas need more definition', description: 'Oscillations on the mid-range notes were softer than the reference.' },
    { type: 'improvement', title: 'Breath dropped the pitch on long phrases', description: 'Notes sagged flat toward the end of sustained phrases in the Charanam.' },
  ],

  recommendations: [
    { id: 'rec_b1', priority: 1, title: 'Define your gamakas', description: 'Sing the Anupallavi at half speed with the original, shaping each oscillation deliberately.', metricId: 'ornamentation', sectionId: 'anupallavi', duration: '10 min' },
    { id: 'rec_b2', priority: 2, title: 'Support the long phrase', description: 'Practice the Charanam phrase on a slow count, keeping the last note as steady as the first.', metricId: 'breath_control', sectionId: 'charanam', duration: '8 min' },
    { id: 'rec_b3', priority: 3, title: 'Keep the pitch from sagging', description: 'Sustain the final note of each Charanam line against a drone and check it stays centered.', metricId: 'note_sustain', sectionId: 'charanam', duration: '6 min' },
    { id: 'rec_b4', priority: 4, title: 'Record the Anupallavi again', description: 'Compare a fresh take with this one and listen for firmer gamakas.', metricId: 'ornamentation', sectionId: 'anupallavi', duration: '5 min' },
  ],

  snapshot: [
    { id: 'key', label: 'Key', format: 'text', original: 'C#', user: 'C#', difference: null },
    { id: 'tempo', label: 'Tempo (BPM)', format: 'number', original: 68, user: 65, difference: -3 },
    { id: 'duration', label: 'Duration', format: 'time', original: 347, user: 352, difference: 5 },
    { id: 'vocal_range', label: 'Vocal Range', format: 'text', original: 'C#3 - A4', user: 'C#3 - G#4', difference: null },
    { id: 'pitch_deviation', label: 'Pitch Deviation', format: 'cents', original: null, user: pitchB.meanDeviationCents, difference: null },
  ],

  attemptHistory: [
    { attempt: 1, score: 79, date: '2026-09-17' },
    { attempt: 2, score: 82, date: '2026-09-21' },
    { attempt: 3, score: 85, date: '2026-09-26' },
  ],
}

/* ==========================================================
   SONG C: Hanuman Chalisa (fast, rhythmic recitation)
   ========================================================== */

const pitchC = createPitchComparison({
  axis: [
    { label: 'Sa', value: 0 },
    { label: 'Re', value: 2 },
    { label: 'Ga', value: 4 },
    { label: 'Ma', value: 5 },
    { label: 'Pa', value: 7 },
    { label: 'Dha', value: 9 },
  ],
  melody: {
    seed: 505,
    duration: 428,
    scale: [2, 4, 5, 7, 9],
    hold: 2,
  },
  user: {
    seed: 606,
    baseOffset: 0.02,
    noise: 0.1,
    deviations: [
      { from: 190, to: 230, offset: 0, jitter: 0.3, label: 'Unsteady through the fast verses' },
      { from: 300, to: 330, offset: 0.26, label: 'Drifted sharp' },
    ],
  },
})

const rhythmEntriesC = [
  { label: 'Doha', startTime: 0, offsetMs: 40 },
  { label: 'Verses 1-10', startTime: 34, offsetMs: 110 },
  { label: 'Verses 11-20', startTime: 150, offsetMs: 210 },
  { label: 'Verses 21-30', startTime: 262, offsetMs: 130 },
  { label: 'Closing', startTime: 352, offsetMs: 60 },
]

const songC = {
  songId: 'song_hanuman_chalisa',
  analysisId: 'an_20260924_hc01',
  createdAt: '2026-09-24',
  meta: { engineVersion: 'mock-1', isMock: true },

  overallScore: 64,
  statusLabel: null,
  summary:
    'Your pitch held up well. Rhythm and phrase entries are what to work on, especially in the faster verses.',

  original: {
    title: 'Hanuman Chalisa',
    artist: 'Tulsidas (traditional)',
    duration: 428,
    tempo: 112,
    key: 'A',
    artwork: { gradient: ['#F4C58A', '#D98A4B', '#7C3A2A'], motif: 'temple' },
    waveform: buildWaveform(31),
    audioUrl: null,
  },
  user: {
    displayName: 'V S Vighnesh',
    avatarUrl: null,
    recordedAt: '2026-09-24',
    duration: 441,
    tempo: 104,
    waveform: buildWaveform(32),
    audioUrl: null,
  },

  songProfile: {
    summary: 'A fast, rhythmic recitation where timing, phrase alignment and clear diction matter most.',
    tags: ['Fast tempo', 'Rhythmic', 'Lyric-heavy', 'Repeating phrases'],
  },

  metrics: [
    { id: 'rhythm', name: 'Rhythm & Timing', score: 58, status: 'needs_practice', relevance: 'high', description: 'Many phrases began after the original.' },
    { id: 'phrase_alignment', name: 'Phrase Alignment', score: 60, status: 'needs_practice', relevance: 'high', description: 'Phrase starts drifted apart from the reference.' },
    { id: 'tempo', name: 'Tempo Consistency', score: 71, status: 'needs_improvement', relevance: 'medium', description: 'You began slower than the original and dragged further.' },
    { id: 'pronunciation', name: 'Pronunciation', score: 66, status: 'needs_improvement', relevance: 'high', description: 'Consonants blurred at faster lines.' },
    { id: 'pitch_accuracy', name: 'Pitch Accuracy', score: 74, status: 'good', relevance: 'medium', description: 'Pitch stayed close to the reference.' },
  ],

  performance: [
    { type: 'positive', text: 'Pitch stayed close to the reference, even in the faster verses.' },
    { type: 'positive', text: 'The opening Doha was placed confidently.' },
    { type: 'improvement', text: 'Phrases entered late in the first half of the recitation.' },
    { type: 'issue', text: 'Tempo dragged and diction blurred in Verses 11-20.' },
  ],

  sections: [
    { id: 'doha', sectionName: 'Doha', startTime: 0, endTime: 34, score: 80, status: 'good', issues: [] },
    { id: 'verses_1_10', sectionName: 'Verses 1-10', startTime: 34, endTime: 150, score: 61, status: 'warning', issues: [{ type: 'timing', label: 'Late phrase entries' }] },
    { id: 'verses_11_20', sectionName: 'Verses 11-20', startTime: 150, endTime: 262, score: 52, status: 'critical', issues: [{ type: 'rhythm', label: 'Tempo dragged' }, { type: 'pronunciation', label: 'Unclear at faster lines' }] },
    { id: 'verses_21_30', sectionName: 'Verses 21-30', startTime: 262, endTime: 352, score: 66, status: 'warning', issues: [{ type: 'pronunciation', label: 'Consonants blurred' }] },
    { id: 'closing', sectionName: 'Verses 31-40 & closing', startTime: 352, endTime: 428, score: 74, status: 'good', issues: [], note: 'Improved' },
  ],

  pitchComparison: pitchC,

  rhythmComparison: {
    unit: 'ms',
    entries: rhythmEntriesC,
  },

  pronunciationAnalysis: {
    items: [
      { startTime: 60, endTime: 90, status: 'clear', note: 'Diction was clean at the start of the recitation.' },
      { startTime: 160, endTime: 190, status: 'unclear', note: 'Vowel length was shortened at faster lines.' },
      { startTime: 270, endTime: 300, status: 'unclear', note: 'Conjunct consonants were rushed.' },
    ],
  },

  // No breathAnalysis: short repeating phrases gave the engine nothing meaningful to report on breath.

  insights: [
    { type: 'positive', title: 'Steady pitch throughout', description: 'Your pitch stayed close to the reference even in the faster verses.' },
    { type: 'positive', title: 'Strong opening', description: 'The opening Doha was well placed and confident.' },
    { type: 'improvement', title: 'Phrases entered late', description: 'Many phrases in Verses 11-20 began after the original.' },
    { type: 'improvement', title: 'Tempo drifted', description: 'You started slower than the reference and dragged further as the verses went on.' },
    { type: 'improvement', title: 'Consonants blurred at speed', description: 'Diction lost clarity in the faster lines.' },
  ],

  recommendations: [
    { id: 'rec_c1', priority: 1, title: 'Practice Verses 11-20 at 80% tempo', description: 'Sing along with the original at a reduced speed, then raise it in small steps.', metricId: 'rhythm', sectionId: 'verses_11_20', duration: '12 min' },
    { id: 'rec_c2', priority: 2, title: 'Match your phrase starts', description: 'Focus only on beginning each line together with the original, ignoring the rest.', metricId: 'phrase_alignment', sectionId: 'verses_1_10', duration: '8 min' },
    { id: 'rec_c3', priority: 3, title: 'Slow diction drill', description: 'Speak the fastest lines slowly, then sing them, keeping every consonant distinct.', metricId: 'pronunciation', sectionId: 'verses_21_30', duration: '8 min' },
    { id: 'rec_c4', priority: 4, title: 'Clap the pulse', description: 'Tap the beat while you sing so the tempo stays even from start to finish.', metricId: 'tempo', sectionId: null, duration: '5 min' },
  ],

  snapshot: [
    { id: 'key', label: 'Key', format: 'text', original: 'A', user: 'A', difference: null },
    { id: 'tempo', label: 'Tempo (BPM)', format: 'number', original: 112, user: 104, difference: -8 },
    { id: 'duration', label: 'Duration', format: 'time', original: 428, user: 441, difference: 13 },
    { id: 'timing_offset', label: 'Timing Offset', format: 'ms', original: null, user: mean(rhythmEntriesC.map((e) => e.offsetMs)), difference: null },
    { id: 'pitch_deviation', label: 'Pitch Deviation', format: 'cents', original: null, user: pitchC.meanDeviationCents, difference: null },
  ],

  attemptHistory: [
    { attempt: 1, score: 52, date: '2026-09-15' },
    { attempt: 2, score: 57, date: '2026-09-19' },
    { attempt: 3, score: 55, date: '2026-09-21' },
    { attempt: 4, score: 64, date: '2026-09-24' },
  ],
}

/* ==========================================================
   EXPORTS
   ========================================================== */

export const mockAnalysisData = { songA, songB, songC }

export const DEFAULT_MOCK_KEY = 'songA'

/** Lightweight list for the Report song selector. */
export const mockSongList = Object.entries(mockAnalysisData).map(([key, a]) => ({
  key,
  songId: a.songId,
  title: a.original.title,
  artist: a.original.artist,
  duration: a.original.duration,
}))

/** Finds a mock analysis by key ("songA") or by songId. Returns undefined if unknown. */
export function getMockAnalysis(keyOrId) {
  return (
    mockAnalysisData[keyOrId] ||
    Object.values(mockAnalysisData).find((a) => a.songId === keyOrId)
  )
}
