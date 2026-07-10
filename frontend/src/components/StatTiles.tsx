import { useMemo } from 'react'
import {
  fmtCelsius,
  fmtMeters,
  fmtTime,
  latestSurge,
  nextExtreme,
  type TidePoint,
} from '../lib/tides'
import type { Product, Reading } from '../types'

interface Props {
  points: TidePoint[]
  predicted: Reading[]
  product: Product
  nowMs: number
}

interface Tile {
  label: string
  value: string
  sub?: string
}

export default function StatTiles({ points, predicted, product, nowMs }: Props) {
  const tiles = useMemo<Tile[]>(() => {
    if (product === 'water_temperature') {
      const temps = points.filter((p) => p.observed !== undefined).map((p) => p.observed as number)
      if (temps.length === 0) return []
      return [
        { label: 'Current', value: fmtCelsius(temps[temps.length - 1]) },
        { label: 'Window low', value: fmtCelsius(Math.min(...temps)) },
        { label: 'Window high', value: fmtCelsius(Math.max(...temps)) },
      ]
    }

    const surge = latestSurge(points)
    const extreme = nextExtreme(predicted, nowMs)
    if (!surge) return []
    const sign = surge.surge >= 0 ? '+' : '−'
    return [
      { label: 'Observed', value: fmtMeters(surge.observed), sub: fmtTime(surge.t) },
      { label: 'Predicted', value: fmtMeters(surge.predicted), sub: 'astronomical tide' },
      {
        label: 'Surge residual',
        value: `${sign}${fmtMeters(Math.abs(surge.surge))}`,
        sub: surge.surge >= 0 ? 'above prediction' : 'below prediction',
      },
      extreme
        ? {
            label: `Next ${extreme.kind} tide`,
            value: fmtTime(extreme.t),
            sub: fmtMeters(extreme.value),
          }
        : { label: 'Next tide', value: '—' },
    ]
  }, [points, predicted, product, nowMs])

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
