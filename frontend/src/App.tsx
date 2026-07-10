import { useEffect, useMemo, useState } from 'react'
import { fetchPredictions, fetchReadings, fetchStations } from './api'
import Controls from './components/Controls'
import ReadingsChart from './components/ReadingsChart'
import SourceBadge from './components/SourceBadge'
import StationMap from './components/StationMap'
import StatTiles from './components/StatTiles'
import { mergeSeries } from './lib/tides'
import type { Product, Series, Station } from './types'

const DEFAULT_STATION = '9414290' // San Francisco

const errorMessage = (err: unknown) => (err instanceof Error ? err.message : 'Request failed')

export default function App() {
  const [stations, setStations] = useState<Station[]>([])
  const [stationsError, setStationsError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [product, setProduct] = useState<Product>('water_level')
  const [hours, setHours] = useState(24)

  const [observed, setObserved] = useState<Series | null>(null)
  const [predicted, setPredicted] = useState<Series | null>(null)
  const [loading, setLoading] = useState(true)
  const [seriesError, setSeriesError] = useState<string | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchStations(ctrl.signal)
      .then((list) => {
        setStations(list)
        setSelectedId((current) => current ?? DEFAULT_STATION)
      })
      .catch((err) => {
        if (!ctrl.signal.aborted) setStationsError(errorMessage(err))
      })
    return () => ctrl.abort()
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const ctrl = new AbortController()
    setLoading(true)
    setSeriesError(null)
    const wantPredictions = product === 'water_level'
    Promise.all([
      fetchReadings(selectedId, product, hours, ctrl.signal),
      wantPredictions ? fetchPredictions(selectedId, hours, ctrl.signal) : Promise.resolve(null),
    ])
      .then(([obs, pred]) => {
        setObserved(obs)
        setPredicted(pred)
      })
      .catch((err) => {
        if (!ctrl.signal.aborted) setSeriesError(errorMessage(err))
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => ctrl.abort()
  }, [selectedId, product, hours])

  const points = useMemo(
    () => mergeSeries(observed?.readings ?? [], predicted?.readings ?? []),
    [observed, predicted],
  )
  const nowMs = useMemo(() => Date.now(), [observed]) // eslint-disable-line react-hooks/exhaustive-deps
  const selectedStation = stations.find((s) => s.id === selectedId)

  return (
    <div className="app">
      <header className="app-header">
        <img src="/wave.svg" alt="" width={30} height={30} />
        <div className="app-title">
          <h1>Tideline</h1>
          <p>NOAA water levels vs. predicted tide</p>
        </div>
        <SourceBadge series={observed} />
      </header>

      <main className="layout">
        <section className="card map-card" aria-label="Station map">
          {stations.length > 0 ? (
            <StationMap stations={stations} selectedId={selectedId} onSelect={setSelectedId} />
          ) : (
            <p className="placeholder">{stationsError ?? 'Loading stations…'}</p>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>
                {selectedStation ? `${selectedStation.name}, ${selectedStation.state}` : '—'}
              </h2>
              {selectedStation && <span className="panel-sub">Station {selectedStation.id}</span>}
            </div>
            <Controls product={product} onProduct={setProduct} hours={hours} onHours={setHours} />
          </div>

          {seriesError ? (
            <div className="card error-card" role="alert">
              <strong>Couldn’t load readings.</strong> {seriesError}
            </div>
          ) : (
            <>
              <StatTiles
                points={points}
                predicted={predicted?.readings ?? []}
                product={product}
                nowMs={nowMs}
              />
              <div className={`card chart-card${loading ? ' is-loading' : ''}`}>
                {points.length > 0 ? (
                  <ReadingsChart points={points} product={product} nowMs={nowMs} />
                ) : (
                  <p className="placeholder">{loading ? 'Loading readings…' : 'No data.'}</p>
                )}
              </div>
            </>
          )}
        </section>
      </main>

      <footer className="app-footer">
        Data: <a href="https://tidesandcurrents.noaa.gov/">NOAA CO-OPS</a> · Map ©{' '}
        <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · Built
        with FastAPI, React & SQLite
      </footer>
    </div>
  )
}
