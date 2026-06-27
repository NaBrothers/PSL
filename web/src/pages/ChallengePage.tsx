import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Trophy, Zap } from 'lucide-react'
import api from '../api/client'
import { useToast } from '@/components/AppToast'

interface ChallengeInfo {
  npc_name: string
  times_left: number
  difficulties: { key: string; star: number }[]
}

const DIFF_COLORS: Record<string, string> = {
  '简单': 'from-green-500/20 to-green-900/10 border-green-500/30',
  '普通': 'from-blue-500/20 to-blue-900/10 border-blue-500/30',
  '困难': 'from-orange-500/20 to-orange-900/10 border-orange-500/30',
  '地狱': 'from-red-500/20 to-red-900/10 border-red-500/30',
  '噩梦': 'from-purple-500/20 to-purple-900/10 border-purple-500/30',
}

export default function ChallengePage() {
  const [info, setInfo] = useState<ChallengeInfo | null>(null)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const { showToast } = useToast()

  useEffect(() => {
    api.get('/challenge').then(res => setInfo(res.data))
  }, [])

  const play = async (difficulty: string) => {
    setLoading(true)
    try {
      const res = await api.post('/challenge/play', { difficulty, mode: 'quick' })
      setResult(res.data)
      setInfo(prev => prev ? { ...prev, times_left: res.data.times_left } : null)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '挑战失败')
    }
    setLoading(false)
  }

  if (!info) return <div className="flex items-center justify-center h-full text-slate-500">加载中...</div>

  if (result) {
    return (
      <div className="p-4">
        <div className="text-center py-8 mb-4 rounded-xl border border-dark-border bg-gradient-to-b from-dark-card/80 to-transparent relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(212,168,67,0.05),transparent_60%)]" />
          <div className="relative">
            <div className="text-5xl font-black mb-2">
              <span className="text-accent">{result.home_score}</span>
              <span className="text-gold mx-3">:</span>
              <span className="text-red-400">{result.away_score}</span>
            </div>
            <p className={`text-xl font-bold ${result.result === 'win' ? 'text-green-400' : result.result === 'lose' ? 'text-red-400' : 'text-yellow-400'}`}>
              {result.result === 'win' ? '胜利！' : result.result === 'lose' ? '失败' : '平局'}
            </p>
            {result.award && (
              <p className="text-gold text-sm mt-2 font-medium">奖励: {result.award}</p>
            )}
          </div>
        </div>

        <Card className="mb-4">
          <CardContent className="p-4">
            <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{result.report}</p>
          </CardContent>
        </Card>

        <Button variant="outline" className="w-full" onClick={() => setResult(null)}>返回</Button>
      </div>
    )
  }

  return (
    <div className="p-4">
      <h1 className="text-lg font-bold text-slate-100 mb-4 flex items-center gap-2">
        <Trophy size={20} className="text-gold" />
        每日挑战
      </h1>

      {/* NPC Info */}
      <div className="mb-5 text-center bg-gradient-to-b from-dark-card/80 to-transparent border border-dark-border rounded-xl p-5 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(79,195,247,0.03),transparent_70%)]" />
        <div className="relative">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-accent/20 to-blue-600/10 border-2 border-accent/40 flex items-center justify-center mx-auto mb-3">
            <span className="text-2xl">🏟️</span>
          </div>
          <h2 className="text-accent font-bold text-lg">{info.npc_name}</h2>
          <div className="flex items-center justify-center gap-1 mt-2">
            <Zap size={14} className="text-gold" />
            <span className="text-slate-400 text-sm">剩余次数:</span>
            <span className="text-gold font-bold">{info.times_left}</span>
          </div>
        </div>
      </div>

      {/* Difficulties */}
      <p className="text-slate-400 text-sm mb-2 font-medium">选择难度</p>
      <div className="space-y-2">
        {info.difficulties.map(d => {
          const colorClass = DIFF_COLORS[d.key] || 'from-slate-500/20 to-slate-900/10 border-slate-500/30'
          return (
            <div
              key={d.key}
              className={`rounded-xl border bg-gradient-to-r ${colorClass} p-4 flex items-center justify-between cursor-pointer hover:scale-[1.01] transition-transform`}
              onClick={() => !loading && info.times_left > 0 && play(d.key)}
            >
              <div className="flex items-center gap-3">
                <span className="text-slate-100 font-bold">{d.key}</span>
                <div className="flex gap-0.5">
                  {Array.from({ length: Math.min(d.star, 5) }).map((_, i) => (
                    <div key={i} className="w-2 h-2 bg-gold rotate-45" />
                  ))}
                  {d.star > 5 && <span className="text-[9px] text-gold ml-0.5">×{d.star}</span>}
                </div>
              </div>
              <Button size="sm" disabled={loading || info.times_left <= 0} className="bg-gold/80 text-black hover:bg-gold font-bold">
                {loading ? '进行中...' : '开赛'}
              </Button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
