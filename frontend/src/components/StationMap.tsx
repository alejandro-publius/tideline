import { latLng, latLngBounds } from 'leaflet'
import { useEffect } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { useChartTheme } from '../theme'
import type { Station } from '../types'

interface Props {
  stations: Station[]
  selectedId: string | null
  onSelect: (id: string) => void
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

export default function StationMap({ stations, selectedId, onSelect }: Props) {
  const theme = useChartTheme()
  const bounds = latLngBounds(stations.map((s) => [s.lat, s.lon] as [number, number])).pad(0.12)

  return (
    <MapContainer bounds={bounds} scrollWheelZoom={true} className="station-map">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <InvalidateOnResize />
      <PanToSelection station={stations.find((s) => s.id === selectedId)} />
      {stations.map((station) => {
        const selected = station.id === selectedId
        return (
          <CircleMarker
            key={station.id}
            center={[station.lat, station.lon]}
            radius={selected ? 9 : 6.5}
            pathOptions={{
              color: selected ? theme.surface : '#1c5cab',
              weight: selected ? 2.5 : 1,
              fillColor: theme.observed,
              fillOpacity: selected ? 1 : 0.8,
            }}
            eventHandlers={{ click: () => onSelect(station.id) }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              {station.name}, {station.state}
            </Tooltip>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
