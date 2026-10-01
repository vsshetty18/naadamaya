import { BarChart3, Music, Star } from 'lucide-react'

import { cn } from '@/utils/cn'

/**
 * The three statistics under the profile on Stage.
 *
 *   (note) 23          (bars) 7           (star) 2
 *   Songs Practiced    Songs Recorded     Songs Posted
 *
 * Props:
 *   stats   AppStateContext stats:
 *           { songsPracticed, songsRecorded, songsPosted }
 *   items   optional override: [{ id, label, value, icon }]
 *           Use it to show a different set of statistics (for example on
 *           Profile). When given, `stats` is ignored.
 *
 * Every number comes from the data. A missing value shows a dash,
 * never NaN or a made-up zero.
 */

const DEFAULT_ITEMS = [
  { id: 'songsPracticed', label: 'Songs Practiced', icon: Music },
  { id: 'songsRecorded', label: 'Songs Recorded', icon: BarChart3 },
  { id: 'songsPosted', label: 'Songs Posted', icon: Star },
]

const DASH = '\u2014'

function display(value) {
  const n = Number(value)
  if (value === null || value === undefined || value === '' || !Number.isFinite(n)) return DASH
  return n.toLocaleString('en-IN')
}

export default function StatisticsCard({ stats, items, className }) {
  const list = Array.isArray(items)
    ? items.filter((i) => i && i.label)
    : DEFAULT_ITEMS.map((d) => ({ ...d, value: stats?.[d.id] }))

  if (list.length === 0) return null

  return (
    <section aria-label="Singing statistics" className={cn('nm-card animate-fade-up px-2 py-4 sm:px-4 sm:py-5', className)}>
      <ul className="grid divide-x divide-gold-100" style={{ gridTemplateColumns: `repeat(${list.length}, minmax(0, 1fr))` }}>
        {list.map((item) => {
          const Icon = item.icon
          return (
            <li key={item.id || item.label} className="flex flex-col items-center px-1 text-center sm:flex-row sm:justify-center sm:gap-3 sm:px-3 sm:text-left">
              {Icon && (
                <Icon className="h-6 w-6 shrink-0 text-brown-400 sm:h-7 sm:w-7" strokeWidth={1.8} aria-hidden="true" />
              )}
              <span className="mt-1 sm:mt-0">
                <span className="block font-serif text-[1.6rem] font-semibold leading-none tabular-nums text-brown-900 sm:text-[1.9rem]">
                  {display(item.value)}
                </span>
                <span className="mt-1 block text-[0.72rem] leading-tight text-brown-500 sm:text-[0.8rem]">
                  {item.label}
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
