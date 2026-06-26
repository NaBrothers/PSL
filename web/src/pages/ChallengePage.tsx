import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import api from '../api/client'
import { useToast } from '@/components/AppToast'

interface ChallengeInfo {
  npc_name: string
  times_left: number
  difficulties: { key: string; star: number }[]
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

  if (!info) return <div className="bg-dark flex items-center justify-center text-slate-500">加载中...</div>

  if (result) {
    return (
      <div className="bg-dark p-4">
        <div className="max-w-md mx-auto">
          {/* Score */}
          <div className="text-center py-6 mb-4 bg-gradient-to-b from-slate-800/50 to-transparent rounded-xl">
            <div className="text-4xl font-bold mb-2">
              <span className="text-accent">{result.home_score}</span>
              <span className="text-slate-600 mx-3">-</span>
              <span className="text-red-400">{result.away_score}</span>
            </div>
            <p className={`text-lg font-bold ${result.result === 'win' ? 'text-green-400' : result.result === 'lose' ? 'text-red-400' : 'text-yellow-400'}`}>
              {result.result === 'win' ? '胜利！' : result.result === 'lose' ? '失败' : '平局'}
            </p>
            {result.award && <p className="text-yellow-400 text-sm mt-2">奖励: {result.award}</p>}
          </div>

          {/* Report */}
          <Card className="mb-4">
            <CardContent className="p-4">
              <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{result.report}</p>
            </CardContent>
          </Card>

          <Button variant="outline" className="w-full" onClick={() => setResult(null)}>返回</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-dark p-4">
      <div className="max-w-md mx-auto">
        <h1 className="text-lg font-bold text-slate-100 mb-2">每日挑战</h1>

        {/* NPC Info */}
        <Card className="mb-4">
          <CardContent className="p-4 text-center">
            <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-2">
              <span className="text-2xl">🏟️</span>
            </div>
            <h2 className="text-accent font-bold text-lg">{info.npc_name}</h2>
            <p className="text-slate-500 text-sm mt-1">剩余次数: <span className="text-yellow-400">{info.times_left}</span></p>
          </CardContent>
        </Card>

        {/* Difficulties */}
        <p className="text-slate-400 text-sm mb-2">选择难度</p>
        <div className="space-y-2">
          {info.difficulties.map(d => (
            <Card key={d.key} className="hover:border-slate-600 transition-colors cursor-pointer" onClick={() => !loading && info.times_left > 0 && play(d.key)}>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <span className="text-slate-100 font-medium">{d.key}</span>
                  <span className="text-yellow-400 ml-2 text-sm">{d.star <= 5 ? '★'.repeat(d.star) : `★${d.star}`}</span>
                </div>
                <Button size="sm" disabled={loading || info.times_left <= 0}>
                  {loading ? '进行中...' : '开赛'}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
