import type { Units } from '../lib/tides'
import { VALID_HOURS } from '../lib/urlState'
import type { Product } from '../types'

const PRODUCTS: { value: Product; label: string }[] = [
  { value: 'water_level', label: 'Water level' },
  { value: 'water_temperature', label: 'Water temp' },
]

const UNITS: { value: Units; label: string }[] = [
  { value: 'metric', label: 'm · °C' },
  { value: 'us', label: 'ft · °F' },
]

interface Props {
  stationId: string
  product: Product
  onProduct: (p: Product) => void
  hours: number
  onHours: (h: number) => void
  units: Units
  onUnits: (u: Units) => void
}

export default function Controls({
  stationId,
  product,
  onProduct,
  hours,
  onHours,
  units,
  onUnits,
}: Props) {
  return (
    <div className="controls">
      <div className="seg" role="group" aria-label="Data product">
        {PRODUCTS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={product === value}
            onClick={() => onProduct(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="seg" role="group" aria-label="Time range">
        {VALID_HOURS.map((h) => (
          <button key={h} type="button" aria-pressed={hours === h} onClick={() => onHours(h)}>
            {h}h
          </button>
        ))}
      </div>
      <div className="seg" role="group" aria-label="Units">
        {UNITS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={units === value}
            onClick={() => onUnits(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {/* native download; the API sets Content-Disposition with a per-station filename */}
      <a
        className="export-link"
        href={`/api/stations/${stationId}/export?days=365`}
        download
        title="Download this station’s observed vs. predicted history (CSV)"
      >
        ↓ CSV
      </a>
    </div>
  )
}
