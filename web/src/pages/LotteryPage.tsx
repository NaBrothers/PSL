import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import api from '../api/client'
import { overallColor, rarityGlow } from '@/lib/card-display'
import PlayerCardDetail from '@/components/PlayerCardDetail'
import { useToast } from '@/components/AppToast'

interface PoolInfo {
  key: string
  name: string
  cost: number
  ten_cost: number
}

interface DrawnCard {
  id: number
  name: string
  position: string
  overall: number
  star: number
  style: string
  style_name: string
}

export default function LotteryPage() {
  const [pools, setPools] = useState<PoolInfo[]>([])
  const [rewardPacks, setRewardPacks] = useState<{name: string; count: number}[]>([])
  const [drawn, setDrawn] = useState<DrawnCard[]>([])
  const [loading, setLoading] = useState(false)
  const [animating, setAnimating] = useState(true)
  const [detail, setDetail] = useState<any>(null)
  const { showToast } = useToast()

  useEffect(() => {
    api.get('/lottery/pools').then(res => {
      setPools(res.data.pools)
      setRewardPacks(res.data.reward_packs || [])
    })
  }, [])

  const draw = async (pool: string, count: number) => {
    setLoading(true)
    setDrawn([])
    setAnimating(true)
    try {
      const res = await api.post('/lottery/draw', { pool, count })
      setDrawn(res.data.cards)
      setTimeout(() => setAnimating(false), 800)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '抽卡失败')
    }
    setLoading(false)
  }

  if (drawn.length > 0) {
    return (
      <div className="bg-dark p-4">
        <div className="max-w-md mx-auto">
          <h2 className="text-lg font-bold text-slate-100 mb-4 text-center">抽卡结果</h2>
          <div className="grid grid-cols-2 gap-3 mb-4">
            {drawn.map((c, i) => (
              <div
                key={c.id}
                onClick={() => api.get(`/cards/${c.id}`).then(res => setDetail(res.data))}
                className={`relative rounded-lg border-2 p-3 text-center transition-all duration-700 ${rarityGlow(c.overall)} ${animating ? 'opacity-0 scale-75 rotate-y-180' : 'opacity-100 scale-100'}`}
                style={{ transitionDelay: `${i * 100}ms`, background: 'linear-gradient(to bottom, rgba(30,41,59,0.8), rgb(15,23,42))' }}
              >
                <div className="text-[10px] text-slate-500">{c.position}</div>
                <div className={`text-2xl font-bold mt-1 ${overallColor(c.overall)}`}>
                  {c.overall}
                </div>
                <div className="text-sm text-slate-200 mt-1 truncate">{c.name}</div>
                <div className="text-yellow-400 text-xs mt-1">{c.star <= 5 ? '★'.repeat(c.star) : `★${c.star}`}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{c.style_name}</div>
              </div>
            ))}
          </div>
          <Button variant="outline" className="w-full" onClick={() => setDrawn([])}>
            返回卡包
          </Button>

          <Dialog open={detail !== null} onOpenChange={(open) => { if (!open) setDetail(null) }}>
            <DialogContent className="max-h-[85vh] overflow-y-auto scrollbar-hide">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 flex-wrap">
                  <span className="text-slate-500 text-sm">[{detail?.id}]</span>
                  <span className="text-slate-400 text-sm">{detail?.position}</span>
                  <span className={overallColor(detail?.overall || 0)}>{detail?.name}</span>
                  <span className={`font-bold ${overallColor(detail?.overall || 0)}`}>{detail?.overall}</span>
                </DialogTitle>
              </DialogHeader>
              <PlayerCardDetail detail={detail} />
            </DialogContent>
          </Dialog>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-dark p-4">
      <div className="max-w-md mx-auto">
        <h1 className="text-lg font-bold text-slate-100 mb-4">抽卡</h1>

        {/* Reward packs */}
        {rewardPacks.length > 0 && (
          <Card className="mb-4 border-yellow-600/40">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-yellow-400">奖励卡包</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {rewardPacks.map(p => (
                <div key={p.name} className="flex items-center justify-between text-sm">
                  <span className="text-slate-300">{p.name}</span>
                  <span className="text-yellow-400">×{p.count}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Pools */}
        <div className="space-y-3">
          {pools.map(p => (
            <Card key={p.key} className="hover:border-slate-600 transition-colors">
              <CardContent className="p-4">
                <div className="flex justify-between items-center mb-3">
                  <span className="text-slate-100 font-medium">{p.name}</span>
                  <span className="text-yellow-400 text-sm">${p.cost}</span>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" className="flex-1" onClick={() => draw(p.key, 1)} disabled={loading}>
                    单抽 ${p.cost}
                  </Button>
                  {p.ten_cost > 0 && (
                    <Button size="sm" variant="secondary" className="flex-1" onClick={() => draw(p.key, 10)} disabled={loading}>
                      十连 ${p.ten_cost}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
