import type { Reading } from '../types'

export interface TidePoint {
  t: number // epoch ms
  observed?: number
  predicted?: number
}

/** Merge observed and predicted series into one timeline keyed by timestamp. */
export function mergeSeries(observed: Reading[], predicted: Reading[]): TidePoint[] {
  const byTime = new Map<number, TidePoint>()
  for (const r of observed) {
    byTime.set(Date.parse(r.ts), { t: Date.parse(r.ts), observed: r.value })
  }
  for (const r of predicted) {
    const t = Date.parse(r.ts)
    const point = byTime.get(t)
    if (point) {
      point.predicted = r.value
    } else {
      byTime.set(t, { t, predicted: r.value })
    }
  }
  return [...byTime.values()].sort((a, b) => a.t - b.t)
}

/** |surge| beyond this (in meters) is colored as anomalous on the map.
 * Chosen empirically: calm-day residuals at these stations sit within ±0.1 m. */
export const SURGE_THRESHOLD = 0.15

export interface SurgeReading {
  t: number
  observed: number
  predicted: number
  /** observed minus predicted: positive means water is higher than the tide alone explains */
  surge: number
}

/** Latest moment where both an observation and a prediction exist. */
export function latestSurge(points: TidePoint[]): SurgeReading | null {
  for (let i = points.length - 1; i >= 0; i--) {
    const { t, observed, predicted } = points[i]
    if (observed !== undefined && predicted !== undefined) {
      return { t, observed, predicted, surge: observed - predicted }
    }
  }
  return null
}

export interface TideExtreme {
  kind: 'high' | 'low'
  t: number
  value: number
}

/** First local extremum in the predicted series after `nowMs`, i.e. the next high/low tide. */
export function nextExtreme(predicted: Reading[], nowMs: number = Date.now()): TideExtreme | null {
  const future = predicted
    .map((r) => ({ t: Date.parse(r.ts), value: r.value }))
    .filter((p) => p.t > nowMs)
    .sort((a, b) => a.t - b.t)
  for (let i = 1; i < future.length - 1; i++) {
    const [prev, cur, next] = [future[i - 1].value, future[i].value, future[i + 1].value]
    if (cur >= prev && cur > next) return { kind: 'high', t: future[i].t, value: cur }
    if (cur <= prev && cur < next) return { kind: 'low', t: future[i].t, value: cur }
  }
  return null
}

const HOUR_MS = 3600_000
const TICK_STEPS_HOURS = [1, 2, 3, 6, 12, 24]

/** Round-hour tick positions across [minMs, maxMs], at most `target` of them. */
export function hourTicks(minMs: number, maxMs: number, target = 7): number[] {
  const span = maxMs - minMs
  const step =
    (TICK_STEPS_HOURS.find((h) => span / (h * HOUR_MS) <= target) ?? 24) * HOUR_MS
  const ticks: number[] = []
  for (let t = Math.ceil(minMs / step) * step; t <= maxMs; t += step) {
    ticks.push(t)
  }
  return ticks
}

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const dayTimeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
})

/** "in 2h 14m" / "in 45 min" — used for the next-tide countdown. */
export function fmtDuration(ms: number): string {
  const mins = Math.max(0, Math.round(ms / 60_000))
  const h = Math.floor(mins / 60)
  return h > 0 ? `in ${h}h ${mins % 60}m` : `in ${mins} min`
}

export const fmtTime = (ms: number) => timeFmt.format(new Date(ms))
export const fmtDayTime = (ms: number) => dayTimeFmt.format(new Date(ms))

/* Data is metric everywhere internally (NOAA is queried in metric);
 * units apply only at the display boundary. */
export type Units = 'metric' | 'us'

const M_TO_FT = 3.28084

export const levelValue = (meters: number, units: Units) =>
  units === 'us' ? meters * M_TO_FT : meters

export const fmtLevel = (meters: number, units: Units, decimals = 2) =>
  `${levelValue(meters, units).toFixed(decimals)} ${units === 'us' ? 'ft' : 'm'}`

/** Signed level with an explicit sign and a true minus (U+2212): "+0.12 m" / "−0.30 m".
 * The shared formatter for surge residuals everywhere they're displayed. */
export const fmtSignedLevel = (meters: number, units: Units, decimals = 2) =>
  `${meters >= 0 ? '+' : '−'}${fmtLevel(Math.abs(meters), units, decimals)}`

export const tempValue = (celsius: number, units: Units) =>
  units === 'us' ? (celsius * 9) / 5 + 32 : celsius

export const fmtTemp = (celsius: number, units: Units) =>
  `${tempValue(celsius, units).toFixed(1)} ${units === 'us' ? '°F' : '°C'}`
