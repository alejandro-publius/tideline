import { fmtTime } from '../lib/tides'
import type { Series } from '../types'

const LABELS = {
  noaa: { text: 'Live from NOAA', className: 'badge badge--live' },
  cache: { text: 'Cached', className: 'badge badge--cache' },
  stale: { text: 'NOAA unreachable — showing cached data', className: 'badge badge--stale' },
} as const

export default function SourceBadge({ series }: { series: Series | null }) {
  if (!series) return null
  const { text, className } = LABELS[series.source]
  return (
    <span className={className}>
      <span className="badge-dot" aria-hidden="true" />
      {text}
      {series.fetched_at && ` · ${fmtTime(Date.parse(series.fetched_at))}`}
    </span>
  )
}
