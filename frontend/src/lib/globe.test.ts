import { describe, expect, it } from 'vitest'
import {
  confidenceColor,
  latLngToVec3,
  pillarHeight,
  SURGE_FULL_SCALE,
  surgeColor,
  surgeConfidence,
} from './globe'

const mag = ([x, y, z]: [number, number, number]) => Math.hypot(x, y, z)

describe('latLngToVec3', () => {
  it('places the north pole on the +Y axis', () => {
    const [x, y, z] = latLngToVec3(90, 0, 1)
    expect(y).toBeCloseTo(1, 6)
    expect(x).toBeCloseTo(0, 6)
    expect(z).toBeCloseTo(0, 6)
  })

  it('places the south pole on the −Y axis', () => {
    const [, y] = latLngToVec3(-90, 123, 1)
    expect(y).toBeCloseTo(-1, 6)
  })

  it('keeps every point on the sphere of the requested radius', () => {
    for (const [lat, lon] of [
      [0, 0],
      [37.8, -122.5], // San Francisco
      [40.7, -74.0], // The Battery
      [21.3, -157.9], // Honolulu
    ] as const) {
      expect(mag(latLngToVec3(lat, lon, 2.5))).toBeCloseTo(2.5, 6)
    }
  })

  it('maps antipodal points to opposite vectors', () => {
    const a = latLngToVec3(37.8, -122.5, 1)
    const b = latLngToVec3(-37.8, 57.5, 1) // antipode: negate lat, +180° lon
    expect(a[0]).toBeCloseTo(-b[0], 6)
    expect(a[1]).toBeCloseTo(-b[1], 6)
    expect(a[2]).toBeCloseTo(-b[2], 6)
  })
})

describe('surgeConfidence', () => {
  it('is full confidence when the sea matches its prediction', () => {
    expect(surgeConfidence(0)).toBe(1)
  })

  it('bottoms out at zero once the residual reaches full scale', () => {
    expect(surgeConfidence(SURGE_FULL_SCALE)).toBe(0)
    expect(surgeConfidence(2 * SURGE_FULL_SCALE)).toBe(0)
  })

  it('is symmetric in the sign of the residual (magnitude is what matters)', () => {
    expect(surgeConfidence(0.3)).toBeCloseTo(surgeConfidence(-0.3), 12)
  })

  it('falls monotonically as the residual grows', () => {
    expect(surgeConfidence(0.1)).toBeGreaterThan(surgeConfidence(0.3))
    expect(surgeConfidence(0.3)).toBeGreaterThan(surgeConfidence(0.5))
  })
})

describe('confidenceColor', () => {
  it('anchors the AlphaFold pLDDT endpoints', () => {
    expect(confidenceColor(1)).toBe('#0053d6') // very high → dark blue
    expect(confidenceColor(0)).toBe('#ff7d45') // very low → orange
  })

  it('hits the cyan and yellow stops at the confidence breakpoints', () => {
    expect(confidenceColor(0.75)).toBe('#65cbf3')
    expect(confidenceColor(0.5)).toBe('#ffdb13')
  })

  it('clamps out-of-range confidence instead of producing garbage', () => {
    expect(confidenceColor(2)).toBe('#0053d6')
    expect(confidenceColor(-1)).toBe('#ff7d45')
  })

  it('always returns a well-formed hex triple', () => {
    for (let c = 0; c <= 1.0001; c += 0.05) {
      expect(confidenceColor(c)).toMatch(/^#[0-9a-f]{6}$/)
    }
  })

  it('surgeColor is calm-blue near zero and hot near full scale', () => {
    expect(surgeColor(0)).toBe('#0053d6')
    expect(surgeColor(SURGE_FULL_SCALE)).toBe('#ff7d45')
  })
})

describe('pillarHeight', () => {
  it('gives calm stations a small but non-zero floor', () => {
    const calm = pillarHeight(0)
    expect(calm).toBeGreaterThan(0)
    expect(calm).toBeLessThan(0.1)
  })

  it('grows with the magnitude of the residual', () => {
    expect(pillarHeight(0.3)).toBeGreaterThan(pillarHeight(0.1))
    expect(pillarHeight(-0.5)).toBeGreaterThan(pillarHeight(-0.2))
  })

  it('treats a missing surge as calm rather than throwing', () => {
    expect(pillarHeight(null)).toBe(pillarHeight(0))
    expect(pillarHeight(undefined)).toBe(pillarHeight(0))
  })

  it('scales with the globe radius', () => {
    expect(pillarHeight(0.3, 2)).toBeCloseTo(2 * pillarHeight(0.3, 1), 12)
  })
})
