import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, Swords, Sparkles, Trophy, Store, BarChart3 } from 'lucide-react'
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

  const quickActions = [
    { icon: Swords, label: '比赛', path: '/match', color: 'from-red-500/20 to-red-900/10', iconColor: 'text-red-400' },
    { icon: Sparkles, label: '抽卡', path: '/lottery', color: 'from-purple-500/20 to-purple-900/10', iconColor: 'text-purple-400' },
    { icon: Trophy, label: '挑战', path: '/challenge', color: 'from-yellow-500/20 to-yellow-900/10', iconColor: 'text-yellow-400' },
    { icon: Store, label: '转会', path: '/transfer', color: 'from-green-500/20 to-green-900/10', iconColor: 'text-green-400' },
    { icon: BarChart3, label: '联赛', path: '/league', color: 'from-blue-500/20 to-blue-900/10', iconColor: 'text-blue-400' },
    { icon: Shield, label: '查询', path: '/search', color: 'from-cyan-500/20 to-cyan-900/10', iconColor: 'text-cyan-400' },
  ]

  return (
    <div className="p-4">
      {/* User header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-gold/30 to-gold/10 border-2 border-gold/50 flex items-center justify-center">
          <span className="text-gold font-bold text-lg">{user.name[0]}</span>
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-bold text-slate-100">{user.name}</h1>
          <p className="text-xs text-slate-500">ID: {user.id}</p>
        </div>
        <div className="text-right bg-dark-card/60 border border-gold/20 rounded-lg px-3 py-1.5">
          <p className="text-gold font-bold text-sm">{user.money.toLocaleString()}</p>
          <p className="text-[9px] text-slate-500">球币</p>
        </div>
      </div>

      {/* Squad preview banner */}
      {squad && (
        <div
          className="relative mb-5 rounded-xl overflow-hidden border border-dark-border cursor-pointer group"
          onClick={() => navigate('/squad')}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-pitch/40 via-dark-card/80 to-pitch/30" />
          <div className="relative p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Shield size={16} className="text-gold" />
                <span className="text-sm font-bold text-slate-200">我的球队</span>
              </div>
              <span className="text-xs text-gold border border-gold/30 rounded px-2 py-0.5">{squad.formation}</span>
            </div>
            <div className="text-center mb-2">
              <span className="text-3xl font-black text-white">{squad.total_ability}</span>
              <span className="text-xs text-slate-400 ml-1">战力</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="text-center bg-black/20 rounded-lg py-1.5">
                <div className="text-[10px] text-slate-500">前场</div>
                <div className="text-red-400 font-bold text-sm">{squad.forward_ability}</div>
              </div>
              <div className="text-center bg-black/20 rounded-lg py-1.5">
                <div className="text-[10px] text-slate-500">中场</div>
                <div className="text-green-400 font-bold text-sm">{squad.midfield_ability}</div>
              </div>
              <div className="text-center bg-black/20 rounded-lg py-1.5">
                <div className="text-[10px] text-slate-500">后场</div>
                <div className="text-blue-400 font-bold text-sm">{squad.guard_ability}</div>
              </div>
            </div>
          </div>
          <div className="absolute top-2 right-2 text-slate-600 group-hover:text-gold transition-colors">
            <span className="text-lg">›</span>
          </div>
        </div>
      )}

      {/* Quick actions grid */}
      <div className="grid grid-cols-3 gap-2.5">
        {quickActions.map(action => {
          const Icon = action.icon
          return (
            <div
              key={action.path}
              onClick={() => navigate(action.path)}
              className={`relative rounded-xl border border-dark-border overflow-hidden cursor-pointer 
                hover:border-gold/30 transition-all hover:scale-[1.02] active:scale-95`}
            >
              <div className={`absolute inset-0 bg-gradient-to-b ${action.color}`} />
              <div className="relative flex flex-col items-center justify-center py-5 gap-2">
                <Icon size={24} className={action.iconColor} />
                <span className="text-xs font-medium text-slate-300">{action.label}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
