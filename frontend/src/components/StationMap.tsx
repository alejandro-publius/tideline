import { latLngBounds } from 'leaflet'
import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import { useChartTheme } from '../theme'
import type { Station } from '../types'

interface Props {
  stations: Station[]
  selectedId: string | null
  onSelect: (id: string) => void
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
