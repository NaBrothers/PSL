import { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ColorText } from '@/components/ColorText'

interface PlayerStat {
  name: string
  colored_name?: string
  position: string
  goals: number
  assists: number
  shots: number
  shots_on_target: number
  xg: number
  npxg: number
  post_shot_xg: number
  big_chances: number
  big_chances_missed: number
  passes: number
  completed_passes: number
  key_passes: number
  xa: number
  progressive_passes: number
  passes_into_final_third: number
  passes_into_box: number
  long_passes: number
  completed_long_passes: number
  crosses: number
  successful_crosses: number
  carries: number
  progressive_carries: number
  carries_into_final_third: number
  carries_into_box: number
  take_ons: number
  successful_take_ons: number
  tackles_attempted: number
  tackles_won: number
  interceptions: number
  blocks: number
  clearances: number
  pressures: number
  successful_pressures: number
  turnovers: number
  dispossessed: number
  offsides: number
  saves: number
  goals_conceded: number
  psxg_faced: number
  goals_prevented: number
  rating?: number
  shot_log: { x: number; y: number; xg: number; in_box: boolean; outcome: string; target_x?: number; target_y?: number }[]
  pass_network: Record<string, number>
  position_samples: [number, number][]
}

interface Props {
  player: PlayerStat
  teamPlayers: PlayerStat[]
  teamSide: 'home' | 'away'
}

const FIELD_W = 300
const FIELD_H = 420
const PITCH_W = 68
const PITCH_H = 105

function pitchToCanvas(x: number, y: number): [number, number] {
  return [(x / PITCH_W) * FIELD_W, (y / PITCH_H) * FIELD_H]
}

function StatRow({ label, value, highlight }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-slate-400 text-xs">{label}</span>
      <span className={`text-xs font-medium ${highlight ? 'text-accent' : 'text-slate-200'}`}>{value}</span>
    </div>
  )
}

function ShotMap({ shots }: { shots: PlayerStat['shot_log'] }) {
  if (shots.length === 0) return <p className="text-slate-500 text-xs text-center py-4">无射门记录</p>

  return (
    <div className="flex justify-center">
      <svg viewBox={`0 0 ${FIELD_W} ${FIELD_H / 2 + 30}`} className="w-full max-w-[320px]" style={{ aspectRatio: `${FIELD_W}/${FIELD_H / 2 + 30}` }}>
        <defs>
          <marker id="arrow-goal" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto">
            <path d="M0,0 L4,2 L0,4 Z" fill="#4ade80" />
          </marker>
          <marker id="arrow-save" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto">
            <path d="M0,0 L4,2 L0,4 Z" fill="#facc15" />
          </marker>
          <marker id="arrow-miss" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto">
            <path d="M0,0 L4,2 L0,4 Z" fill="#ef4444" />
          </marker>
        </defs>
        {/* Half pitch */}
        <rect x="0" y="0" width={FIELD_W} height={FIELD_H / 2 + 30} fill="#1a3a1a" rx="4" />
        {/* Goal */}
        <rect x={FIELD_W / 2 - 30} y="0" width="60" height="4" fill="#fff" opacity="0.3" />
        {/* Penalty box */}
        <rect x={FIELD_W / 2 - 72} y="0" width="144" height={(16.5 / PITCH_H) * FIELD_H} fill="none" stroke="#fff" strokeOpacity="0.2" />
        {/* 6-yard box */}
        <rect x={FIELD_W / 2 - 36} y="0" width="72" height={(5.5 / PITCH_H) * FIELD_H} fill="none" stroke="#fff" strokeOpacity="0.15" />
        {/* Penalty spot */}
        <circle cx={FIELD_W / 2} cy={(12 / PITCH_H) * FIELD_H} r="2" fill="#fff" opacity="0.3" />
        {/* Shot arrows + dots */}
        {shots.map((s, i) => {
          const [cx, cy] = pitchToCanvas(s.x, s.y)
          const targetX = s.target_x != null ? (s.target_x / PITCH_W) * FIELD_W : FIELD_W / 2
          const targetY = 2
          const color = s.outcome === 'goal' ? '#4ade80' : s.outcome === 'save' ? '#facc15' : '#ef4444'
          const isGoal = s.outcome === 'goal'
          const markerId = s.outcome === 'goal' ? 'arrow-goal' : s.outcome === 'save' ? 'arrow-save' : 'arrow-miss'
          const size = Math.max(4, Math.min(12, s.xg * 40))
          return (
            <g key={i}>
              <line
                x1={cx} y1={cy} x2={targetX} y2={targetY}
                stroke={color}
                strokeWidth={isGoal ? 2 : 1.5}
                strokeDasharray={isGoal ? undefined : "4 3"}
                opacity="0.7"
                markerEnd={`url(#${markerId})`}
              />
              <circle cx={cx} cy={cy} r={size} fill={color} opacity="0.8" stroke="#fff" strokeWidth="0.5" />
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function Heatmap({ samples }: { samples: [number, number][] }) {
  if (samples.length === 0) return <p className="text-slate-500 text-xs text-center py-4">无活动数据</p>

  const GRID_X = 8
  const GRID_Y = 12
  const cellW = FIELD_W / GRID_X
  const cellH = FIELD_H / GRID_Y
  const grid: number[][] = Array.from({ length: GRID_Y }, () => Array(GRID_X).fill(0))

  for (const [x, y] of samples) {
    const gx = Math.min(GRID_X - 1, Math.max(0, Math.floor((x / PITCH_W) * GRID_X)))
    const gy = Math.min(GRID_Y - 1, Math.max(0, Math.floor((y / PITCH_H) * GRID_Y)))
    grid[gy][gx]++
  }

  const maxVal = Math.max(...grid.flat(), 1)

  return (
    <div className="flex justify-center">
      <svg viewBox={`0 0 ${FIELD_W} ${FIELD_H}`} className="w-full max-w-[280px] rounded-lg" style={{ aspectRatio: `${FIELD_W}/${FIELD_H}` }}>
        <rect x="0" y="0" width={FIELD_W} height={FIELD_H} fill="#1a3a1a" rx="4" />
        {/* Center line */}
        <line x1="0" y1={FIELD_H / 2} x2={FIELD_W} y2={FIELD_H / 2} stroke="#fff" strokeOpacity="0.2" />
        {/* Center circle */}
        <circle cx={FIELD_W / 2} cy={FIELD_H / 2} r="30" fill="none" stroke="#fff" strokeOpacity="0.15" />
        {/* Top penalty box (attacking end) */}
        <rect x={FIELD_W / 2 - 72} y="0" width="144" height={(16.5 / PITCH_H) * FIELD_H} fill="none" stroke="#fff" strokeOpacity="0.2" />
        {/* Bottom penalty box (defending end) */}
        <rect x={FIELD_W / 2 - 72} y={FIELD_H - (16.5 / PITCH_H) * FIELD_H} width="144" height={(16.5 / PITCH_H) * FIELD_H} fill="none" stroke="#fff" strokeOpacity="0.2" />
        {/* Heat cells */}
        {grid.map((row, gy) =>
          row.map((val, gx) => {
            if (val === 0) return null
            const intensity = val / maxVal
            return (
              <rect
                key={`${gx}-${gy}`}
                x={gx * cellW}
                y={gy * cellH}
                width={cellW}
                height={cellH}
                fill={`rgba(239, 68, 68, ${intensity * 0.7})`}
                rx="2"
              />
            )
          })
        )}
      </svg>
    </div>
  )
}

export default function PlayerMatchDetail({ player, teamPlayers: _teamPlayers, teamSide: _teamSide }: Props) {
  const [tab, setTab] = useState('stats')
  const passRate = player.passes > 0 ? Math.round((player.completed_passes / player.passes) * 100) : 0
  const isGK = player.position === 'GK'

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="text-center">
        <div className="text-lg font-bold"><ColorText text={player.colored_name || player.name} /></div>
        <div className="text-xs text-slate-500">{player.position}</div>
        {player.rating && (
          <div className={`text-2xl font-bold mt-1 ${player.rating >= 8 ? 'text-green-400' : player.rating >= 7 ? 'text-lime-400' : player.rating >= 6.5 ? 'text-yellow-400' : 'text-orange-400'}`}>
            {player.rating}
          </div>
        )}
      </div>

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="w-full">
          <TabsTrigger value="stats" className="flex-1 text-xs">数据</TabsTrigger>
          <TabsTrigger value="shots" className="flex-1 text-xs">射门</TabsTrigger>
          <TabsTrigger value="heatmap" className="flex-1 text-xs">热区</TabsTrigger>
        </TabsList>

        <TabsContent value="stats" className="space-y-3 mt-2">
          {/* Attack */}
          <div>
            <div className="text-[10px] text-accent font-medium mb-1 uppercase tracking-wide">进攻</div>
            <div className="bg-slate-900/50 rounded-lg p-2 space-y-0.5">
              <StatRow label="进球" value={player.goals} highlight={player.goals > 0} />
              <StatRow label="助攻" value={player.assists} highlight={player.assists > 0} />
              <StatRow label="射门 / 射正" value={`${player.shots} / ${player.shots_on_target}`} />
              <StatRow label="xG" value={player.xg.toFixed(2)} />
              <StatRow label="绝对机会" value={player.big_chances} />
              <StatRow label="关键传球" value={player.key_passes} />
              <StatRow label="xA" value={player.xa.toFixed(2)} />
            </div>
          </div>

          {/* Passing */}
          <div>
            <div className="text-[10px] text-green-400 font-medium mb-1 uppercase tracking-wide">传球</div>
            <div className="bg-slate-900/50 rounded-lg p-2 space-y-0.5">
              <StatRow label="传球成功率" value={`${player.completed_passes}/${player.passes} (${passRate}%)`} />
              <StatRow label="推进传球" value={player.progressive_passes} />
              <StatRow label="进入禁区" value={player.passes_into_box} />
              <StatRow label="长传成功" value={`${player.completed_long_passes}/${player.long_passes}`} />
              <StatRow label="传中成功" value={`${player.successful_crosses}/${player.crosses}`} />
            </div>
          </div>

          {/* Carry & Dribble */}
          <div>
            <div className="text-[10px] text-purple-400 font-medium mb-1 uppercase tracking-wide">带球</div>
            <div className="bg-slate-900/50 rounded-lg p-2 space-y-0.5">
              <StatRow label="带球推进" value={player.progressive_carries} />
              <StatRow label="带球进禁区" value={player.carries_into_box} />
              <StatRow label="过人成功" value={`${player.successful_take_ons}/${player.take_ons}`} />
            </div>
          </div>

          {/* Defence */}
          <div>
            <div className="text-[10px] text-blue-400 font-medium mb-1 uppercase tracking-wide">防守</div>
            <div className="bg-slate-900/50 rounded-lg p-2 space-y-0.5">
              <StatRow label="抢断" value={`${player.tackles_won}/${player.tackles_attempted}`} />
              <StatRow label="拦截" value={player.interceptions} />
              <StatRow label="封堵" value={player.blocks} />
              <StatRow label="解围" value={player.clearances} />
              <StatRow label="逼抢成功" value={`${player.successful_pressures}/${player.pressures}`} />
            </div>
          </div>

          {/* GK */}
          {isGK && (
            <div>
              <div className="text-[10px] text-yellow-400 font-medium mb-1 uppercase tracking-wide">门将</div>
              <div className="bg-slate-900/50 rounded-lg p-2 space-y-0.5">
                <StatRow label="扑救" value={player.saves} />
                <StatRow label="失球" value={player.goals_conceded} />
                <StatRow label="PSxG" value={player.psxg_faced.toFixed(2)} />
                <StatRow label="防止失球" value={player.goals_prevented.toFixed(2)} highlight={player.goals_prevented > 0} />
              </div>
            </div>
          )}

          {/* Other */}
          <div>
            <div className="text-[10px] text-slate-500 font-medium mb-1 uppercase tracking-wide">其他</div>
            <div className="bg-slate-900/50 rounded-lg p-2 space-y-0.5">
              <StatRow label="丢失球权" value={player.turnovers} />
              <StatRow label="被断" value={player.dispossessed} />
              <StatRow label="越位" value={player.offsides} />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="shots" className="mt-2">
          <ShotMap shots={player.shot_log} />
          {player.shot_log.length > 0 && (
            <div className="flex justify-center gap-4 mt-2 text-[10px] text-slate-400">
              <span><span className="inline-block w-2 h-2 rounded-full bg-green-400 mr-1" />进球</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-yellow-400 mr-1" />被扑</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-red-400 mr-1" />偏出</span>
              <span className="text-slate-500">圆圈大小 = xG</span>
            </div>
          )}
        </TabsContent>

        <TabsContent value="heatmap" className="mt-2">
          <Heatmap samples={player.position_samples} />
          <p className="text-center text-[10px] text-slate-500 mt-2">基于 {player.position_samples.length} 次位置采样</p>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export type { PlayerStat }
