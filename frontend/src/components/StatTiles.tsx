import { useMemo } from 'react'
import {
  fmtDuration,
  fmtLevel,
  fmtTemp,
  fmtTime,
  latestSurge,
  nextExtreme,
  type TidePoint,
  type Units,
} from '../lib/tides'
import type { Product, Reading } from '../types'

interface Props {
  points: TidePoint[]
  predicted: Reading[]
  product: Product
  nowMs: number
  units: Units
  /** NWS minor flood threshold (meters MLLW) for the selected station */
  floodMinor?: number | null
}

interface Tile {
  label: string
  value: string
  sub?: string
}

export default function StatTiles({ points, predicted, product, nowMs, units, floodMinor }: Props) {
  const tiles = useMemo<Tile[]>(() => {
    if (product === 'water_temperature') {
      const temps = points.filter((p) => p.observed !== undefined).map((p) => p.observed as number)
      if (temps.length === 0) return []
      return [
        { label: 'Current', value: fmtTemp(temps[temps.length - 1], units) },
        { label: 'Window low', value: fmtTemp(Math.min(...temps), units) },
        { label: 'Window high', value: fmtTemp(Math.max(...temps), units) },
      ]
    }

    const surge = latestSurge(points)
    const extreme = nextExtreme(predicted, nowMs)
    if (!surge) return []
    const sign = surge.surge >= 0 ? '+' : '−'
    const floodTile: Tile[] = []
    if (floodMinor != null) {
      const headroom = floodMinor - surge.observed
      floodTile.push(
        headroom > 0
          ? {
              label: 'To minor flood',
              value: fmtLevel(headroom, units),
              sub: `NWS stage at ${fmtLevel(floodMinor, units)}`,
            }
          : {
              label: 'Flood stage',
              value: 'Flooding',
              sub: `${fmtLevel(-headroom, units)} above NWS minor stage`,
            },
      )
    }
    return [
      { label: 'Observed', value: fmtLevel(surge.observed, units), sub: fmtTime(surge.t) },
      { label: 'Predicted', value: fmtLevel(surge.predicted, units), sub: 'astronomical tide' },
      {
        label: 'Surge residual',
        value: `${sign}${fmtLevel(Math.abs(surge.surge), units)}`,
        sub: surge.surge >= 0 ? 'above prediction' : 'below prediction',
      },
      extreme
        ? {
            label: `Next ${extreme.kind} tide`,
            value: fmtTime(extreme.t),
            sub: `${fmtDuration(extreme.t - nowMs)} · ${fmtLevel(extreme.value, units)}`,
          }
        : { label: 'Next tide', value: '—' },
      ...floodTile,
    ]
  }, [points, predicted, product, nowMs, units, floodMinor])

  if (tiles.length === 0) return null
  return (
    <div className="tiles">
      {tiles.map((tile) => (
        <div key={tile.label} className="card tile">
          <span className="tile-label">{tile.label}</span>
          <span className="tile-value">{tile.value}</span>
          {tile.sub && <span className="tile-sub">{tile.sub}</span>}
        </div>
      ))}
    </div>
  )
}
