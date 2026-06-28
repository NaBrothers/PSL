interface RadarProps {
  values: number[]
  labels: string[]
  maxValue?: number
  color?: string
  secondValues?: number[]
  secondColor?: string
  size?: number
}

export default function RadarChart({ values, labels, maxValue = 120, color = '#4fc3f7', secondValues, secondColor = '#4ade80', size = 200 }: RadarProps) {
  const cx = size / 2, cy = size / 2
  const r = size * 0.32
  const n = labels.length

  const angleStep = (Math.PI * 2) / n
  const startAngle = -Math.PI / 2

  function getPoint(i: number, val: number): [number, number] {
    const angle = startAngle + i * angleStep
    const ratio = Math.min(val / maxValue, 1)
    return [cx + r * ratio * Math.cos(angle), cy + r * ratio * Math.sin(angle)]
  }

  function polygon(vals: number[]): string {
    return vals.map((v, i) => getPoint(i, v).join(',')).join(' ')
  }

  // Grid lines
  const gridLevels = [0.25, 0.5, 0.75, 1]
  const gridLines = gridLevels.map(level => {
    const points = Array.from({ length: n }, (_, i) => {
      const angle = startAngle + i * angleStep
      return `${cx + r * level * Math.cos(angle)},${cy + r * level * Math.sin(angle)}`
    }).join(' ')
    return points
  })

  // Axis lines
  const axes = Array.from({ length: n }, (_, i) => {
    const angle = startAngle + i * angleStep
    return { x2: cx + r * Math.cos(angle), y2: cy + r * Math.sin(angle) }
  })

  // Label positions
  const labelPositions = Array.from({ length: n }, (_, i) => {
    const angle = startAngle + i * angleStep
    const labelR = r + 14
    return { x: cx + labelR * Math.cos(angle), y: cy + labelR * Math.sin(angle) }
  })

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full" style={{ maxWidth: size }}>
      {/* Grid */}
      {gridLines.map((points, i) => (
        <polygon key={i} points={points} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="0.5" />
      ))}

      {/* Axes */}
      {axes.map((a, i) => (
        <line key={i} x1={cx} y1={cy} x2={a.x2} y2={a.y2} stroke="rgba(255,255,255,0.15)" strokeWidth="0.5" />
      ))}

      {/* Second player area (behind) */}
      {secondValues && (
        <>
          <polygon points={polygon(secondValues)} fill={secondColor} fillOpacity="0.15" stroke={secondColor} strokeWidth="1.5" />
          {secondValues.map((v, i) => {
            const [px, py] = getPoint(i, v)
            return <circle key={i} cx={px} cy={py} r="3" fill={secondColor} />
          })}
        </>
      )}

      {/* Main player area */}
      <polygon points={polygon(values)} fill={color} fillOpacity="0.2" stroke={color} strokeWidth="1.5" />
      {values.map((v, i) => {
        const [px, py] = getPoint(i, v)
        return <circle key={i} cx={px} cy={py} r="3" fill={color} />
      })}

      {/* Labels */}
      {labelPositions.map((pos, i) => (
        <text key={i} x={pos.x} y={pos.y} textAnchor="middle" dominantBaseline="middle" fill="#94a3b8" fontSize="10" fontWeight="500">
          {labels[i]}
        </text>
      ))}
    </svg>
  )
}

export function computeRadarValues(abilities: Record<string, { value: number }>, isGK = false): number[] {
  const get = (k: string) => abilities[k]?.value || 0
  if (isGK) {
    return [
      get('GK_Saving'),       // 扑救
      get('GK_Positioning'),  // 站位
      get('GK_Reaction'),     // 反应
      get('Long_Passing'),    // 传球
      get('Speed'),           // 速度
      get('IQ'),              // 球商
    ]
  }
  return [
    Math.round((get('Finishing') + get('Long_Shot') + get('Heading')) / 3),  // 射门
    Math.round((get('Short_Passing') + get('Long_Passing')) / 2),  // 传球
    get('IQ'),  // 球商
    Math.round((get('Tackling') + get('Defence')) / 2),  // 防守
    get('Speed'),  // 速度
    get('Dribbling'),  // 盘带
  ]
}

export const RADAR_LABELS = ['射门', '传球', '球商', '防守', '速度', '盘带']
export const RADAR_LABELS_GK = ['扑救', '站位', '反应', '传球', '速度', '球商']
