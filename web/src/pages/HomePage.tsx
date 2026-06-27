import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, Backpack, Store, Search, Trophy as TrophyIcon, CalendarDays } from 'lucide-react'
import api from '../api/client'
import { cardBorderColor } from '@/lib/card-display'

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
  cards: ({ player_id: number; name: string; overall: number; star: number } | null)[]
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

  const topPlayers = (squad?.cards?.filter(c => c !== null) || []).sort((a, b) => (b!.overall + b!.star) - (a!.overall + a!.star)).slice(0, 5)

  return (
    <div className="p-3 flex flex-col gap-3 h-full">
      {/* User header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-gold/30 to-gold/10 border-2 border-gold/50 flex items-center justify-center shadow-[0_0_10px_rgba(212,168,67,0.15)]">
          <span className="text-gold font-bold text-base">{user.name[0]}</span>
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-bold text-slate-100 truncate">{user.name}</h1>
          <p className="text-[10px] text-slate-500">ID: {user.id}</p>
        </div>
        <div className="bg-dark-card/80 border border-gold/20 rounded-lg px-3 py-1">
          <p className="text-gold font-bold text-sm">${user.money.toLocaleString()}</p>
        </div>
      </div>

      {/* Main Banner - Squad */}
      <div
        className="relative rounded-xl overflow-hidden cursor-pointer group flex-shrink-0"
        onClick={() => navigate('/squad')}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-[#0a1628] via-[#0d1f3c] to-[#0a1628]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,rgba(45,90,39,0.3),transparent_70%)]" />
        <div className="relative px-4 py-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <span className="text-white font-bold text-base">我的球队</span>
              <span className="text-gold text-xs ml-2 border border-gold/30 rounded px-1.5 py-0.5">{squad?.formation || '442'}</span>
            </div>
            <div className="text-right">
              <span className="text-2xl font-black text-white">{squad?.total_ability || 0}</span>
              <span className="text-[10px] text-slate-400 ml-1">战力</span>
            </div>
          </div>
          {/* Player avatars */}
          <div className="flex justify-center -space-x-2">
            {topPlayers.map((p, i) => (
              <div
                key={i}
                className={`w-11 h-11 rounded-full overflow-hidden border-2 bg-slate-800 shadow-lg ${cardBorderColor(p!.overall, p!.star)}`}
              >
                <img
                  src={`/game-assets/avatars/${p!.player_id}.png`}
                  alt=""
                  className="w-full h-full object-cover"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
              </div>
            ))}
          </div>
          <div className="flex justify-center gap-4 mt-2 text-[10px]">
            <span className="text-red-400">前场 {squad?.forward_ability || 0}</span>
            <span className="text-green-400">中场 {squad?.midfield_ability || 0}</span>
            <span className="text-blue-400">后场 {squad?.guard_ability || 0}</span>
          </div>
        </div>
      </div>

      {/* Quick icon bar */}
      <div className="grid grid-cols-6 gap-1 flex-shrink-0">
        {quickIcons.map(item => {
          const Icon = item.icon
          return (
            <div
              key={item.path}
              onClick={() => navigate(item.path)}
              className="flex flex-col items-center gap-1 py-1.5 cursor-pointer hover:opacity-80 transition-opacity"
            >
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${item.color}`}>
                <Icon size={15} />
              </div>
              <span className="text-[9px] text-slate-400">{item.label}</span>
            </div>
          )
        })}
      </div>

      {/* Bottom cards - waterfall layout */}
      <div className="flex-1 grid grid-cols-2 gap-2.5 auto-rows-min min-h-0">
        {/* Left column - tall first */}
        <div
          className="relative rounded-xl overflow-hidden cursor-pointer row-span-2 min-h-[140px]"
          onClick={() => navigate('/match')}
        >
          <img src="/assets/banner-stadium.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-black/10" />
          <div className="relative h-full flex flex-col justify-end p-3">
            <span className="text-white font-bold">比赛</span>
            <span className="text-gold text-[10px] font-medium">PK · 对战</span>
          </div>
        </div>
        {/* Right column - two short */}
        <div
          className="relative rounded-xl overflow-hidden cursor-pointer min-h-[66px]"
          onClick={() => navigate('/challenge')}
        >
          <img src="/assets/entry-trophy.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2.5">
            <span className="text-white font-bold text-sm">每日挑战</span>
          </div>
        </div>
        <div
          className="relative rounded-xl overflow-hidden cursor-pointer min-h-[66px]"
          onClick={() => navigate('/lottery')}
        >
          <img src="/assets/entry-cards.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2.5">
            <span className="text-white font-bold text-sm">抽卡</span>
          </div>
        </div>
        {/* Second row */}
        <div
          className="relative rounded-xl overflow-hidden cursor-pointer min-h-[66px]"
          onClick={() => navigate('/transfer')}
        >
          <img src="/assets/entry-market.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2.5">
            <span className="text-white font-bold text-sm">转会市场</span>
          </div>
        </div>
        <div
          className="relative rounded-xl overflow-hidden cursor-pointer min-h-[66px]"
          onClick={() => navigate('/league')}
        >
          <img src="/assets/entry-league.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2.5">
            <span className="text-white font-bold text-sm">联赛</span>
          </div>
        </div>
        <div
          className="relative rounded-xl overflow-hidden cursor-pointer min-h-[66px]"
          onClick={() => navigate('/search')}
        >
          <img src="/assets/entry-pitch.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
          <div className="relative h-full flex flex-col justify-end p-2.5">
            <span className="text-white font-bold text-sm">全局查询</span>
          </div>
        </div>
      </div>
    </div>
  )
}
