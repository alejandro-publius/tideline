import type { Units } from './tides'
import type { Product } from '../types'

/** UI state that survives reload / is shareable as a link. */
export interface UrlState {
  station: string | null
  product: Product
  hours: number
  units: Units
}

export const DEFAULT_STATION = '9414290' // San Francisco
export const VALID_HOURS = [12, 24, 48, 72]

export function readUrlState(search: string): UrlState {
  const params = new URLSearchParams(search)
  const hours = Number(params.get('hours'))
  return {
    station: params.get('station'),
    product: params.get('product') === 'water_temperature' ? 'water_temperature' : 'water_level',
    hours: VALID_HOURS.includes(hours) ? hours : 24,
    units: params.get('units') === 'us' ? 'us' : 'metric',
  }
}

/** Query string for the given state; defaults are omitted so plain visits keep a clean URL. */
export function writeUrlState({ station, product, hours, units }: UrlState): string {
  const params = new URLSearchParams()
  if (station && station !== DEFAULT_STATION) params.set('station', station)
  if (product !== 'water_level') params.set('product', product)
  if (hours !== 24) params.set('hours', String(hours))
  if (units !== 'metric') params.set('units', units)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}
