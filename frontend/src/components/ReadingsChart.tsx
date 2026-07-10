import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  fmtDayTime,
  fmtLevel,
  fmtTemp,
  fmtTime,
  hourTicks,
  levelValue,
  tempValue,
  type TidePoint,
  type Units,
} from '../lib/tides'
import { useChartTheme } from '../theme'
import type { Product } from '../types'
import SurgeChart from './SurgeChart'

const SYNC_ID = 'tideline' // synchronizes the crosshair across main + surge charts

interface Props {
  points: TidePoint[]
  product: Product
  nowMs: number
  units: Units
  /** NWS minor flood threshold (meters MLLW); drawn when within reach of the data */
  floodMinor?: number | null
}

interface TooltipEntry {
  color?: string
  name?: string
  value?: number
}

function ChartTooltip({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean
  payload?: TooltipEntry[]
  label?: number
  format: (value: number) => string
}) {
  if (!active || !payload?.length || label === undefined) return null
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-time">{fmtDayTime(label)}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="chart-tooltip-row">
          <span className="legend-swatch" style={{ background: entry.color }} />
          <span className="chart-tooltip-name">{entry.name}</span>
          <span className="chart-tooltip-value">
            {entry.value !== undefined ? format(entry.value) : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function ReadingsChart({ points, product, nowMs, units, floodMinor }: Props) {
  const theme = useChartTheme()
  const hasPredicted = points.some((p) => p.predicted !== undefined)
  const isLevel = product === 'water_level'
  const dataMax = Math.max(
    ...points.flatMap((p) => [p.observed, p.predicted].filter((v): v is number => v !== undefined)),
  )
  // only draw the flood line when the water is anywhere near it — a threshold
  // 2 m above the whole window would just squash the tide curve
  const showFloodLine = isLevel && floodMinor != null && floodMinor <= dataMax + 0.75
  const fmtValue = (v: number) => (isLevel ? fmtLevel(v, units) : fmtTemp(v, units))
  const axisValue = (v: number) => (isLevel ? levelValue(v, units) : tempValue(v, units))
  const spansDays = points.length > 1 && points[points.length - 1].t - points[0].t > 24 * 3600_000
  const tickFmt = spansDays ? fmtDayTime : fmtTime
  const ticks =
    points.length > 1 ? hourTicks(points[0].t, points[points.length - 1].t) : undefined
  const domain: [number, number] =
    points.length > 1 ? [points[0].t, points[points.length - 1].t] : [0, 1]

  return (
    <div className="chart">
      <div className="chart-head">
        <h3>{product === 'water_level' ? 'Water level (MLLW)' : 'Water temperature'}</h3>
        {hasPredicted && (
          <div className="chart-legend">
            <span className="legend-item">
              <span className="legend-swatch" style={{ background: theme.observed }} /> Observed
            </span>
            <span className="legend-item">
              <span
                className="legend-swatch legend-swatch--dashed"
                style={{ color: theme.predicted }}
              />{' '}
              Predicted
            </span>
          </div>
        )}
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: 0 }} syncId={SYNC_ID}>
          <CartesianGrid stroke={theme.grid} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={domain}
            tickFormatter={tickFmt}
            tick={{ fill: theme.muted, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: theme.baseline }}
            ticks={ticks}
          />
          <YAxis
            domain={['auto', 'auto']}
            tickFormatter={(v: number) => axisValue(v).toFixed(1)}
            tick={{ fill: theme.muted, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={40}
            unit=""
          />
          <Tooltip
            content={<ChartTooltip format={fmtValue} />}
            cursor={{ stroke: theme.baseline, strokeDasharray: '4 4' }}
            isAnimationActive={false}
          />
          {hasPredicted && (
            <ReferenceLine
              x={nowMs}
              stroke={theme.muted}
              strokeDasharray="3 3"
              label={{ value: 'now', fill: theme.muted, fontSize: 11, position: 'insideTopRight' }}
            />
          )}
          {showFloodLine && (
            <ReferenceLine
              y={floodMinor}
              ifOverflow="extendDomain"
              stroke={theme.surgeAbove}
              strokeDasharray="2 4"
              label={{
                value: `NWS minor flood · ${fmtLevel(floodMinor, units)}`,
                fill: theme.muted,
                fontSize: 11,
                position: 'insideBottomLeft',
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="observed"
            name="Observed"
            stroke={theme.observed}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: theme.surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
          {hasPredicted && (
            <Line
              type="monotone"
              dataKey="predicted"
              name="Predicted"
              stroke={theme.predicted}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              activeDot={{ r: 4, stroke: theme.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
      {hasPredicted && (
        <SurgeChart points={points} domain={domain} nowMs={nowMs} syncId={SYNC_ID} units={units} />
      )}
    </div>
  )
}
