import { describe, expect, it } from 'vitest'
import type { Reading } from '../types'
import {
  fmtDuration,
  fmtLevel,
  fmtTemp,
  hourTicks,
  latestSurge,
  mergeSeries,
  nextExtreme,
} from './tides'

const HOUR = 3600_000

const reading = (iso: string, value: number): Reading => ({ ts: iso, value })

describe('mergeSeries', () => {
  it('merges observed and predicted readings that share a timestamp', () => {
    const merged = mergeSeries(
      [reading('2026-07-09T10:00:00Z', 1.2)],
      [reading('2026-07-09T10:00:00Z', 1.0), reading('2026-07-09T11:00:00Z', 1.4)],
    )

    expect(merged).toEqual([
      { t: Date.parse('2026-07-09T10:00:00Z'), observed: 1.2, predicted: 1.0 },
      { t: Date.parse('2026-07-09T11:00:00Z'), predicted: 1.4 },
    ])
  })

  it('sorts the merged timeline chronologically', () => {
    const merged = mergeSeries(
      [reading('2026-07-09T12:00:00Z', 2), reading('2026-07-09T10:00:00Z', 1)],
      [],
    )

    expect(merged.map((p) => p.observed)).toEqual([1, 2])
  })
})

describe('latestSurge', () => {
  it('uses the most recent point where both series exist', () => {
    const points = mergeSeries(
      [reading('2026-07-09T10:00:00Z', 1.5), reading('2026-07-09T11:00:00Z', 1.8)],
      [reading('2026-07-09T10:00:00Z', 1.0), reading('2026-07-09T11:00:00Z', 1.6)],
    )

    const surge = latestSurge(points)

    expect(surge?.t).toBe(Date.parse('2026-07-09T11:00:00Z'))
    expect(surge?.surge).toBeCloseTo(0.2)
  })

  it('ignores prediction-only points at the tail (the future)', () => {
    const points = mergeSeries(
      [reading('2026-07-09T10:00:00Z', 1.5)],
      [reading('2026-07-09T10:00:00Z', 1.0), reading('2026-07-09T12:00:00Z', 2.0)],
    )

    expect(latestSurge(points)?.t).toBe(Date.parse('2026-07-09T10:00:00Z'))
  })

  it('returns null when the series never overlap', () => {
    const points = mergeSeries([reading('2026-07-09T10:00:00Z', 1.5)], [])

    expect(latestSurge(points)).toBeNull()
  })
})

describe('nextExtreme', () => {
  const now = Date.parse('2026-07-09T10:00:00Z')
  const at = (hoursAhead: number, value: number) =>
    reading(new Date(now + hoursAhead * HOUR).toISOString(), value)

  it('finds the next high tide (local maximum after now)', () => {
    const extreme = nextExtreme([at(-1, 0.5), at(1, 1.0), at(2, 1.8), at(3, 1.2)], now)

    expect(extreme).toEqual({ kind: 'high', t: now + 2 * HOUR, value: 1.8 })
  })

  it('finds the next low tide (local minimum after now)', () => {
    const extreme = nextExtreme([at(1, 1.0), at(2, 0.2), at(3, 0.9)], now)

    expect(extreme?.kind).toBe('low')
    expect(extreme?.value).toBe(0.2)
  })

  it('returns null when the future window is monotonic', () => {
    expect(nextExtreme([at(1, 1.0), at(2, 1.2), at(3, 1.4)], now)).toBeNull()
  })

  it('ignores extremes in the past', () => {
    const extreme = nextExtreme([at(-3, 0.1), at(-2, 2.0), at(-1, 0.5), at(1, 1.0)], now)

    expect(extreme).toBeNull()
  })
})

describe('hourTicks', () => {
  it('places ticks on round hours', () => {
    const start = Date.parse('2026-07-09T10:17:00Z')
    const ticks = hourTicks(start, start + 12 * HOUR)

    for (const tick of ticks) {
      expect(tick % HOUR).toBe(0)
    }
  })

  it('never exceeds the target count', () => {
    const start = Date.parse('2026-07-09T00:00:00Z')
    for (const span of [6, 12, 24, 48, 72, 120]) {
      expect(hourTicks(start, start + span * HOUR).length).toBeLessThanOrEqual(7)
    }
  })

  it('keeps every tick inside the range', () => {
    const start = Date.parse('2026-07-09T10:17:00Z')
    const end = start + 24 * HOUR
    for (const tick of hourTicks(start, end)) {
      expect(tick).toBeGreaterThanOrEqual(start)
      expect(tick).toBeLessThanOrEqual(end)
    }
  })
})

describe('unit conversion', () => {
  it('formats levels in meters or feet', () => {
    expect(fmtLevel(1, 'metric')).toBe('1.00 m')
    expect(fmtLevel(1, 'us')).toBe('3.28 ft')
    expect(fmtLevel(-0.35, 'us')).toBe('-1.15 ft')
  })

  it('formats temperatures in °C or °F', () => {
    expect(fmtTemp(20, 'metric')).toBe('20.0 °C')
    expect(fmtTemp(20, 'us')).toBe('68.0 °F')
    expect(fmtTemp(0, 'us')).toBe('32.0 °F')
  })
})

describe('fmtDuration', () => {
  it('formats hours and minutes', () => {
    expect(fmtDuration(2 * HOUR + 14 * 60_000)).toBe('in 2h 14m')
  })

  it('formats sub-hour durations as minutes', () => {
    expect(fmtDuration(45 * 60_000)).toBe('in 45 min')
  })

  it('clamps negatives to zero', () => {
    expect(fmtDuration(-5000)).toBe('in 0 min')
  })
})
