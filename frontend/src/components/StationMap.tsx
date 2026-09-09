import { latLng, latLngBounds } from 'leaflet'
import { useEffect } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { fmtLevel, fmtSignedLevel, SURGE_THRESHOLD, type Units } from '../lib/tides'
import { useChartTheme, type ChartTheme } from '../theme'
import type { Station, StationOverview } from '../types'

interface Props {
  stations: Station[]
  selectedId: string | null
  onSelect: (id: string) => void
  /** latest overview row per station id; missing key = no data yet */
  overviewById: Record<string, StationOverview>
  units: Units
}

/** Leaflet only tracks window resizes; when the layout itself grows (e.g. the
 * chart column gets taller and stretches the map card) it leaves an untiled
 * dead zone. Watch the container and tell Leaflet about size changes. */
function InvalidateOnResize() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

/** Pans/zooms to the selected station when it's outside the current view
 * (e.g. picked from the dropdown) — map clicks don't move the viewport. */
function PanToSelection({ station }: { station: Station | undefined }) {
  const map = useMap()
  useEffect(() => {
    if (!station) return
    const target = latLng(station.lat, station.lon)
    if (!map.getBounds().pad(-0.15).contains(target)) {
      const zoom = Math.max(map.getZoom(), 6)
      // honor the OS "reduce motion" setting: jump instead of animating
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        map.setView(target, zoom, { animate: false })
      } else {
        map.flyTo(target, zoom, { duration: 0.8 })
      }
    }
  }, [map, station])
  return null
}

/** Diverging encoding: red above prediction, blue below, gray near zero. */
function markerColor(surge: number | null | undefined, theme: ChartTheme): string {
  if (surge == null) return theme.muted
  if (surge >= SURGE_THRESHOLD) return theme.surgeAbove
  if (surge <= -SURGE_THRESHOLD) return theme.surgeBelow
  return theme.muted
}

export default function StationMap({ stations, selectedId, onSelect, overviewById, units }: Props) {
  const threshold = fmtLevel(SURGE_THRESHOLD, units)
  const theme = useChartTheme()
  const bounds = latLngBounds(stations.map((s) => [s.lat, s.lon] as [number, number])).pad(0.12)

  return (
    <div className="map-wrap">
      <MapContainer bounds={bounds} scrollWheelZoom={true} className="station-map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <InvalidateOnResize />
        <PanToSelection station={stations.find((s) => s.id === selectedId)} />
        {stations.map((station) => {
          const selected = station.id === selectedId
          const row = overviewById[station.id]
          const surge = row?.surge ?? null
          const flooding = row?.flood_stage ?? null
          const known = surge != null
          const fill = flooding ? theme.surgeAbove : markerColor(surge, theme)
          return (
            <CircleMarker
              key={station.id}
              center={[station.lat, station.lon]}
              radius={selected ? 9 : flooding ? 8.5 : 6.5}
              pathOptions={{
                color: selected ? theme.surface : flooding ? theme.surgeAbove : fill,
                weight: selected ? 2.5 : flooding ? 2 : 1,
                dashArray: known ? undefined : '3 3',
                fillColor: fill,
                fillOpacity: known ? (selected || flooding ? 1 : 0.85) : 0.15,
              }}
              eventHandlers={{ click: () => onSelect(station.id) }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {station.name}, {station.state}
                {known && ` · surge ${fmtSignedLevel(surge, units)}`}
                {flooding && ` · ${flooding.toUpperCase()} FLOODING`}
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
      {/* role="img" so the aria-label is actually exposed (labels on generic divs are ignored) */}
      <div
        className="map-legend"
        role="img"
        aria-label="Surge legend: red is above prediction, blue below, gray near zero, hollow no data"
      >
        <span className="legend-item">
          <span className="legend-dot" style={{ background: theme.surgeAbove }} /> ≥ +{threshold}
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: theme.surgeBelow }} /> ≤ −{threshold}
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: theme.muted }} /> near zero
        </span>
        <span className="legend-item">
          <span className="legend-dot legend-dot--hollow" style={{ borderColor: theme.muted }} />{' '}
          no data
        </span>
      </div>
    </div>
  )
}
