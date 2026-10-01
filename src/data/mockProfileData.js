/**
 * MOCK profile data used only by the Profile page.
 *
 * Personal details (name, email, phone, photo), the Songs Practiced and
 * Songs Recorded counts, the credits and the preference values all live in
 * AppStateContext, because other pages read and change them. This file holds
 * what only Profile needs: the vocal profile and the choices offered by the
 * preference controls.
 *
 * A real backend would send the vocal profile after analysing the singer's
 * recordings, so it is plain data with no logic in it.
 */

/** Vocal profile. Notes use scientific pitch notation (C4 = middle C). */
export const MOCK_VOCAL_PROFILE = {
  vocalRange: 'Tenor',
  lowestNote: 'C3',
  highestNote: 'A4',
  preferredLanguages: ['Kannada', 'Hindi', 'Sanskrit'],
  preferredGenres: ['Devotional', 'Light classical', 'Film melodies'],
}

/** Options for the preference controls on Profile. */
export const PREFERENCE_OPTIONS = {
  language: ['English', 'Kannada', 'Hindi', 'Tamil', 'Telugu'],
  theme: ['Light', 'Dark', 'System'],
  audioQuality: ['Standard', 'High', 'Lossless'],
  reminders: ['Off', 'Daily, 7:00 AM', 'Daily, 7:00 PM', 'Weekly, Sunday'],
}

/** Recent payments, shown under Account. Empty on the free plan. */
export const MOCK_PAYMENT_HISTORY = []
