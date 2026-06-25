import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
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
    return <div className="bg-dark flex items-center justify-center text-slate-500">加载中...</div>
  }

  return (
    <div className="bg-dark p-4">
      <div className="max-w-md mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-slate-100">{user.name}</h1>
            <p className="text-sm text-slate-500">ID: {user.id}</p>
          </div>
          <div className="text-right">
            <p className="text-yellow-400 font-bold">${user.money.toLocaleString()}</p>
            <p className="text-xs text-slate-500">球币</p>
          </div>
        </div>

        {/* Squad Preview */}
        {squad && (
          <Card className="mb-4 cursor-pointer hover:border-accent/40 transition-colors" onClick={() => navigate('/squad')}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-slate-400 flex justify-between">
                <span>我的球队</span>
                <span className="text-accent">{squad.formation}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-slate-300">总能力</span>
                <span className="text-white font-bold">{squad.total_ability}</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center">
                  <div className="text-xs text-slate-500">前场</div>
                  <div className="text-red-400 font-bold">{squad.forward_ability}</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500">中场</div>
                  <div className="text-green-400 font-bold">{squad.midfield_ability}</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500">后场</div>
                  <div className="text-blue-400 font-bold">{squad.guard_ability}</div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Quick Actions */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <Button variant="secondary" className="h-16 flex-col gap-1" onClick={() => navigate('/match')}>
            <span className="text-lg">⚽</span>
            <span className="text-xs">比赛</span>
          </Button>
          <Button variant="secondary" className="h-16 flex-col gap-1" onClick={() => navigate('/lottery')}>
            <span className="text-lg">🎴</span>
            <span className="text-xs">抽卡</span>
          </Button>
          <Button variant="secondary" className="h-16 flex-col gap-1" onClick={() => navigate('/challenge')}>
            <span className="text-lg">🏆</span>
            <span className="text-xs">挑战</span>
          </Button>
          <Button variant="secondary" className="h-16 flex-col gap-1" onClick={() => navigate('/transfer')}>
            <span className="text-lg">💰</span>
            <span className="text-xs">转会</span>
          </Button>
        </div>

        {/* League shortcut */}
        <Card className="cursor-pointer hover:border-accent/40 transition-colors" onClick={() => navigate('/league')}>
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-200">联赛</p>
              <p className="text-xs text-slate-500">查看积分榜和赛程</p>
            </div>
            <span className="text-slate-600">→</span>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
