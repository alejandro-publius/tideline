import { useEffect, useMemo, useState } from 'react'
import { fetchOverview, fetchPredictions, fetchReadings, fetchStations } from './api'
import Controls from './components/Controls'
import ReadingsChart from './components/ReadingsChart'
import SourceBadge from './components/SourceBadge'
import StationMap from './components/StationMap'
import StatTiles from './components/StatTiles'
import { mergeSeries } from './lib/tides'
import { DEFAULT_STATION, readUrlState, writeUrlState } from './lib/urlState'
import type { Product, Series, Station, StationOverview } from './types'

const REFRESH_INTERVAL_MS = 5 * 60_000

const errorMessage = (err: unknown) => (err instanceof Error ? err.message : 'Request failed')

const initialState = readUrlState(window.location.search)

export default function App() {
  const [stations, setStations] = useState<Station[]>([])
  const [stationsError, setStationsError] = useState<string | null>(null)
  const [overview, setOverview] = useState<StationOverview[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(initialState.station)
  const [product, setProduct] = useState<Product>(initialState.product)
  const [hours, setHours] = useState(initialState.hours)
  const [units, setUnits] = useState(initialState.units)
  const [refreshTick, setRefreshTick] = useState(0)

  const [observed, setObserved] = useState<Series | null>(null)
  const [predicted, setPredicted] = useState<Series | null>(null)
  const [loading, setLoading] = useState(true)
  const [seriesError, setSeriesError] = useState<string | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchStations(ctrl.signal)
      .then((list) => {
        setStations(list)
        // keep a station from the URL only if it actually exists
        setSelectedId((cur) => (cur && list.some((s) => s.id === cur) ? cur : DEFAULT_STATION))
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
  }, [selectedId, product, hours, refreshTick])

  // shareable URLs: reflect the current view without spamming history
  useEffect(() => {
    if (!selectedId) return
    const qs = writeUrlState({ station: selectedId, product, hours, units })
    window.history.replaceState(null, '', `${window.location.pathname}${qs}`)
  }, [selectedId, product, hours, units])

  // surge overview colors the map; slower than /stations, so it loads separately
  useEffect(() => {
    const ctrl = new AbortController()
    fetchOverview(ctrl.signal)
      .then((data) => setOverview(data.stations))
      .catch(() => {
        // map falls back to uncolored markers; not worth an error state
      })
    return () => ctrl.abort()
  }, [refreshTick])

  // keep a visible dashboard live; hidden tabs don't poll
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') setRefreshTick((t) => t + 1)
    }, REFRESH_INTERVAL_MS)
    return () => clearInterval(id)
  }, [])

  const points = useMemo(
    () => mergeSeries(observed?.readings ?? [], predicted?.readings ?? []),
    [observed, predicted],
  )
  const nowMs = useMemo(() => Date.now(), [observed]) // eslint-disable-line react-hooks/exhaustive-deps
  const selectedStation = stations.find((s) => s.id === selectedId)
  const surgeById = useMemo(
    () => Object.fromEntries(overview.map((row) => [row.station.id, row.surge])),
    [overview],
  )

  const emptyMessage =
    product === 'water_temperature'
      ? 'No water temperature sensor at this station.'
      : 'No data available for this station.'

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
            <StationMap
              stations={stations}
              selectedId={selectedId}
              onSelect={setSelectedId}
              surgeById={surgeById}
              units={units}
            />
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
              {selectedStation && (
                <a
                  className="panel-sub"
                  href={`https://tidesandcurrents.noaa.gov/stationhome.html?id=${selectedStation.id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Station {selectedStation.id} ↗
                </a>
              )}
            </div>
            <div className="controls-row">
              <label className="station-select">
                <span className="visually-hidden">Station</span>
                <select
                  value={selectedId ?? ''}
                  onChange={(event) => setSelectedId(event.target.value)}
                >
                  {stations.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}, {s.state}
                    </option>
                  ))}
                </select>
              </label>
              <Controls
                product={product}
                onProduct={setProduct}
                hours={hours}
                onHours={setHours}
                units={units}
                onUnits={setUnits}
              />
            </div>
          </div>

          {seriesError ? (
            <div className="card error-card" role="alert">
              <span>
                <strong>Couldn’t load readings.</strong> {seriesError}
              </span>
              <button type="button" onClick={() => setRefreshTick((t) => t + 1)}>
                Retry
              </button>
            </div>
          ) : (
            <>
              <StatTiles
                points={points}
                predicted={predicted?.readings ?? []}
                product={product}
                nowMs={nowMs}
                units={units}
              />
              <div className={`card chart-card${loading ? ' is-loading' : ''}`}>
                {points.length > 0 ? (
                  <ReadingsChart points={points} product={product} nowMs={nowMs} units={units} />
                ) : (
                  <p className="placeholder">{loading ? 'Loading readings…' : emptyMessage}</p>
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
