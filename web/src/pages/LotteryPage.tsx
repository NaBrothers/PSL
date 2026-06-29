import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import api from '../api/client'

import PlayerCard from '@/components/PlayerCard'
import { useToast } from '@/components/AppToast'
import { haptic, hapticSuccess } from '@/lib/haptic'
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

const PACK_COVERS: Record<string, string> = {
  '初级': '/assets/packs/pack-basic.png',
  '初级前锋': '/assets/packs/pack-forward.png',
  '初级中场': '/assets/packs/pack-midfield.png',
  '初级后卫': '/assets/packs/pack-defender.png',
  '初级门将': '/assets/packs/pack-goalkeeper.png',
  '中级': '/assets/packs/pack-mid-tier.png',
  '中级前锋': '/assets/packs/pack-mid-forward.png',
  '中级中场': '/assets/packs/pack-mid-midfield.png',
  '中级后卫': '/assets/packs/pack-mid-defender.png',
  '中级门将': '/assets/packs/pack-mid-goalkeeper.png',
  '高级': '/assets/packs/pack-high-tier.png',
}

const PACK_ACCENT: Record<string, string> = {
  '初级': 'border-gold/50',
  '初级前锋': 'border-orange-500/50',
  '初级中场': 'border-blue-500/50',
  '初级后卫': 'border-emerald-500/50',
  '初级门将': 'border-purple-500/50',
  '中级': 'border-pink-500/50',
  '中级前锋': 'border-red-500/50',
  '中级中场': 'border-blue-400/50',
  '中级后卫': 'border-emerald-400/50',
  '中级门将': 'border-violet-500/50',
  '高级': 'border-yellow-400/60',
}

type TabKey = 'basic' | 'mid' | 'high' | 'reward'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'basic', label: '初级' },
  { key: 'mid', label: '中级' },
  { key: 'high', label: '高级' },
  { key: 'reward', label: '奖励' },
]

function poolTab(key: string): TabKey {
  if (key.startsWith('高级')) return 'high'
  if (key.startsWith('中级')) return 'mid'
  return 'basic'
}

export default function LotteryPage() {
  const navigate = useNavigate()
  const [pools, setPools] = useState<PoolInfo[]>([])
  const [rewardPacks, setRewardPacks] = useState<{name: string; count: number}[]>([])
  const [drawn, setDrawn] = useState<DrawnCard[]>([])
  const [animCard, setAnimCard] = useState<DrawnCard | null>(null)
  const [animQueue, setAnimQueue] = useState<DrawnCard[]>([])
  const [loading, setLoading] = useState(false)
  const [lastDraw, setLastDraw] = useState<{pool: string; count: number; isReward: boolean}>({pool: "", count: 1, isReward: false})
  const [animating, setAnimating] = useState(true)
  const [tab, setTab] = useState<TabKey>('basic')
  const { showToast } = useToast()

  useEffect(() => {
    api.get('/lottery/pools').then(res => {
      setPools(res.data.pools)
      setRewardPacks(res.data.reward_packs || [])
    })
  }, [])

  const draw = async (pool: string, count: number, isReward = false) => {
    haptic('medium')
    setLoading(true)
    setDrawn([])
    setAnimating(true)
    try {
      setLastDraw({pool, count, isReward})
      const endpoint = isReward ? '/lottery/draw-reward' : '/lottery/draw'
      const payload = isReward ? { pool } : { pool, count }
      const res = await api.post(endpoint, payload)
      const cards = res.data.cards as DrawnCard[]
      const rares = cards.filter(c => isRareCard(c.overall, c.star))
      if (rares.length > 0) {
        hapticSuccess()
        setAnimQueue(rares.slice(1))
        setAnimCard(rares[0])
      }
      setDrawn(cards)
      setTimeout(() => setAnimating(false), 600)
      if (isReward) {
        api.get('/lottery/pools').then(res => {
          setRewardPacks(res.data.reward_packs || [])
        })
      }
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

  // Results view
  if (drawn.length > 0) {
    return (
      <>
      {animCard && <PackOpenAnimation key={animCard.id} card={animCard} onComplete={handleAnimComplete} />}
      <div className="p-3 flex flex-col h-full">
        <h2 className="text-base font-bold text-slate-100 mb-3 text-center">抽卡结果</h2>
        <div className="flex-1 overflow-y-auto scrollbar-hide">
          <div className="grid grid-cols-3 gap-1.5 mb-4 justify-items-center">
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
                  onClick={() => navigate(`/cards/${c.id}`)}
                />
              </div>
            ))}
          </div>
        </div>
        <div className="flex gap-2 flex-shrink-0 pt-2">
          <Button variant="outline" className={`${lastDraw.isReward ? 'w-full' : 'flex-1'} h-10 border-dark-border text-slate-300`} onClick={() => setDrawn([])}>
            返回卡包
          </Button>
          {!lastDraw.isReward && (
            <Button className="flex-1 h-10 bg-gradient-to-r from-gold/90 to-yellow-600/90 text-black font-bold hover:from-gold hover:to-yellow-600" onClick={() => { setDrawn([]); draw(lastDraw.pool, lastDraw.count) }} disabled={loading}>
              {lastDraw.count === 1 ? '再来一发' : '再来十连'}
            </Button>
          )}
        </div>

      </div>
      </>
    )
  }

  const filteredPools = pools.filter(p => poolTab(p.key) === tab)

  return (
    <div className="p-3 flex flex-col gap-3 h-full">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <h1 className="text-lg font-bold text-slate-100">卡包商城</h1>
      </div>

      {/* Tab bar */}
      <div className="flex rounded-lg overflow-hidden border border-dark-border bg-dark-card/60 flex-shrink-0">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`flex-1 py-2 text-xs font-bold transition-all relative ${tab === t.key ? 'text-gold bg-gold/10' : 'text-slate-500 hover:text-slate-300'}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {tab === t.key && <span className="absolute bottom-0 left-1/4 right-1/4 h-[2px] bg-gold rounded-full" />}
            {t.key === 'reward' && rewardPacks.length > 0 && (
              <span className="absolute top-1 right-2 w-1.5 h-1.5 rounded-full bg-red-500" />
            )}
          </button>
        ))}
      </div>

      {/* Pack list */}
      <div className="flex-1 overflow-y-auto scrollbar-hide space-y-3">
        {tab !== 'reward' ? (
          filteredPools.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <div className="text-3xl mb-2">📦</div>
              <div className="text-sm">暂无可用卡包</div>
            </div>
          ) : (
            filteredPools.map(p => {
              const cover = PACK_COVERS[p.key] || '/assets/packs/pack-basic.png'
              const accent = PACK_ACCENT[p.key] || 'border-dark-border'
              return (
                <div key={p.key} className={`flex rounded-xl overflow-hidden border ${accent} bg-dark-card/80 transition-all shadow-lg group`}>
                  {/* Left cover image */}
                  <div className="w-[100px] flex-shrink-0 relative overflow-hidden bg-black/30">
                    <img
                      src={cover}
                      alt={p.name}
                      className="absolute inset-0 w-full h-full object-cover object-top group-hover:scale-105 transition-transform duration-300"
                    />
                  </div>
                  {/* Right info */}
                  <div className="flex-1 p-3 flex flex-col justify-center min-w-0 gap-2">
                    <div>
                      <div className="text-slate-100 font-bold text-[15px]">{p.name}</div>
                      <div className="text-[11px] text-slate-400 mt-1">
                        单抽 <span className="text-gold font-bold">${p.cost}</span>
                        {p.ten_cost > 0 && <> · 十连 <span className="text-purple-400 font-bold">${p.ten_cost}</span></>}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        className="flex-1 bg-gradient-to-r from-gold/90 to-yellow-600/90 text-black font-bold text-[11px] hover:from-gold hover:to-yellow-600 h-9 rounded-lg shadow-md"
                        onClick={() => draw(p.key, 1)}
                        disabled={loading}
                      >
                        单抽
                      </Button>
                      {p.ten_cost > 0 && (
                        <Button
                          size="sm"
                          className="flex-1 bg-gradient-to-r from-purple-600/90 to-indigo-600/90 text-white font-bold text-[11px] hover:from-purple-600 hover:to-indigo-600 h-9 rounded-lg shadow-md"
                          onClick={() => draw(p.key, 10)}
                          disabled={loading}
                        >
                          十连
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })
          )
        ) : (
          /* Reward packs tab */
          rewardPacks.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <div className="text-3xl mb-2">🎁</div>
              <div className="text-sm">暂无奖励卡包</div>
              <div className="text-[11px] text-slate-600 mt-1">通过比赛和活动获取</div>
            </div>
          ) : (
            rewardPacks.map(p => (
              <div key={p.name} className="flex rounded-xl overflow-hidden border border-gold/30 bg-dark-card/60 shadow-lg">
                <div className="w-[110px] min-h-[110px] flex-shrink-0 bg-gradient-to-br from-amber-900/80 via-yellow-800/60 to-orange-700/80 flex flex-col items-center justify-center relative">
                  <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.08),transparent_60%)]" />
                  <span className="text-4xl drop-shadow-lg relative z-10">🎁</span>
                </div>
                <div className="flex-1 p-3 flex flex-col justify-between">
                  <div>
                    <div className="text-slate-100 font-bold text-sm">{p.name}</div>
                    <div className="text-gold text-xs font-bold mt-1">剩余 ×{p.count}</div>
                  </div>
                  <Button
                    size="sm"
                    className="mt-2.5 w-full bg-gradient-to-r from-gold/90 to-yellow-600/90 text-black font-bold text-[11px] hover:from-gold hover:to-yellow-600 h-8 rounded-lg"
                    onClick={() => draw(p.name, 1, true)}
                    disabled={loading}
                  >
                    开启
                  </Button>
                </div>
              </div>
            ))
          )
        )}
      </div>
    </div>
  )
}
