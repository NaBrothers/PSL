import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Sparkles, Gift } from 'lucide-react'
import api from '../api/client'
import { overallColor } from '@/lib/card-display'
import PlayerCardDetail from '@/components/PlayerCardDetail'
import PlayerCard from '@/components/PlayerCard'
import { useToast } from '@/components/AppToast'
import PackOpenAnimation from '@/components/PackOpenAnimation'

interface PoolInfo {
  key: string
  name: string
  cost: number
  ten_cost: number
}

interface DrawnCard {
  id: number
  player_id: number
  name: string
  position: string
  overall: number
  star: number
  style: string
  style_name: string
  nationality: string
  club: string
  top_abilities?: { name: string; value: number }[]
}

const STAR_ABILITY: Record<number, number> = {1:0,2:1,3:2,4:4,5:6,6:8,7:11,8:14,9:17,10:21}
function isRareCard(overall: number, star: number): boolean {
  const bonus = STAR_ABILITY[star] ?? 0
  const v = overall - bonus + star - 1
  return v >= 89
}

export default function LotteryPage() {
  const [pools, setPools] = useState<PoolInfo[]>([])
  const [rewardPacks, setRewardPacks] = useState<{name: string; count: number}[]>([])
  const [drawn, setDrawn] = useState<DrawnCard[]>([])
  const [animCard, setAnimCard] = useState<DrawnCard | null>(null)
  const [animQueue, setAnimQueue] = useState<DrawnCard[]>([])
  const [loading, setLoading] = useState(false)
  const [lastDraw, setLastDraw] = useState<{pool: string; count: number}>({pool: "", count: 1})
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
      setLastDraw({pool, count})
      const res = await api.post('/lottery/draw', { pool, count })
      const cards = res.data.cards as DrawnCard[]
      const rares = cards.filter(c => isRareCard(c.overall, c.star))
      if (rares.length > 0) {
        setAnimQueue(rares.slice(1))
        setAnimCard(rares[0])
      }
      setDrawn(cards)
      setTimeout(() => setAnimating(false), 600)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '抽卡失败')
    }
    setLoading(false)
  }

  const handleAnimComplete = () => {
    if (animQueue.length > 0) {
      setAnimCard(animQueue[0])
      setAnimQueue(animQueue.slice(1))
    } else {
      setAnimCard(null)
    }
  }

  if (drawn.length > 0) {
    return (
      <>
      {animCard && <PackOpenAnimation key={animCard.id} card={animCard} onComplete={handleAnimComplete} />}
      <div className="p-4">
        <h2 className="text-lg font-bold text-slate-100 mb-4 text-center">抽卡结果</h2>
        <div className="grid grid-cols-3 gap-2 mb-4 justify-items-center">
          {drawn.map((c, i) => (
            <div
              key={c.id}
              className={`transition-all duration-700 ${animating ? 'opacity-0 scale-50' : 'opacity-100 scale-100'}`}
              style={{ transitionDelay: `${i * 80}ms` }}
            >
              <PlayerCard
                playerId={c.player_id}
                name={c.name}
                position={c.position}
                overall={c.overall}
                star={c.star}
                style={c.style}
                topAbilities={c.top_abilities}
                size="sm"
                onClick={() => api.get(`/cards/${c.id}`).then(res => setDetail(res.data))}
              />
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => setDrawn([])}>
            返回卡包
          </Button>
          <Button className="flex-1" onClick={() => { setDrawn([]); draw(lastDraw.pool, lastDraw.count) }} disabled={loading}>
            {lastDraw.count === 1 ? '再来一发' : '再来十连'}
          </Button>
        </div>

        <Dialog open={detail !== null} onOpenChange={(open) => { if (!open) setDetail(null) }}>
          <DialogContent className="max-h-[85vh] overflow-y-auto scrollbar-hide">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 flex-wrap">
                <span className="text-slate-500 text-sm">[{detail?.id}]</span>
                <span className={overallColor(detail?.overall || 0, detail?.star)}>{detail?.name}</span>
                <span className={`font-bold ${overallColor(detail?.overall || 0, detail?.star)}`}>{detail?.overall}</span>
              </DialogTitle>
            </DialogHeader>
            <PlayerCardDetail detail={detail} />
          </DialogContent>
        </Dialog>
      </div>
      </>
    )
  }

  return (
    <div className="p-4">
      <h1 className="text-lg font-bold text-slate-100 mb-4 flex items-center gap-2">
        <Sparkles size={20} className="text-gold" />
        抽卡
      </h1>

      {/* Reward packs */}
      {rewardPacks.length > 0 && (
        <div className="mb-4 bg-gradient-to-r from-yellow-900/20 to-orange-900/20 border border-gold/30 rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <Gift size={14} className="text-gold" />
            <span className="text-sm font-medium text-gold">奖励卡包</span>
          </div>
          <div className="space-y-1">
            {rewardPacks.map(p => (
              <div key={p.name} className="flex items-center justify-between text-sm">
                <span className="text-slate-300">{p.name}</span>
                <span className="text-gold font-bold">×{p.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pools */}
      <div className="space-y-3">
        {pools.map(p => (
          <div key={p.key} className="bg-dark-card/80 border border-dark-border rounded-xl overflow-hidden hover:border-gold/30 transition-colors">
            <div className="p-4">
              <div className="flex justify-between items-center mb-3">
                <span className="text-slate-100 font-bold">{p.name}</span>
                <span className="text-gold text-sm font-medium">${p.cost}/抽</span>
              </div>
              <div className="flex gap-2">
                <Button size="sm" className="flex-1 bg-gradient-to-r from-gold/80 to-yellow-600/80 text-black font-bold hover:from-gold hover:to-yellow-600" onClick={() => draw(p.key, 1)} disabled={loading}>
                  单抽 ${p.cost}
                </Button>
                {p.ten_cost > 0 && (
                  <Button size="sm" className="flex-1 bg-gradient-to-r from-purple-600/80 to-blue-600/80 text-white font-bold hover:from-purple-600 hover:to-blue-600" onClick={() => draw(p.key, 10)} disabled={loading}>
                    十连 ${p.ten_cost}
                  </Button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
