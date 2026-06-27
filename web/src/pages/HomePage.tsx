import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Backpack, Store, Search, Trophy as TrophyIcon, CalendarDays } from 'lucide-react'
import api from '../api/client'

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
  cards: ({ player_id: number; name: string } | null)[]
}

export default function HomePage() {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [squad, setSquad] = useState<SquadPreview | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/me').then(res => setUser(res.data))
    api.get('/squad').then(res => setSquad(res.data))
  }, [])

  if (!user) {
    return <div className="flex items-center justify-center h-full text-slate-500">加载中...</div>
  }

  const quickIcons = [
    { icon: Sparkles, label: '抽卡', path: '/lottery', color: 'bg-purple-500/20 text-purple-400' },
    { icon: Backpack, label: '背包', path: '/bag', color: 'bg-blue-500/20 text-blue-400' },
    { icon: Store, label: '转会', path: '/transfer', color: 'bg-green-500/20 text-green-400' },
    { icon: Search, label: '查询', path: '/search', color: 'bg-cyan-500/20 text-cyan-400' },
    { icon: CalendarDays, label: '联赛', path: '/league', color: 'bg-orange-500/20 text-orange-400' },
    { icon: TrophyIcon, label: '挑战', path: '/challenge', color: 'bg-yellow-500/20 text-yellow-400' },
  ]

  const topPlayers = squad?.cards?.filter(c => c !== null).slice(0, 3) || []

  return (
    <div className="p-3 space-y-3">
      {/* User header */}
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-full bg-gradient-to-br from-gold/30 to-gold/10 border-2 border-gold/50 flex items-center justify-center shadow-[0_0_10px_rgba(212,168,67,0.15)]">
          <span className="text-gold font-bold text-lg">{user.name[0]}</span>
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-bold text-slate-100 truncate">{user.name}</h1>
          <p className="text-[10px] text-slate-500">ID: {user.id} · 战力 {squad?.total_ability || 0}</p>
        </div>
        <div className="bg-dark-card/80 border border-gold/20 rounded-lg px-3 py-1.5">
          <p className="text-gold font-bold text-sm">${user.money.toLocaleString()}</p>
        </div>
      </div>

      {/* Quick icon bar */}
      <div className="grid grid-cols-6 gap-1">
        {quickIcons.map(item => {
          const Icon = item.icon
          return (
            <div
              key={item.path}
              onClick={() => navigate(item.path)}
              className="flex flex-col items-center gap-1 py-2 cursor-pointer hover:opacity-80 transition-opacity"
            >
              <div className={`w-9 h-9 rounded-full flex items-center justify-center ${item.color}`}>
                <Icon size={16} />
              </div>
              <span className="text-[9px] text-slate-400">{item.label}</span>
            </div>
          )
        })}
      </div>

      {/* Main Banner - PK */}
      <div
        className="relative rounded-xl overflow-hidden cursor-pointer group h-36"
        onClick={() => navigate('/match')}
      >
        <img src="/assets/banner-stadium.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/70 via-black/40 to-transparent" />
        <div className="relative h-full flex items-center px-4">
          {/* Left: player avatars */}
          <div className="flex -space-x-3">
            {topPlayers.map((p, i) => (
              <div key={i} className="w-12 h-12 rounded-full border-2 border-white/30 overflow-hidden bg-slate-800 shadow-lg">
                <img
                  src={`/game-assets/avatars/${p!.player_id}.png`}
                  alt=""
                  className="w-full h-full object-cover"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
              </div>
            ))}
          </div>
          {/* Right: CTA */}
          <div className="ml-auto text-right">
            <p className="text-slate-300 text-xs mb-2">选择对手，一决高下</p>
            <div className="inline-block bg-gradient-to-r from-gold to-yellow-500 text-black font-black text-lg px-5 py-1.5 rounded-lg shadow-[0_0_12px_rgba(212,168,67,0.4)] group-hover:scale-105 transition-transform">
              PK
            </div>
          </div>
        </div>
      </div>

      {/* Medium entries - 2 columns */}
      <div className="grid grid-cols-2 gap-2.5">
        <div
          className="relative rounded-xl overflow-hidden h-24 cursor-pointer group"
          onClick={() => navigate('/squad')}
        >
          <img src="/assets/entry-pitch.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-3">
            <span className="text-white font-bold text-sm">球队阵容</span>
            <span className="text-slate-300 text-[10px]">{squad?.formation || '442'} · {squad?.total_ability || 0}</span>
          </div>
        </div>
        <div
          className="relative rounded-xl overflow-hidden h-24 cursor-pointer group"
          onClick={() => navigate('/challenge')}
        >
          <img src="/assets/entry-trophy.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-3">
            <span className="text-white font-bold text-sm">每日挑战</span>
            <span className="text-slate-300 text-[10px]">挑战NPC赢奖励</span>
          </div>
        </div>
      </div>

      {/* Small entries - 3 columns */}
      <div className="grid grid-cols-3 gap-2">
        <div
          className="relative rounded-xl overflow-hidden h-20 cursor-pointer"
          onClick={() => navigate('/lottery')}
        >
          <img src="/assets/entry-cards.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2">
            <span className="text-white font-bold text-xs">抽卡</span>
          </div>
        </div>
        <div
          className="relative rounded-xl overflow-hidden h-20 cursor-pointer"
          onClick={() => navigate('/transfer')}
        >
          <img src="/assets/entry-market.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2">
            <span className="text-white font-bold text-xs">转会市场</span>
          </div>
        </div>
        <div
          className="relative rounded-xl overflow-hidden h-20 cursor-pointer"
          onClick={() => navigate('/league')}
        >
          <img src="/assets/entry-league.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2">
            <span className="text-white font-bold text-xs">联赛</span>
          </div>
        </div>
      </div>
    </div>
  )
}
