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

export type AnomalyKind = 'flood' | 'surge'

/** An anomaly the detector recorded off the event path (see ADR 0007). */
export interface Anomaly {
  station_id: string
  station_name: string
  ts: string // ISO 8601, UTC
  value: number
  kind: AnomalyKind
  /** flood: minor | moderate | major. surge: above | below. */
  severity: string
  /** observed - predicted, meters. Null for flood anomalies. */
  residual: number | null
  detected_at: string
}
