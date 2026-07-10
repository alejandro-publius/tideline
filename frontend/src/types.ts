export interface Station {
  id: string
  name: string
  state: string
  lat: number
  lon: number
}

export type Product = 'water_level' | 'water_temperature'

export type SeriesSource = 'noaa' | 'cache' | 'stale'

export interface Reading {
  ts: string // ISO 8601, UTC
  value: number
}

export interface Series {
  station_id: string
  product: string
  source: SeriesSource
  fetched_at: string | null
  readings: Reading[]
}
