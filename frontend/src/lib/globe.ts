/**
 * Pure geometry + color helpers for the 3D globe.
 *
 * Deliberately free of any `three` / WebGL import so it can be unit-tested in
 * jsdom and stay out of the eager bundle — the heavy scene code lives in
 * `components/globeScene.ts`, which is only pulled in by the lazy Globe chunk.
 */

export const DEG2RAD = Math.PI / 180

/**
 * Project a geographic coordinate onto a sphere of the given radius.
 *
 * Uses the classic equirectangular convention (phi from the +Y pole, theta
 * offset by 180°). The absolute handedness is unimportant — coastlines and
 * station pillars are projected with this same function, so they always align.
 */
export function latLngToVec3(lat: number, lon: number, radius = 1): [number, number, number] {
  const phi = (90 - lat) * DEG2RAD
  const theta = (lon + 180) * DEG2RAD
  return [
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  ]
}

/**
 * Surge magnitude (m) at which "confidence" bottoms out — i.e. the sea has
 * departed so far from its astronomical prediction that the pillar glows the
 * hottest colour. Calm-day residuals sit within ±0.1 m (see SURGE_THRESHOLD),
 * so 0.6 m spans a calm→storm range with room to spare.
 */
export const SURGE_FULL_SCALE = 0.6

/**
 * Map a surge residual to a [0, 1] "confidence" that the sea is behaving as
 * astronomy alone predicts: 1 when observed matches prediction, falling toward
 * 0 as the residual grows. This is the value the AlphaFold-style colour scale
 * is keyed on — the homage is deliberate: high confidence reads blue, low
 * confidence (a big storm-surge residual) reads orange.
 */
export function surgeConfidence(surgeMeters: number, fullScale = SURGE_FULL_SCALE): number {
  const anomaly = Math.min(Math.abs(surgeMeters) / fullScale, 1)
  return 1 - anomaly
}

type RGB = readonly [number, number, number]

/**
 * AlphaFold's pLDDT confidence palette, keyed by our [0, 1] confidence:
 * dark blue (very high) → cyan → yellow → orange (very low).
 */
const CONFIDENCE_STOPS: ReadonlyArray<readonly [number, RGB]> = [
  [1.0, [0, 83, 214]], //  #0053D6  very high
  [0.75, [101, 203, 243]], //  #65CBF3  confident
  [0.5, [255, 219, 19]], //  #FFDB13  low
  [0.0, [255, 125, 69]], //  #FF7D45  very low
]

const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x)

const toHex = ([r, g, b]: RGB) =>
  '#' +
  [r, g, b].map((c) => Math.round(clamp01(c / 255) * 255).toString(16).padStart(2, '0')).join('')

const lerp = (a: number, b: number, t: number) => a + (b - a) * t

/**
 * Colour for a given confidence in [0, 1], linearly interpolated between the
 * AlphaFold stops. Returns a `#rrggbb` string (consumable by both CSS and
 * `THREE.Color`), which keeps this function trivially testable.
 */
export function confidenceColor(confidence: number): string {
  const c = clamp01(confidence)
  // stops run high→low confidence; find the pair bracketing `c`
  for (let i = 0; i < CONFIDENCE_STOPS.length - 1; i++) {
    const [hi, hiRGB] = CONFIDENCE_STOPS[i]
    const [lo, loRGB] = CONFIDENCE_STOPS[i + 1]
    if (c <= hi && c >= lo) {
      const t = hi === lo ? 0 : (c - lo) / (hi - lo)
      return toHex([lerp(loRGB[0], hiRGB[0], t), lerp(loRGB[1], hiRGB[1], t), lerp(loRGB[2], hiRGB[2], t)])
    }
  }
  return toHex(c >= 1 ? CONFIDENCE_STOPS[0][1] : CONFIDENCE_STOPS[CONFIDENCE_STOPS.length - 1][1])
}

/** Convenience: the pillar/marker colour straight from a surge residual. */
export const surgeColor = (surgeMeters: number): string =>
  confidenceColor(surgeConfidence(surgeMeters))

/**
 * Radial height of a station's surge pillar, as a fraction of the globe radius.
 * A small floor keeps calm stations visible as luminous nubs; the magnitude
 * term lets a storm spike stretch to ~0.6 R. Height is unsigned — a pillar's
 * length encodes how anomalous the sea is, its colour how confidently so.
 */
export function pillarHeight(surgeMeters: number | null | undefined, radius = 1): number {
  const mag = surgeMeters == null ? 0 : Math.min(Math.abs(surgeMeters) / SURGE_FULL_SCALE, 1.4)
  return (0.035 + mag * 0.42) * radius
}
