import { latLng, latLngBounds } from 'leaflet'
import { useEffect } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { SURGE_THRESHOLD } from '../lib/tides'
import { useChartTheme, type ChartTheme } from '../theme'
import type { Station } from '../types'

interface Props {
  stations: Station[]
  selectedId: string | null
  onSelect: (id: string) => void
  /** latest surge per station id; undefined key or null value = unknown */
  surgeById: Record<string, number | null>
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
      map.flyTo(target, Math.max(map.getZoom(), 6), { duration: 0.8 })
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

const fmtSurge = (surge: number) =>
  `${surge >= 0 ? '+' : '−'}${Math.abs(surge).toFixed(2)} m`

export default function StationMap({ stations, selectedId, onSelect, surgeById }: Props) {
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
          const surge = surgeById[station.id]
          const known = surge != null
          return (
            <CircleMarker
              key={station.id}
              center={[station.lat, station.lon]}
              radius={selected ? 9 : 6.5}
              pathOptions={{
                color: selected ? theme.surface : markerColor(surge, theme),
                weight: selected ? 2.5 : 1,
                dashArray: known ? undefined : '3 3',
                fillColor: markerColor(surge, theme),
                fillOpacity: known ? (selected ? 1 : 0.85) : 0.15,
              }}
              eventHandlers={{ click: () => onSelect(station.id) }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {station.name}, {station.state}
                {known && ` · surge ${fmtSurge(surge)}`}
              </Tooltip>
            </CircleMarker>
          )
        })}
      </MapContainer>
      <div className="map-legend" aria-label="Surge legend">
        <span className="legend-item">
          <span className="legend-dot" style={{ background: theme.surgeAbove }} /> ≥ +
          {SURGE_THRESHOLD} m
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ background: theme.surgeBelow }} /> ≤ −
          {SURGE_THRESHOLD} m
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
