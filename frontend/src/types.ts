export interface Station {
  id: string
  name: string
  state: string
  lat: number
  lon: number
  /** NWS coastal flood thresholds, meters above MLLW */
  flood_minor: number | null
  flood_moderate: number | null
  flood_major: number | null
}

export type FloodStage = 'minor' | 'moderate' | 'major'

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

export interface StationOverview {
  station: Station
  ts: string | null
  observed: number | null
  predicted: number | null
  surge: number | null
  flood_stage: FloodStage | null
}
