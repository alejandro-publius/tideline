import type { Product } from '../types'

const PRODUCTS: { value: Product; label: string }[] = [
  { value: 'water_level', label: 'Water level' },
  { value: 'water_temperature', label: 'Water temp' },
]

const RANGES = [12, 24, 48, 72]

interface Props {
  product: Product
  onProduct: (p: Product) => void
  hours: number
  onHours: (h: number) => void
}

export default function Controls({ product, onProduct, hours, onHours }: Props) {
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
        {RANGES.map((h) => (
          <button key={h} type="button" aria-pressed={hours === h} onClick={() => onHours(h)}>
            {h}h
          </button>
        ))}
      </div>
    </div>
  )
}
