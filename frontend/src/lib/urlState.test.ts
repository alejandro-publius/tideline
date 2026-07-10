import { describe, expect, it } from 'vitest'
import { DEFAULT_STATION, readUrlState, writeUrlState } from './urlState'

describe('readUrlState', () => {
  it('reads a full state from the query string', () => {
    expect(readUrlState('?station=1612340&product=water_temperature&hours=48')).toEqual({
      station: '1612340',
      product: 'water_temperature',
      hours: 48,
    })
  })

  it('falls back to defaults for missing or invalid values', () => {
    expect(readUrlState('?product=banana&hours=999')).toEqual({
      station: null,
      product: 'water_level',
      hours: 24,
    })
  })
})

describe('writeUrlState', () => {
  it('omits defaults so a plain visit keeps a clean URL', () => {
    expect(
      writeUrlState({ station: DEFAULT_STATION, product: 'water_level', hours: 24 }),
    ).toBe('')
  })

  it('round-trips through readUrlState', () => {
    const state = { station: '9447130', product: 'water_temperature' as const, hours: 72 }

    expect(readUrlState(writeUrlState(state))).toEqual(state)
  })
})
