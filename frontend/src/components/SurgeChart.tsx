import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtDayTime, fmtSignedLevel, levelValue, type TidePoint, type Units } from '../lib/tides'
import { useChartTheme, type ChartTheme } from '../theme'

interface Props {
  points: TidePoint[]
  domain: [number, number]
  nowMs: number
  syncId: string
  units: Units
}

interface SurgePoint {
  t: number
  surge: number
}

function SurgeTooltip({
  active,
  payload,
  label,
  theme,
  units,
}: {
  active?: boolean
  payload?: { value?: number }[]
  label?: number
  theme: ChartTheme
  units: Units
}) {
  if (!active || !payload?.length || label === undefined) return null
  const value = payload[0].value ?? 0
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-time">{fmtDayTime(label)}</div>
      <div className="chart-tooltip-row">
        <span
          className="legend-swatch"
          style={{ background: value >= 0 ? theme.surgeAbove : theme.surgeBelow }}
        />
        <span className="chart-tooltip-name">Surge</span>
        <span className="chart-tooltip-value">{fmtSignedLevel(value, units)}</span>
      </div>
    </div>
  )
}

/** Small diverging chart of observed − predicted, axis-aligned with the main chart. */
export default function SurgeChart({ points, domain, nowMs, syncId, units }: Props) {
  const theme = useChartTheme()
  const surgePoints: SurgePoint[] = points
    .filter((p) => p.observed !== undefined && p.predicted !== undefined)
    .map((p) => ({ t: p.t, surge: (p.observed as number) - (p.predicted as number) }))
  if (surgePoints.length < 2) return null

  // symmetric domain keeps zero centered; a floor stops ±2 cm noise looking dramatic
  const maxAbs = Math.max(0.1, ...surgePoints.map((p) => Math.abs(p.surge)))

  return (
    <div className="chart surge-chart">
      <div className="chart-head">
        <h3>Surge residual (observed − predicted)</h3>
        <div className="chart-legend">
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: theme.surgeAbove }} /> above
          </span>
          <span className="legend-item">
            <span className="legend-swatch" style={{ background: theme.surgeBelow }} /> below
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={110}>
        <AreaChart
          data={surgePoints}
          margin={{ top: 4, right: 16, bottom: 4, left: 0 }}
          syncId={syncId}
        >
          <defs>
            {/* domain is symmetric, so the sign flip is exactly halfway */}
            <linearGradient id="surge-stroke" x1="0" y1="0" x2="0" y2="1">
              <stop offset="50%" stopColor={theme.surgeAbove} />
              <stop offset="50%" stopColor={theme.surgeBelow} />
            </linearGradient>
            <linearGradient id="surge-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="50%" stopColor={theme.surgeAbove} stopOpacity={0.16} />
              <stop offset="50%" stopColor={theme.surgeBelow} stopOpacity={0.16} />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" type="number" domain={domain} hide />
          <YAxis
            domain={[-maxAbs * 1.25, maxAbs * 1.25]}
            ticks={[-maxAbs, 0, maxAbs]}
            tickFormatter={(v: number) => levelValue(v, units).toFixed(2)}
            tick={{ fill: theme.muted, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <Tooltip
            content={<SurgeTooltip theme={theme} units={units} />}
            cursor={{ stroke: theme.baseline, strokeDasharray: '4 4' }}
            isAnimationActive={false}
          />
          <ReferenceLine y={0} stroke={theme.baseline} />
          <ReferenceLine x={nowMs} stroke={theme.muted} strokeDasharray="3 3" />
          <Area
            dataKey="surge"
            name="Surge"
            baseValue={0}
            type="monotone"
            stroke="url(#surge-stroke)"
            strokeWidth={1.5}
            fill="url(#surge-fill)"
            dot={false}
            activeDot={{ r: 3, stroke: theme.surface, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
