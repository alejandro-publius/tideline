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
import { fmtDayTime, fmtTime, hourTicks, type TidePoint } from '../lib/tides'
import { useChartTheme } from '../theme'
import type { Product } from '../types'

interface Props {
  points: TidePoint[]
  product: Product
  nowMs: number
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
  unit,
}: {
  active?: boolean
  payload?: TooltipEntry[]
  label?: number
  unit: string
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
            {entry.value?.toFixed(2)} {unit}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function ReadingsChart({ points, product, nowMs }: Props) {
  const theme = useChartTheme()
  const hasPredicted = points.some((p) => p.predicted !== undefined)
  const unit = product === 'water_level' ? 'm' : '°C'
  const spansDays = points.length > 1 && points[points.length - 1].t - points[0].t > 24 * 3600_000
  const tickFmt = spansDays ? fmtDayTime : fmtTime
  const ticks =
    points.length > 1 ? hourTicks(points[0].t, points[points.length - 1].t) : undefined

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
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={theme.grid} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={tickFmt}
            tick={{ fill: theme.muted, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: theme.baseline }}
            ticks={ticks}
          />
          <YAxis
            domain={['auto', 'auto']}
            tickFormatter={(v: number) => v.toFixed(1)}
            tick={{ fill: theme.muted, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={40}
            unit=""
          />
          <Tooltip
            content={<ChartTooltip unit={unit} />}
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
    </div>
  )
}
