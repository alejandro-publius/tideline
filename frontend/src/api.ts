import type { Product, Series, Station } from './types'

// Same-origin in production (the backend serves the built frontend);
// the Vite dev server proxies /api instead.
const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { signal })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      detail = (await resp.json()).detail ?? detail
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(resp.status, detail)
  }
  return resp.json() as Promise<T>
}

export const fetchStations = (signal?: AbortSignal) => getJson<Station[]>('/api/stations', signal)

export const fetchReadings = (
  stationId: string,
  product: Product,
  hours: number,
  signal?: AbortSignal,
) => getJson<Series>(`/api/stations/${stationId}/readings?product=${product}&hours=${hours}`, signal)

// Lookback follows the selected range; the backend caps lookahead at 48h
export const fetchPredictions = (stationId: string, hours: number, signal?: AbortSignal) =>
  getJson<Series>(`/api/stations/${stationId}/predictions?hours=${hours}`, signal)
