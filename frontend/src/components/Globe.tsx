import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { fmtSignedLevel, type Units } from '../lib/tides'
import { createGlobeScene, type GlobeScene, type GlobeStation } from './globeScene'

interface Props {
  stations: GlobeStation[]
  selectedId: string | null
  onSelect: (id: string) => void
  units: Units
}

interface HoverState {
  station: GlobeStation
  x: number
  y: number
}

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(REDUCED_MOTION_QUERY)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    () => window.matchMedia(REDUCED_MOTION_QUERY).matches,
    () => false,
  )
}

/**
 * The lazily-loaded WebGL globe. Builds the three.js scene once, then forwards
 * data/selection/motion changes to it imperatively; pauses rendering whenever it
 * scrolls off-screen or the tab is hidden.
 */
export default function Globe({ stations, selectedId, onSelect, units }: Props) {
  const mountRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<GlobeScene | null>(null)
  const [hover, setHover] = useState<HoverState | null>(null)
  const reducedMotion = usePrefersReducedMotion()

  // Build the scene once; tear it down fully on unmount (StrictMode-safe).
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    const scene = createGlobeScene(
      mount,
      {
        onSelect,
        onHover: (station, clientX, clientY) => {
          if (!station) return setHover(null)
          const rect = mount.getBoundingClientRect()
          // Clamp inside the stage so the tooltip never clips against the
          // hero's overflow:hidden edges.
          const x = Math.min(Math.max(clientX - rect.left, 70), rect.width - 70)
          const y = Math.max(clientY - rect.top, 48)
          setHover({ station, x, y })
        },
      },
      { reducedMotion: window.matchMedia(REDUCED_MOTION_QUERY).matches },
    )
    sceneRef.current = scene

    const resizeObserver = new ResizeObserver(() => scene.resize())
    resizeObserver.observe(mount)

    // Only render while actually on-screen and the tab is visible.
    let onScreen = true
    const syncActive = () => scene.setActive(onScreen && document.visibilityState === 'visible')
    const intersectionObserver = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting
        syncActive()
      },
      { threshold: 0.01 },
    )
    intersectionObserver.observe(mount)
    document.addEventListener('visibilitychange', syncActive)

    return () => {
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      document.removeEventListener('visibilitychange', syncActive)
      scene.dispose()
      sceneRef.current = null
    }
    // Deliberately build-once: the scene is expensive to construct and every
    // prop change is forwarded imperatively below. onSelect is App's setState
    // dispatcher, which React guarantees is stable across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    sceneRef.current?.setStations(stations)
  }, [stations])

  useEffect(() => {
    sceneRef.current?.setSelected(selectedId)
  }, [selectedId])

  useEffect(() => {
    sceneRef.current?.setReducedMotion(reducedMotion)
  }, [reducedMotion])

  return (
    <div
      className="globe-canvas"
      ref={mountRef}
      role="img"
      aria-label="Interactive 3D globe of NOAA tide stations. Click a spike to select a station; keyboard users can pick a station from the station list below."
    >
      {hover && (
        <div className="globe-tooltip" style={{ left: hover.x, top: hover.y }} aria-hidden="true">
          <span className="globe-tooltip-name">
            {hover.station.name}, {hover.station.state}
          </span>
          <span className="globe-tooltip-surge">
            {hover.station.surge == null
              ? 'no fresh reading'
              : `surge ${fmtSignedLevel(hover.station.surge, units)}`}
            {hover.station.flooding && ' · flooding'}
          </span>
        </div>
      )}
    </div>
  )
}
