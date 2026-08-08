import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { Anomaly } from '../types'
import AnomalyFeed from './AnomalyFeed'

const NOW = Date.parse('2026-07-09T12:00:00Z')
const MINUTE = 60_000

const anomaly = (over: Partial<Anomaly> = {}): Anomaly => ({
  station_id: '8518750',
  station_name: 'The Battery',
  ts: '2026-07-09T11:48:00Z',
  value: 1.42,
  kind: 'surge',
  severity: 'above',
  residual: 0.4,
  detected_at: '2026-07-09T11:49:00Z',
  ...over,
})

/** Render with the defaults every test shares, overriding only what it exercises. */
const render = (props: Partial<Parameters<typeof AnomalyFeed>[0]> = {}) =>
  renderToStaticMarkup(
    <AnomalyFeed
      anomalies={[]}
      loading={false}
      error={null}
      onRetry={() => {}}
      nowMs={NOW}
      units="metric"
      {...props}
    />,
  )

describe('surge anomalies', () => {
  it('shows the residual with an explicit sign and direction', () => {
    const html = render({ anomalies: [anomaly()] })

    expect(html).toContain('+0.40 m above prediction')
    expect(html).toContain('The Battery')
    expect(html).toContain('Surge above')
  })

  it('uses a true minus sign for a negative residual', () => {
    const html = render({
      anomalies: [anomaly({ severity: 'below', residual: -0.27 })],
    })

    expect(html).toContain('−0.27 m below prediction')
    expect(html).toContain('Surge below')
  })

  it('converts the residual when the app is in US units', () => {
    const html = render({ anomalies: [anomaly()], units: 'us' })

    expect(html).toContain('+1.31 ft above prediction')
  })
})

describe('flood anomalies', () => {
  it('labels the NWS stage and falls back to the observed level (residual is null)', () => {
    const html = render({
      anomalies: [anomaly({ kind: 'flood', severity: 'major', residual: null })],
    })

    expect(html).toContain('Major flood')
    expect(html).toContain('1.42 m observed')
    expect(html).not.toContain('prediction')
  })

  it('distinguishes the three stages without relying on color', () => {
    const marks = (['minor', 'moderate', 'major'] as const).map((severity) => {
      const html = render({ anomalies: [anomaly({ kind: 'flood', severity, residual: null })] })
      return html.slice(html.indexOf('anomaly-mark'), html.indexOf('anomaly-mark') + 60)
    })

    expect(marks[0]).toContain('●○○')
    expect(marks[1]).toContain('●●○')
    expect(marks[2]).toContain('●●●')
    expect(new Set(marks).size).toBe(3)
  })
})

describe('ordering and timestamps', () => {
  it('lists newest first regardless of the order the API returned', () => {
    const html = render({
      anomalies: [
        anomaly({ station_name: 'Older', ts: '2026-07-09T09:00:00Z' }),
        anomaly({ station_name: 'Newest', ts: '2026-07-09T11:30:00Z' }),
        anomaly({ station_name: 'Middle', ts: '2026-07-09T10:00:00Z' }),
      ],
    })

    expect(html.indexOf('Newest')).toBeLessThan(html.indexOf('Middle'))
    expect(html.indexOf('Middle')).toBeLessThan(html.indexOf('Older'))
  })

  it('renders relative times with the machine-readable timestamp alongside', () => {
    const at = (minsAgo: number) => new Date(NOW - minsAgo * MINUTE).toISOString()
    const html = render({
      anomalies: [
        anomaly({ station_id: 'a', ts: at(12) }),
        anomaly({ station_id: 'b', ts: at(185) }),
      ],
    })

    expect(html).toContain('12m ago')
    expect(html).toContain('3h 5m ago')
    // lowercased because React serializes the attribute as `dateTime`
    expect(html.toLowerCase()).toContain(`datetime="${at(12).toLowerCase()}"`)
  })
})

describe('empty, loading and error states', () => {
  it('says the coast is quiet rather than showing nothing', () => {
    const html = render()

    expect(html).toContain('No anomalies recorded')
    expect(html).toContain('within its normal range')
    expect(html).not.toContain('anomaly-list')
  })

  it('shows a loading placeholder only while the first fetch is in flight', () => {
    expect(render({ loading: true })).toContain('Loading anomalies…')
    // a refresh over existing rows keeps the list visible
    expect(render({ loading: true, anomalies: [anomaly()] })).toContain('anomaly-list')
  })

  it('reports a failed fetch as an alert with a retry action', () => {
    const html = render({ error: 'anomaly store unreachable' })

    expect(html).toContain('role="alert"')
    expect(html).toContain('anomaly store unreachable')
    expect(html).toContain('Retry')
    expect(html).not.toContain('No anomalies recorded')
  })

  it('prefers the error over stale rows so a broken feed is never silent', () => {
    const html = render({ error: 'boom', anomalies: [anomaly()] })

    expect(html).not.toContain('anomaly-list')
  })
})
