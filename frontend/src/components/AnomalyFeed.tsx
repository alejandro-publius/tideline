import { useMemo } from 'react'
import { fmtAgo, fmtDayTime, fmtLevel, type Units } from '../lib/tides'
import type { Anomaly } from '../types'

interface Props {
  anomalies: Anomaly[]
  loading: boolean
  error: string | null
  onRetry: () => void
  nowMs: number
  units: Units
}

/* Severity is carried by the label and by the pip/arrow mark, never by color
 * alone: the three flood stages stay separable in grayscale, and the marks
 * repeat the diverging surge pair (theme.surgeAbove / surgeBelow) rather than
 * replacing it. Color lives in index.css keyed off `anomaly-tag--<severity>`. */
const FLOOD = {
  minor: { label: 'Minor flood', mark: '●○○' },
  moderate: { label: 'Moderate flood', mark: '●●○' },
  major: { label: 'Major flood', mark: '●●●' },
} as const

const SURGE = {
  above: { label: 'Surge above', mark: '▲' },
  below: { label: 'Surge below', mark: '▼' },
} as const

interface Row {
  key: string
  tone: string
  label: string
  mark: string
  station: string
  detail: string
  ago: string
  exact: string
  ts: string
}

function describe(anomaly: Anomaly, nowMs: number, units: Units): Row {
  const { kind, severity, value, residual, ts } = anomaly
  const tag =
    kind === 'flood'
      ? FLOOD[severity as keyof typeof FLOOD]
      : SURGE[severity as keyof typeof SURGE]
  // residual is null for floods, and the detector may add severities we don't
  // know yet — both fall back to the raw observed level rather than rendering
  // an empty row.
  const detail =
    kind === 'surge' && residual != null
      ? `${residual >= 0 ? '+' : '−'}${fmtLevel(Math.abs(residual), units)} ${
          residual >= 0 ? 'above' : 'below'
        } prediction`
      : `${fmtLevel(value, units)} observed`
  const t = Date.parse(ts)
  return {
    key: `${kind}-${anomaly.station_id}-${ts}`,
    tone: tag ? severity : 'unknown',
    label: tag?.label ?? `${kind} · ${severity}`,
    mark: tag?.mark ?? '•',
    station: anomaly.station_name,
    detail,
    ago: fmtAgo(nowMs - t),
    exact: fmtDayTime(t),
    ts,
  }
}

/** The detector's recorded anomalies, newest first. A pure view of what it
 * already found: an empty list means a quiet coast, not a broken pipeline. */
export default function AnomalyFeed({ anomalies, loading, error, onRetry, nowMs, units }: Props) {
  // the API already sorts, but the feed's ordering shouldn't depend on that
  const rows = useMemo(
    () =>
      [...anomalies]
        .sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts))
        .map((a) => describe(a, nowMs, units)),
    [anomalies, nowMs, units],
  )

  return (
    <section className="card anomaly-card" aria-labelledby="anomaly-heading">
      <div className="chart-head">
        <h3 id="anomaly-heading">Recent anomalies</h3>
        {rows.length > 0 && <span className="panel-sub">{rows.length} recorded · newest first</span>}
      </div>

      {error ? (
        <div className="error-card" role="alert">
          <span>
            <strong>Couldn’t load anomalies.</strong> {error}
          </span>
          <button type="button" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : loading && rows.length === 0 ? (
        <p className="placeholder">Loading anomalies…</p>
      ) : rows.length === 0 ? (
        <p className="placeholder">
          No anomalies recorded
          <span className="placeholder-sub">every station is within its normal range</span>
        </p>
      ) : (
        <ul className="anomaly-list">
          {rows.map((row) => (
            <li key={row.key} className="anomaly-row">
              <span className={`anomaly-tag anomaly-tag--${row.tone}`}>
                <span className="anomaly-mark" aria-hidden="true">
                  {row.mark}
                </span>
                {row.label}
              </span>
              <span className="anomaly-station">{row.station}</span>
              <span className="anomaly-detail">{row.detail}</span>
              <time className="anomaly-ago" dateTime={row.ts} title={row.exact}>
                {row.ago}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
