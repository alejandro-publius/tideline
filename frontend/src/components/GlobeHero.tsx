import { Component, lazy, Suspense, useMemo, useState, type ReactNode } from 'react'
import { fmtSignedLevel, type Units } from '../lib/tides'
import { surgeColor } from '../lib/globe'
import type { Station, StationOverview } from '../types'
import type { GlobeStation } from './globeScene'

// three.js + the 55 KB coastline TopoJSON only download once the hero mounts.
const Globe = lazy(() => import('./Globe'))

interface Props {
  stations: Station[]
  overviewById: Record<string, StationOverview>
  selectedId: string | null
  onSelect: (id: string) => void
  units: Units
}

/** Detect WebGL once; the globe degrades to a static banner without it. */
function detectWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl2') || canvas.getContext('webgl'))
    )
  } catch {
    return false
  }
}

/** A failed lazy chunk load (flaky network, ad blocker) must degrade to the
 * fallback banner, not white-screen the whole dashboard. */
class GlobeErrorBoundary extends Component<{
  fallback: ReactNode
  onFailed: () => void
  children: ReactNode
}> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch() {
    this.props.onFailed() // lets the hero hide globe-only UI like the drag hint
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export default function GlobeHero({ stations, overviewById, selectedId, onSelect, units }: Props) {
  const [webglOk] = useState(detectWebGL)
  const [globeFailed, setGlobeFailed] = useState(false)

  const globeStations = useMemo<GlobeStation[]>(
    () =>
      stations.map((s) => {
        const row = overviewById[s.id]
        return {
          id: s.id,
          name: s.name,
          state: s.state,
          lat: s.lat,
          lon: s.lon,
          surge: row?.surge ?? null,
          flooding: row?.flood_stage != null,
        }
      }),
    [stations, overviewById],
  )

  // The live headline: which coast is running most anomalous right now.
  const { mostAnomalous, floodingCount } = useMemo(() => {
    let top: GlobeStation | null = null
    let floods = 0
    for (const s of globeStations) {
      if (s.flooding) floods++
      if (s.surge != null && (top == null || Math.abs(s.surge) > Math.abs(top.surge!))) top = s
    }
    return { mostAnomalous: top, floodingCount: floods }
  }, [globeStations])

  const anomalyChip =
    mostAnomalous && mostAnomalous.surge != null ? (
      <button
        type="button"
        className="globe-anomaly"
        onClick={() => onSelect(mostAnomalous.id)}
        style={{ ['--anomaly-color' as string]: surgeColor(mostAnomalous.surge) }}
      >
        <span className="globe-anomaly-label">Most anomalous now</span>
        <span className="globe-anomaly-value">
          <span className="globe-anomaly-dot" />
          {mostAnomalous.name}, {mostAnomalous.state}
          <span className="globe-anomaly-surge">{fmtSignedLevel(mostAnomalous.surge, units)}</span>
        </span>
      </button>
    ) : null

  // Only claim liveness when at least one fresh surge reading is on screen —
  // the eyebrow must not contradict a scene full of muted "no data" pillars.
  const hasLiveData = mostAnomalous != null

  return (
    <section className="globe-hero" aria-label="3D surge globe">
      <div className="globe-stage">
        {webglOk ? (
          <GlobeErrorBoundary
            onFailed={() => setGlobeFailed(true)}
            fallback={
              <div className="globe-loading">
                The 3D view failed to load — the interactive map below has the same data.
              </div>
            }
          >
            <Suspense fallback={<div className="globe-loading">Rendering the coastline…</div>}>
              <Globe
                stations={globeStations}
                selectedId={selectedId}
                onSelect={onSelect}
                units={units}
              />
            </Suspense>
          </GlobeErrorBoundary>
        ) : (
          <div className="globe-loading">
            3D view needs WebGL — the interactive map below has the same data.
          </div>
        )}
      </div>

      <div className="globe-overlay">
        <div className="globe-intro">
          <span className="globe-eyebrow">
            {hasLiveData && <span className="globe-live-dot" />}
            {hasLiveData ? 'Live · NOAA CO-OPS' : 'NOAA CO-OPS'}
          </span>
          <h2 className="globe-title">The coastline, in three dimensions</h2>
          <p className="globe-lede">
            Every spike is a tide station. Its <strong>height</strong> and <strong>color</strong>{' '}
            are the storm-surge residual — how far the sea has drifted from the tide that
            astronomy alone predicts.
          </p>
        </div>

        {anomalyChip}

        <div className="globe-footer">
          {/* role="img" so the aria-label is exposed (labels on generic divs are ignored) */}
          <div
            className="globe-scale"
            role="img"
            aria-label="Surge color scale: blue is calm, orange is storm surge"
          >
            <span className="globe-scale-end">calm</span>
            <span className="globe-scale-bar" />
            <span className="globe-scale-end">storm surge</span>
          </div>
          {floodingCount > 0 && (
            <span className="globe-flood-note">
              {floodingCount} station{floodingCount > 1 ? 's' : ''} at flood stage
            </span>
          )}
          {webglOk && !globeFailed && (
            <span className="globe-hint">drag to explore · ctrl + scroll to zoom</span>
          )}
        </div>
      </div>
    </section>
  )
}
