import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Building2, X } from 'lucide-react'
import api from '../api/client'
import InboxBanner from '@/components/InboxBanner'
import { overallColor } from '@/lib/card-display'
import type { ClubAgent, ClubBuilding } from '@/game/club/types'

const ClubTownGame = lazy(() => import('@/game/club/ClubTownGame'))

interface UserInfo {
  id: number
  qq: number
  name: string
  money: number
  formation: string
}

interface SquadPreview {
  formation: string
  total_ability: number
  forward_ability: number
  midfield_ability: number
  guard_ability: number
  cards: ({ id: number; player_id: number; name: string; overall: number; star: number; position?: string } | null)[]
}

const buildings: ClubBuilding[] = [
  {
    id: 'stadium', name: '主球场', level: 4, status: '赛程准备中', production: '主场比赛奖金 +8%', actionLabel: '进入比赛', path: '/match', kind: 'stadium',
    plot: { x: 48, y: 30, width: 430, height: 270 },
    building: { x: 48, y: 30, width: 430, height: 270 },
    entry: { x: 456, y: 352 },
  },
  {
    id: 'training', name: '训练中心', level: 2, status: '3 名球员训练中', production: '训练点 +120 / 天', actionLabel: '进入训练', path: '/squad', kind: 'training',
    plot: { x: 920, y: 18, width: 286, height: 174 },
    building: { x: 1056, y: 86, width: 118, height: 82 },
    entry: { x: 920, y: 208 },
  },
  {
    id: 'clubhouse', name: '俱乐部大厅', level: 3, status: '阵容会议', production: '管理球队和球员卡', actionLabel: '打开背包', path: '/bag', kind: 'clubhouse',
    plot: { x: 582, y: 62, width: 216, height: 138 },
    building: { x: 604, y: 78, width: 172, height: 110 },
    entry: { x: 690, y: 214 },
  },
  {
    id: 'commerce', name: '商业中心', level: 3, status: '赞助收益可结算', production: '球币 +2400 / 天', actionLabel: '前往市场', path: '/transfer', kind: 'commerce',
    plot: { x: 964, y: 284, width: 214, height: 124 },
    building: { x: 998, y: 312, width: 146, height: 88 },
    entry: { x: 964, y: 424 },
  },
  {
    id: 'academy', name: '青训营', level: 1, status: '新秀报告待领取', production: '青训卡包进度 +1 / 天', actionLabel: '查看卡包', path: '/lottery', kind: 'academy',
    plot: { x: 888, y: 492, width: 246, height: 126 },
    building: { x: 906, y: 520, width: 128, height: 84 },
    entry: { x: 888, y: 476 },
  },
  {
    id: 'scout', name: '球探中心', level: 2, status: '球探路线已刷新', production: '球探点 +80 / 天', actionLabel: '查看球探', path: '/search', kind: 'scout',
    plot: { x: 96, y: 492, width: 222, height: 122 },
    building: { x: 142, y: 520, width: 132, height: 82 },
    entry: { x: 258, y: 482 },
  },
  {
    id: 'medical', name: '医疗中心', level: 1, status: '恢复舱空闲', production: '挑战恢复效率 +5%', actionLabel: '每日挑战', path: '/challenge', kind: 'medical',
    plot: { x: 530, y: 492, width: 196, height: 104 },
    building: { x: 568, y: 510, width: 118, height: 78 },
    entry: { x: 690, y: 474 },
  },
]

export default function HomePage() {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [squad, setSquad] = useState<SquadPreview | null>(null)
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/me').then(res => setUser(res.data))
    api.get('/squad').then(res => setSquad(res.data))
  }, [])

  const startingAgents: ClubAgent[] = useMemo(() => (
    (squad?.cards || [])
      .filter((card): card is NonNullable<SquadPreview['cards'][number]> => card !== null)
      .slice(0, 11)
      .map((card, index) => ({
        id: index,
        cardId: card.id,
        playerId: card.player_id,
        name: card.name,
        overall: card.overall,
        star: card.star,
        position: card.position,
      }))
  ), [squad])

  const selectedBuilding = buildings.find(b => b.id === selectedBuildingId) || null
  const topPlayer = startingAgents.slice().sort((a, b) => (b.overall + b.star) - (a.overall + a.star))[0]

  if (!user) {
    return <div className="flex items-center justify-center h-full text-slate-500">加载中...</div>
  }

  return (
    <div className="relative h-full overflow-hidden bg-[#6ebf57]">
      <Suspense fallback={<div className="h-full w-full bg-[#8ed46a]" />}>
        <ClubTownGame
          agents={startingAgents}
          buildings={buildings}
          onBuildingClick={setSelectedBuildingId}
          onAgentClick={(cardId) => navigate(`/cards/${cardId}`)}
        />
      </Suspense>

      <div className="absolute top-2 left-3 right-3 z-30">
        <InboxBanner />
      </div>

      <div className="pointer-events-none absolute left-3 right-3 top-12 z-30 flex items-start justify-between gap-3">
        <div className="rounded-md border-2 border-slate-900/30 bg-white/82 px-3 py-2 shadow-[4px_4px_0_rgba(15,23,42,0.25)]">
          <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Club Base</div>
          <div className="text-base font-black leading-tight text-slate-900">{user.name}</div>
        </div>
        <div className="rounded-md border-2 border-slate-900/30 bg-white/82 px-3 py-2 text-right shadow-[4px_4px_0_rgba(15,23,42,0.25)]">
          <div className="text-[10px] font-bold text-slate-500">{squad?.formation || '442'}</div>
          <div className="text-xl font-black leading-none text-slate-900">{squad?.total_ability || 0}</div>
          <div className="mt-1 text-[10px] text-slate-500">${user.money?.toLocaleString?.() || user.money}</div>
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-3 left-3 z-20">
        <div className="rounded-full border-2 border-slate-900/20 bg-white/80 px-3 py-2 shadow-[3px_3px_0_rgba(15,23,42,0.16)]">
          <div className="flex items-center gap-2 text-[10px] font-black text-slate-900">
            <span>首发 {startingAgents.length}/11</span>
            <span className="text-slate-400">|</span>
            <span>{squad?.forward_ability || 0}/{squad?.midfield_ability || 0}/{squad?.guard_ability || 0}</span>
            {topPlayer && (
              <>
                <span className="text-slate-400">|</span>
                <span className={`max-w-[86px] truncate ${overallColor(topPlayer.overall, topPlayer.star)}`}>{topPlayer.name}</span>
              </>
            )}
          </div>
        </div>
      </div>

      {selectedBuilding && (
        <div className="absolute inset-0 z-40 flex items-end bg-black/12" onClick={() => setSelectedBuildingId(null)}>
          <div
            className="w-full border-t-4 border-slate-900 bg-[#111827]/95 p-4 text-slate-100 shadow-[0_-8px_0_rgba(15,23,42,0.28)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <Building2 size={18} className="text-gold" />
                  <h2 className="text-lg font-black">{selectedBuilding.name}</h2>
                  <span className="rounded bg-gold px-1.5 py-0.5 text-[10px] font-black text-black">Lv.{selectedBuilding.level}</span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{selectedBuilding.status}</p>
              </div>
              <button className="rounded border border-slate-600 p-1 text-slate-400" onClick={() => setSelectedBuildingId(null)}>
                <X size={16} />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-md bg-slate-900 px-3 py-2">
                <div className="text-slate-500">设施效果</div>
                <div className="mt-1 font-bold text-slate-100">{selectedBuilding.production}</div>
              </div>
              <div className="rounded-md bg-slate-900 px-3 py-2">
                <div className="text-slate-500">附近球员</div>
                <div className="mt-1 truncate font-bold text-slate-100">
                  {startingAgents.slice(0, 3).map(agent => agent.name).join(' / ') || '暂无'}
                </div>
              </div>
            </div>
            <button
              className="mt-3 w-full rounded-md bg-gold px-4 py-3 text-sm font-black text-black shadow-[3px_3px_0_rgba(0,0,0,0.35)]"
              onClick={() => navigate(selectedBuilding.path)}
            >
              {selectedBuilding.actionLabel}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
